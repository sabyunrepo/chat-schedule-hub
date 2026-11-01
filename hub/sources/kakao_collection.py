"""Private room policy and bounded host-observation ingestion for Kakao UI."""
import uuid
import re
from datetime import datetime
from ..core import now, require
from ..selection import select_ingest
from .kakao_anchors import KakaoAnchors


def eligibility(quiet, latest, since):
    if quiet is True:
        return 'excluded-quiet'
    if quiet is not False or latest is None:
        return 'needs-verification'
    return 'eligible' if datetime.fromisoformat(latest) >= datetime.fromisoformat(since) else 'excluded-inactive'


# Conservative local exclusion before fingerprints or external processing.
FINANCIAL = re.compile(r"카카오페이|송금|입금|출금|결제|청구|납부|계좌|카드|은행|금액|요금|원(?:을|이|의|입니다|\s|$)|쿠폰|포인트|보험|대출|잔액|환불|거래|결제일|수수료")

def filter_rows(rows, since, until):
    """Retain only explicitly reviewed rows; None preserves every excluded position."""
    start, end = datetime.fromisoformat(since), datetime.fromisoformat(until)
    counts={k:0 for k in ('period','financial','undated','non_schedule','hold','allowed')}
    result=[]
    for row in rows:
        if row is None:
            counts['hold']+=1; result.append(None); continue
        stamp=row.get('sentAt')
        try:
            date=datetime.fromisoformat(stamp) if stamp else None
            in_period=date is not None and start <= date <= end
        except (ValueError, TypeError):
            date=None; in_period=False
        text=row.get('text','')
        if date is None: reason='undated'
        elif not in_period: reason='period'
        elif FINANCIAL.search(text): reason='financial'
        elif row.get('reviewedSchedule') is False: reason='non_schedule'
        elif row.get('reviewedSchedule') is not True or not row.get('authorDisplayName') or not text: reason='hold'
        else: reason='allowed'
        counts[reason]+=1
        result.append({k:row[k] for k in ('text','sentAt','authorRef','authorDisplayName') if k in row} if reason=='allowed' else None)
    return result, counts

def collect(store, target, label, observations, latest, quiet, since, until, provider):
    """Caller supplies two independently observed, normalized UI windows.

    Never declares history complete. Unknown timestamps remain pending rather than
    being silently admitted to a bounded collection period.
    """
    require(len(observations) == 2, 'two actual observations required')
    state=eligibility(quiet, latest, since)
    if state != 'eligible':
        return {'state':state,'apiCalls':0,'retained':0}
    classified=[filter_rows(view,since,until) for view in observations]
    filtered=[entry[0] for entry in classified]
    def triples(view):
        return [tuple((r.get('text'),r.get('sentAt'),r.get('authorRef')) for r in view[i:i+3])
                for i in range(len(view)-2) if all(r is not None for r in view[i:i+3])]
    from collections import Counter
    left,right=map(lambda v:Counter(triples(v)),filtered)
    if not any(n==1 and right.get(t)==1 for t,n in left.items()):
        return {'state':'held','matched':0,'apiCalls':0,'retained':0,
                'filterCountsByObservation':[entry[1] for entry in classified], 'coverageVerified':False}
    store.db.execute('CREATE TABLE IF NOT EXISTS kakao_rooms(target TEXT PRIMARY KEY,label TEXT,latest TEXT,state TEXT,updated TEXT)')
    with store.db:
        store.db.execute('INSERT OR REPLACE INTO kakao_rooms VALUES(?,?,?,?,?)',(target,label,latest,state,now()))
    store.register_target(target,'kakao-mac','local-kakao',label,{'since':since,'until':until,'excludeQuiet':True,'inactiveDays':30})
    anchors=KakaoAnchors(store.db)
    anchors.observe(target,filtered[0])
    matched=anchors.observe(target,filtered[1])
    rows=[m for m in matched['messages'] if m.get('sentAt') and datetime.fromisoformat(since)<=datetime.fromisoformat(m['sentAt'])<=datetime.fromisoformat(until)]
    run=store.begin(target)
    results=[]
    for offset in range(0,len(rows),32):
        batch={'schemaVersion':1,'batchId':str(uuid.uuid4()),'runId':run['id'],'targetId':target,
               'verifiedTarget':True,'externalProcessingAllowed':True,
               'messages':[{**m,'observedAt':m.get('observedAt') or now()} for m in rows[offset:offset+32]],
               'cursor':{'hostObservationOnly':True},'stopReason':'budget-exhausted','coverageVerified':False}
        results.append(select_ingest(store,batch,provider,
            'Kakao recruitment room: a recruitment card may be cancelled or deleted because recruitment is complete. '
            'Do not infer the actual gathering is cancelled. Display names are not verified account IDs.'))
    with store.db:
        store.db.execute('UPDATE kakao_rooms SET state=?,updated=? WHERE target=?',('partial',now(),target))
    return {'state':'partial','matched':matched['matchedRows'],'unconfirmed':matched['unconfirmed'],
            'filterCountsByObservation':[entry[1] for entry in classified], 'batches':results,'coverageVerified':False}
