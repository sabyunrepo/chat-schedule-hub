"""Durable host-driven UI scan. No pixel coordinates or private Kakao API.

Windows are chronological (oldest first); the host scrolls towards older messages
with a three-message overlap. A checkpoint is published only after ingestion.
"""
import json
import time
from collections import Counter
from datetime import datetime
from ..core import digest, require, now
from ..selection import RULE_VERSION
from .kakao_collection import collect, eligibility, filter_rows


def fingerprints(rows):
    return [digest({k:r.get(k) for k in ('text','sentAt','authorRef','authorDisplayName')})
            if r is not None else None for r in rows]


def overlap(a, b):
    def triples(seq):
        return Counter(tuple(seq[i:i+3]) for i in range(len(seq)-2)
                       if None not in seq[i:i+3])
    aa, bb = triples(a), triples(b)
    matches=[(a.index(t[0]), b.index(t[0])) for t,n in aa.items()
             if n == 1 and bb[t] == 1 and a.count(t[0]) == b.count(t[0]) == 1]
    # Reject contradictory ordering rather than merging repeated/reordered rows.
    return bool(matches) and [j for _,j in sorted(matches)] == sorted(j for _,j in matches)


class KakaoScan:
    def __init__(self, store):
        self.store=store
        store.db.execute('CREATE TABLE IF NOT EXISTS kakao_scan_state(target TEXT PRIMARY KEY, state TEXT NOT NULL, updated TEXT NOT NULL)')

    def status(self, target):
        row=self.store.db.execute('SELECT state FROM kakao_scan_state WHERE target=?',(target,)).fetchone()
        return json.loads(row[0]) if row else None

    def save(self, target, state):
        with self.store.db:
            self.store.db.execute('INSERT OR REPLACE INTO kakao_scan_state VALUES(?,?,?)',
                                  (target,json.dumps(state),now()))
            if state['phase']=='complete':
                # The adapter owns UI boundaries; do not publish unverified generic
                # message-ID boundaries from legacy runs to Store.begin().
                self.store.db.execute("UPDATE runs SET state='complete',reason='kakao-scan-complete',cursor=?,updated=? WHERE target=? AND state='active'",
                    (json.dumps({'adapter':'kakao-mac','cursorVersion':1,'stateTable':'kakao_scan_state'}),now(),target))

    def start(self, target, label, since, until, quiet, latest, max_pages=80):
        require(isinstance(target,str) and bool(target.strip()) and isinstance(label,str) and bool(label.strip()),'stable target and label required')
        start,end=map(datetime.fromisoformat,(since,until))
        require(start.tzinfo is not None and end.tzinfo is not None and start<=end,'invalid bounded range')
        state=eligibility(quiet,latest,since)
        if state != 'eligible': return {'state':state,'action':'stop'}
        require(1<=max_pages<=500,'invalid page budget')
        old=self.status(target)
        # until can grow between runs without losing the unfinished frontier.
        scope=digest([target,label,RULE_VERSION,1])
        if old and (start < datetime.fromisoformat(old['since']) or end < datetime.fromisoformat(old['until'])): old=None
        if old and old['scope']==scope and old['phase']!='complete':
            old.update(phase='seeking' if old['frontier'] else 'scanning',pages=0,last=[],stalls=0,maxPages=max_pages,until=until)
            state=old
        else:
            state=dict(scope=scope,label=label,since=since,until=until,phase='scanning',
                       baseline=old['head'] if old and old['scope']==scope and old['phase']=='complete' else [],
                       head=[],frontier=[],pages=0,last=[],stalls=0,maxPages=max_pages,deferredLatest=False)
        self.save(target,state)
        return {'state':state['phase'],'action':'open-latest','resuming':bool(state['frontier']),
                'since':state['since'],'until':state['until'],'coverageVerified':False}

    def step(self, target, label, observations, provider, *, quiet, latest,
             at_latest=False, source_end=False, range_end=False, cancelled=False):
        state=self.status(target)
        require(state is not None,'start scan first')
        require(label==state['label'],'observed room mismatch')
        if cancelled: return {'state':'cancelled','action':'stop','coverageVerified':False}
        policy=eligibility(quiet,latest,state['since'])
        if policy!='eligible': return {'state':policy,'action':'stop'}
        if state['phase']=='complete': return {'state':'complete','action':'stop','coverageVerified':True}
        if state['pages']>=state['maxPages']:
            return {'state':'anchor-lost' if state['phase']=='seeking' else 'budget-exhausted','action':'stop','coverageVerified':False}
        require(len(observations)==2 and all(3<=len(v)<=500 for v in observations),'two bounded observations required')
        filtered=[filter_rows(v,state['since'],state['until']) for v in observations]
        views=[v[0] for v in filtered]
        hashes=[fingerprints(v) for v in views]
        # Excluded/unknown rows must not form a false contiguous boundary.
        if (hashes[0]!=hashes[1] or not overlap(*hashes)
                or any(counts['hold'] or counts['undated'] for _,counts in filtered)):
            return {'state':'needs-review','action':'stop','coverageVerified':False}
        current=hashes[1]
        if not state['pages']: require(at_latest is True,'first observation must be verified latest screen')
        state['pages']+=1
        state['stalls']=state['stalls']+1 if current==state['last'] else 0
        if state['stalls']>=2:
            self.save(target,state)
            return {'state':'no-content-progress','action':'stop','coverageVerified':False}
        previous=state['last']; state['last']=current
        if state['phase']=='seeking':
            # Read-only navigation: never classify the intervening screens.
            if overlap(state['frontier'],current):
                state['phase']='scanning'
                # The located page can expose older rows: ingest it before scrolling.
                previous=state['frontier']
            else:
                state['deferredLatest']=True
                self.save(target,state)
                return {'state':'seeking','action':'scroll-older','apiCalls':0,'coverageVerified':False}
        if previous and not overlap(previous,current):
            # Keep the durable frontier; require restart/reacquisition after a jump.
            return {'state':'gap-detected','action':'stop','coverageVerified':False}
        known=overlap(state['baseline'],current)
        result=collect(self.store,target,label,observations,latest,quiet,state['since'],state['until'],provider)
        if (result.get('state')!='partial' or result.get('unconfirmed')!=current.count(None)
                or not result.get('batches')
                or any(b.get('selection',{}).get('evidenceGaps') for b in result.get('batches',[]))):
            return {'state':'needs-review','action':'stop','collection':result,'coverageVerified':False}
        # collect has committed every batch. A crash before save only replays a page.
        if not state['head']: state['head']=current
        state['frontier']=current
        complete=known or source_end or range_end
        if complete: state['phase']='complete'
        self.save(target,state)
        return {'state':'complete' if complete else 'scanning',
                'action':('restart-latest' if state.get('deferredLatest') else 'stop') if complete else 'scroll-older',
                'reason':'known-boundary' if known else 'explicit-source-end' if source_end else 'requested-range-reached' if range_end else 'continue',
                'coverageVerified':bool(complete),'collection':result}


def run_scan(scan, driver, provider, *, max_seconds=180, **scope):
    """ComputerDriver integration; driver supplies reviewed UI, not hidden APIs.

    driver.open_latest(target), observe_pair(), scroll_older() are synchronous.
    observe_pair returns step keyword args including observed target/label, quiet,
    latest, at_latest and optional explicit end evidence. No absence inference.
    """
    deadline=time.monotonic()+max_seconds
    outcome=scan.start(**scope)
    if outcome['action']=='stop': return outcome
    driver.open_latest(scope['target'])
    while True:
        if time.monotonic()>=deadline:
            return {'state':'budget-exhausted','action':'stop','coverageVerified':False}
        frame=driver.observe_pair()
        require(frame.get('target')==scope['target'],'driver target changed')
        outcome=scan.step(provider=provider,**frame)
        if outcome['action']=='stop': return outcome
        if outcome['action']=='restart-latest':
            scan.start(**scope)
            driver.open_latest(scope['target'])
            continue
        driver.scroll_older()
