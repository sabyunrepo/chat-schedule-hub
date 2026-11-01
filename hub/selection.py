"""Classify observed pages before retaining text; checkpoints remain transactional."""
import json, time, re
from .core import digest, require

RULE_VERSION = 4
RELEVANCE_FLOOR = .1


def fingerprint(message):
    return digest({k:message.get(k) for k in ['text','authorRef','sentAt','attachments','observationKind']})


def select_ingest(store, batch, provider, context=''):
    require(batch.get('externalProcessingAllowed') is True, 'External processing must be enabled')
    require(len(batch['messages']) <= 32, 'selective page limit is 32 messages')
    # Validate scope before sending anything to a provider.
    run=store.db.execute('SELECT target,state FROM runs WHERE id=?',(batch['runId'],)).fetchone()
    require(run and run['target']==batch['targetId'] and batch.get('verifiedTarget') is True,'unverified target')
    previous=store.db.execute('SELECT result FROM batches WHERE id=? AND run=?',(batch['batchId'],batch['runId'])).fetchone()
    if previous:
        recorded=store.db.execute('SELECT fingerprint FROM batch_inputs WHERE id=?',(batch['batchId'],)).fetchone()
        require(not recorded or recorded[0]==digest(batch),'batch payload changed')
        return json.loads(previous[0])
    require(run['state']=='active','run not active')
    store.validate_messages(batch)
    started=time.perf_counter(); decisions={}; uncached=[]; cache_keys={}
    # Full page context is included in the key: changed neighbors re-evaluate short replies.
    page_context=digest([context,[(m.get('originId') or m.get('occurrenceKey'),fingerprint(m)) for m in batch['messages']]])
    for i,m in enumerate(batch['messages']):
        mid=digest([batch['targetId'],m.get('originId') or m.get('occurrenceKey')])
        key=digest([mid,fingerprint(m),provider.name,provider.model,RULE_VERSION,page_context])
        cache_keys[i]=key
        row=store.db.execute('SELECT decision FROM selection_cache WHERE id=?',(key,)).fetchone()
        if row: decisions[i]=json.loads(row[0])
        else: uncached.append(i)
    api_start=time.perf_counter()
    if uncached:
        decisions.update(provider.classify_page(batch['messages'],uncached,context))
    api_ms=(time.perf_counter()-api_start)*1000
    require(set(decisions)==set(range(len(batch['messages']))),'incomplete page decisions')
    keep=set()
    from datetime import datetime
    for i,d in decisions.items():
        # Relevance is a separate binary criterion; class confidence is not relevance.
        if d.get('relevance',1)>RELEVANCE_FLOOR: keep.add(i)
        # High-recall guard for dates/deadlines and explicit changes; never a keyword-only reject.
        if re.search(r'(\d+\s*(?:시|시간|분|월|일|주)|오늘|내일|모레|이번\s*주|다음\s*주|요일|취소|불참|참석|참여|연기|확정|예약|일정|약속)',batch['messages'][i]['text']): keep.add(i)
        # Short invitations can have no date and be misclassified as casual chatter.
        # Preserve explicit join cues without treating them as confirmed future events.
        if re.search(r'(?:디코|디스코드|음성|보이스|회의|게임|모임).{0,20}(?:ㄱㄱ|들어|오세|와요|오실|합류)|(?:들어오세요|들어와요|합류해)',batch['messages'][i]['text']): keep.add(i)
        if d.get('relevance',1)>=.6:
            for j in [i-1,i+1]:
                if not 0<=j<len(batch['messages']): continue
                left=batch['messages'][i].get('sentAt'); right=batch['messages'][j].get('sentAt')
                # Context around a concrete scheduling message, not an entire day of chatter.
                if not left or not right or abs((datetime.fromisoformat(left)-datetime.fromisoformat(right)).total_seconds())<=600: keep.add(j)
    # Previously retained evidence is never erased by a later classification.
    for i,m in enumerate(batch['messages']):
        if store.db.execute('SELECT 1 FROM messages WHERE id=?',(digest([batch['targetId'],m.get('originId') or m.get('occurrenceKey')]),)).fetchone():keep.add(i)
    metrics={'observed':len(batch['messages']),'retained':len(keep),'discarded':len(batch['messages'])-len(keep),'apiCalls':int(bool(uncached)),'cacheHits':len(decisions)-len(uncached),'apiMs':round(api_ms,2),'classifyMs':round((time.perf_counter()-started)*1000,2)}
    return store.ingest(batch, selection={'keep':keep,'decisions':decisions,'keys':cache_keys,'metrics':metrics})
