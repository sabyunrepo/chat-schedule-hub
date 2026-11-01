"""Process a short buffer of real, independently captured Kakao UI frames.

This helper does not drive the UI, invent a second observation, concatenate
windows, or establish history coverage. The host must supply a fresh observation
ID for each actual capture and verify the focused room before capturing it.
"""
import time
from collections import Counter

from ..core import digest, require
from .kakao_collection import collect, eligibility, filter_rows


def _triples(rows):
    # Filtering occurs first: never fingerprint financial/excluded raw content.
    keys=[digest(row) if row is not None else None for row in rows]
    counts=Counter(tuple(keys[i:i+3]) for i in range(len(keys)-2)
                   if None not in keys[i:i+3])
    return {triple for triple,count in counts.items() if count==1}


def collect_buffer(store, target, label, frames, latest, quiet, since, until, provider):
    """Select/persist overlapping frames, with serial writes and bounded memory.

    frames: 2..8 dictionaries containing observationId and rows (0..500 rows,
    at most 2000 rows total). Optional target/label must match the outer scope.
    rows contain the same reviewed fields as collect(); None gaps are retained.
    A repeated payload is valid only when independently observed under another
    observationId. IDs are host assertions, not proof of an independent capture.

    Errors propagate. Successful earlier collect() calls remain committed; the
    caller can replay the same real observations through the common cache. This
    method never promotes kakao_scan_state or declares an entire room complete.
    """
    started=time.perf_counter()
    policy=eligibility(quiet,latest,since)
    if policy!='eligible':
        return dict(state=policy,coverageVerified=False,apiCalls=0,new=0,changed=0,
                    elapsedMs=round((time.perf_counter()-started)*1000,2))
    require(isinstance(frames,list) and 2<=len(frames)<=8,'need 2..8 real observation frames')
    ids=set(); total_rows=0
    for frame in frames:
        require(isinstance(frame,dict),'invalid frame')
        oid=frame.get('observationId')
        require(isinstance(oid,str) and 0<len(oid)<=128 and oid not in ids,
                'distinct observation IDs required')
        ids.add(oid)
        require(frame.get('target',target)==target and frame.get('label',label)==label,
                'observed room mismatch')
        rows=frame.get('rows')
        require(isinstance(rows,list) and len(rows)<=500,'invalid bounded frame')
        total_rows+=len(rows)
        for row in rows:
            require(row is None or (isinstance(row,dict)
                    and isinstance(row.get('text'),str) and len(row['text'])<=100000),
                    'invalid reviewed row')
    require(total_rows<=2000,'buffer row budget exceeded')

    prepared=[]
    for frame in frames:
        filtered,counts=filter_rows(frame['rows'],since,until)
        # Keep reviewed evidence on the sanitized input for collect's own guard.
        rows=[dict(row,reviewedSchedule=True) if row is not None else None for row in filtered]
        prepared.append(dict(rows=rows,counts=counts,triples=_triples(rows),key=digest(rows)))

    completed=set(); attempted=set(); results=[]; reports=[]
    for i,current in enumerate(prepared):
        report=dict(index=i,observationId=frames[i]['observationId'],
                    filterCounts=current['counts'],state='unmatched')
        reports.append(report)
        if current['key'] in completed:
            report['state']='skipped-processed-frame'
            continue
        # Prefer the actual earlier observation with the strongest unique overlap.
        candidates=[(len(current['triples'] & prior['triples']),j)
                    for j,prior in enumerate(prepared[:i])]
        candidates=[(score,j) for score,j in candidates if score
                    and (prepared[j]['key'],current['key']) not in attempted]
        if not candidates: continue
        _,j=max(candidates)
        prior=prepared[j]
        result=collect(store,target,label,[prior['rows'],current['rows']],latest,quiet,since,until,provider)
        attempted.add((prior['key'],current['key']))
        report.update(state=result['state'],matched=result.get('matched',0),
                      unconfirmed=result.get('unconfirmed',len(current['rows'])),referenceIndex=j)
        results.append(dict(frameIndex=i,referenceIndex=j,result=result))
        # A partial frame must remain retryable when another observation supplies
        # additional matching context. Only fully identified permitted rows skip.
        if (result.get('state')=='partial' and result.get('batches')
                and result.get('unconfirmed')==current['rows'].count(None)):
            completed.add(current['key'])

    for i,report in enumerate(reports):
        if report['state']=='unmatched' and prepared[i]['key'] in completed:
            report['state']='confirmed-by-later-observation'
    batches=[batch for entry in results for batch in entry['result'].get('batches',[])]
    metrics=[batch.get('selection',{}) for batch in batches]
    return dict(state='partial' if batches else 'held',coverageVerified=False,
                frames=reports,collections=results,observedRows=total_rows,
                candidateRows=sum(p['counts']['allowed'] for p in prepared),
                processedFrames=len(results),
                skippedFrames=sum(r['state']=='skipped-processed-frame' for r in reports),
                unmatchedFrames=sum(r['state']=='unmatched' for r in reports),
                apiCalls=sum(m.get('apiCalls',0) for m in metrics),
                apiMs=round(sum(m.get('apiMs',0) for m in metrics),2),
                retained=sum(m.get('retained',0) for m in metrics),
                new=sum(b.get('new',0) for b in batches),
                changed=sum(b.get('changed',0) for b in batches),
                elapsedMs=round((time.perf_counter()-started)*1000,2))
