"""Private room policy and bounded host-observation ingestion for Kakao UI."""
import uuid
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


def collect(store, target, label, observations, latest, quiet, since, until, provider):
    """Caller supplies two independently observed, normalized UI windows.

    Never declares history complete. Unknown timestamps remain pending rather than
    being silently admitted to a bounded collection period.
    """
    require(len(observations) == 2, 'two actual observations required')
    state=eligibility(quiet, latest, since)
    store.db.execute('CREATE TABLE IF NOT EXISTS kakao_rooms(target TEXT PRIMARY KEY,label TEXT,latest TEXT,state TEXT,updated TEXT)')
    with store.db:
        store.db.execute('INSERT OR REPLACE INTO kakao_rooms VALUES(?,?,?,?,?)',(target,label,latest,state,now()))
    if state != 'eligible':
        return {'state':state,'apiCalls':0,'retained':0}
    store.register_target(target,'kakao-mac','local-kakao',label,{'since':since,'until':until,'excludeQuiet':True,'inactiveDays':30})
    anchors=KakaoAnchors(store.db)
    anchors.observe(target,observations[0])
    matched=anchors.observe(target,observations[1])
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
            'undatedOrOutsideRange':len(matched['messages'])-len(rows),'batches':results,'coverageVerified':False}
