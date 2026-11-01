"""Transactional storage and host-driven, resumable collection protocol."""
import hashlib, json, sqlite3, uuid
from datetime import datetime, timezone
from pathlib import Path


def now(): return datetime.now(timezone.utc).isoformat()
def digest(value): return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
def require(ok, message):
    if not ok: raise ValueError(message)

def message_fingerprint(message):
    # Reply/provenance changes can change the meaning of identical short text.
    fields={k:message.get(k) for k in ['text','authorRef','sentAt','attachments','observationKind',
        'replyToRef','threadRef','sourceLocator','editedAt','timestampPrecision','provenance']}
    if 'structuredPayload' in message: fields['structuredPayload']=message['structuredPayload']
    return digest(fields)


class SourceRegistry:
    def __init__(self): self.adapters = {}
    def register(self, spec):
        require(spec['id'] not in self.adapters, 'duplicate adapter')
        require(spec['contractVersion'] == 1, 'unsupported contract')
        self.adapters[spec['id']] = spec
    def get(self, key): return self.adapters[key]


REGISTRY = SourceRegistry()
for key, label, transport in [('kakao-mac', '카카오톡', 'native-ui'), ('discord-web', 'Discord 웹', 'browser-ui'), ('fixture', '합성 검증', 'file-import')]:
    REGISTRY.register(dict(id=key, label=label, transport=transport, contractVersion=1,
        adapterVersion='0.1.0', driver='host-observation' if key != 'fixture' else 'fixture',
        capabilities=dict(history=True, resume='observed-anchor', edits='observed-only', deletions='explicit-only', threads='separate-target', attachments='metadata-only')))


REGISTRY.register(dict(id='discord-bot', label='Discord 봇', transport='official-api',
    contractVersion=1, adapterVersion='0.2.0', driver='discord.py-gateway',
    capabilities=dict(history='bounded-page', resume='gateway-resume-and-bounded-repair', edits='raw-event-refetch',
                      deletions='explicit-only', threads='active-and-explicit-target', attachments='metadata-only')))


for key, label, transport in [('gmail-api', 'Gmail', 'official-api'), ('naver-imap', '네이버 메일', 'official-protocol'), ('google-calendar-api', 'Google Calendar', 'official-api')]:
    REGISTRY.register(dict(id=key, label=label, transport=transport, contractVersion=1,
        adapterVersion='0.1.0', driver='read-only-bounded-pilot',
        capabilities=dict(history='bounded-inbox-pilot', resume='pilot-replay-only',
                          edits='observed-only' if key == 'google-calendar-api' else 'unsupported', deletions='unsupported', threads='metadata-only', attachments='metadata-only')))
REGISTRY.adapters['google-calendar-api']['capabilities']['history']='bounded-calendar-pilot'


class Store:
    def __init__(self, path):
        if str(path) != ':memory:':
            Path(path).parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS batch_inputs(id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS selection_cache(id TEXT PRIMARY KEY, decision TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS observations(id TEXT PRIMARY KEY, target TEXT NOT NULL, fingerprint TEXT NOT NULL, retained INTEGER NOT NULL, observed TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS targets(id TEXT PRIMARY KEY, adapter TEXT NOT NULL, connection TEXT NOT NULL, label TEXT NOT NULL, config TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY, target TEXT NOT NULL REFERENCES targets(id), identity TEXT NOT NULL, fingerprint TEXT NOT NULL, payload TEXT NOT NULL, observed TEXT NOT NULL, UNIQUE(target,identity));
        CREATE TABLE IF NOT EXISTS revisions(id TEXT PRIMARY KEY, message TEXT NOT NULL REFERENCES messages(id), fingerprint TEXT NOT NULL, payload TEXT NOT NULL, observed TEXT NOT NULL, UNIQUE(message,fingerprint));
        CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, revision TEXT NOT NULL REFERENCES revisions(id), state TEXT NOT NULL DEFAULT 'pending', result TEXT, error TEXT, UNIQUE(revision));
        CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, target TEXT NOT NULL REFERENCES targets(id), state TEXT NOT NULL, cursor TEXT NOT NULL, baseline TEXT NOT NULL, seen TEXT NOT NULL, reason TEXT, started TEXT NOT NULL, updated TEXT NOT NULL);
        CREATE UNIQUE INDEX IF NOT EXISTS one_active ON runs(target) WHERE state='active';
        CREATE TABLE IF NOT EXISTS boundaries(target TEXT PRIMARY KEY REFERENCES targets(id), anchors TEXT NOT NULL, updated TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS boundary_policies(target TEXT PRIMARY KEY REFERENCES targets(id), version INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS batches(id TEXT PRIMARY KEY, run TEXT NOT NULL REFERENCES runs(id), result TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, version INTEGER NOT NULL, payload TEXT NOT NULL, updated TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS changes(id TEXT PRIMARY KEY, event TEXT NOT NULL REFERENCES events(id), payload TEXT NOT NULL, created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS event_evidence_links(event TEXT NOT NULL, revision TEXT NOT NULL, label TEXT NOT NULL, PRIMARY KEY(event,revision));
        CREATE TABLE IF NOT EXISTS source_event_policy(target TEXT PRIMARY KEY, excluded INTEGER NOT NULL, reason TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS people(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS outbox(id INTEGER PRIMARY KEY AUTOINCREMENT, event TEXT NOT NULL, version INTEGER NOT NULL, payload TEXT NOT NULL, sent INTEGER NOT NULL DEFAULT 0, UNIQUE(event,version));
        CREATE INDEX IF NOT EXISTS message_target ON messages(target,observed,id);
        CREATE INDEX IF NOT EXISTS pending_jobs ON jobs(state,id);
        CREATE INDEX IF NOT EXISTS pending_outbox ON outbox(sent,id);
        CREATE INDEX IF NOT EXISTS batches_run ON batches(run);
        ''')
    def register_target(self, target, adapter, connection, label, config):
        REGISTRY.get(adapter)
        require(config.get('since') and config.get('until'), 'explicit collection range required')
        existing = self.db.execute('SELECT adapter,connection FROM targets WHERE id=?',(target,)).fetchone()
        require(not existing or (existing['adapter']==adapter and existing['connection']==connection),'target identity changed')
        with self.db: self.db.execute('INSERT INTO targets VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET label=excluded.label,config=excluded.config',(target,adapter,connection,label,json.dumps(config)))
    def begin(self, target, restart=False):
        t=self.db.execute('SELECT * FROM targets WHERE id=?',(target,)).fetchone()
        require(t is not None,'unknown target')
        active=self.db.execute("SELECT * FROM runs WHERE target=? AND state='active'",(target,)).fetchone()
        if active and not restart: return dict(active)
        if active:
            with self.db: self.db.execute("UPDATE runs SET state='superseded',reason='retention-policy-changed',updated=? WHERE id=?",(now(),active['id']))
        boundary=self.db.execute('SELECT anchors FROM boundaries WHERE target=?',(target,)).fetchone()
        from .selection import COMPATIBLE_RULE_VERSIONS
        policy=self.db.execute('SELECT version FROM boundary_policies WHERE target=?',(target,)).fetchone()
        # Unknown/older selection policies may have discarded newly valuable evidence.
        if restart or not policy or policy[0] not in (0,*COMPATIBLE_RULE_VERSIONS): boundary=None
        rid=str(uuid.uuid4()); stamp=now()
        with self.db: self.db.execute('INSERT INTO runs VALUES(?,?,?,?,?,?,?,?,?)',(rid,target,'active','{}',boundary[0] if boundary else '[]','[]',None,stamp,stamp))
        return dict(self.db.execute('SELECT * FROM runs WHERE id=?',(rid,)).fetchone())
    def validate_messages(self, batch):
        from datetime import datetime
        target=self.db.execute('SELECT config FROM targets WHERE id=?',(batch['targetId'],)).fetchone()
        require(target,'unknown target')
        config=json.loads(target[0])
        for i,m in enumerate(batch['messages']):
            require(isinstance(m.get('text'),str) and len(m['text'])<=100000,'invalid message')
            require(m.get('observedAt'),'observation time required')
            require(m.get('originId') or (m.get('occurrenceKey') and m.get('identityQuality')=='verified-anchor'),'ambiguous identity')
            if m.get('sentAt'): require(datetime.fromisoformat(config['since'])<=datetime.fromisoformat(m['sentAt'])<=datetime.fromisoformat(config['until']),'outside selected range')

    def ingest(self, batch, selection=None):
        """UI host supplies an observed page, never a hidden service API response."""
        require(batch.get('schemaVersion')==1,'unsupported batch schema')
        previous=self.db.execute('SELECT result FROM batches WHERE id=?',(batch['batchId'],)).fetchone()
        if previous:
            recorded=self.db.execute('SELECT fingerprint FROM batch_inputs WHERE id=?',(batch['batchId'],)).fetchone()
            require(not recorded or recorded[0]==digest(batch),'batch payload changed')
            original=self.db.execute('SELECT run FROM batches WHERE id=?',(batch['batchId'],)).fetchone()[0]
            require(original==batch['runId'],'batch id collision')
            return json.loads(previous[0])
        run=self.db.execute('SELECT * FROM runs WHERE id=?',(batch['runId'],)).fetchone()
        require(run is not None and run['state']=='active','run not active')
        require(batch['targetId']==run['target'],'wrong target')
        require(batch.get('verifiedTarget') is True,'host must verify focused target')
        require(len(batch['messages'])<=500,'page too large')
        target=self.db.execute('SELECT * FROM targets WHERE id=?',(run['target'],)).fetchone()
        config=json.loads(target['config'])
        seen=json.loads(run['seen']); baseline=json.loads(run['baseline']); identities=[]; new=0; changed=0
        with self.db:
            for i,m in enumerate(batch['messages']):
                require(isinstance(m.get('text'),str) and len(m['text'])<=100000,'invalid message')
                require(m.get('observedAt'),'observation time required')
                # Host must preserve a verified occurrence key for messages without native IDs.
                identity=m.get('originId') or m.get('occurrenceKey')
                require(identity and (m.get('originId') or m.get('identityQuality')=='verified-anchor'),'ambiguous identity: keep unresolved, do not merge')
                if m.get('sentAt'):
                    require(datetime.fromisoformat(config['since'])<=datetime.fromisoformat(m['sentAt'])<=datetime.fromisoformat(config['until']), 'outside selected range')
                fingerprint=message_fingerprint(m)
                mid=digest([run['target'],identity]); rid=digest([mid,fingerprint]); identities.append(mid)
                if selection is not None:
                    retain=i in selection['keep']
                    self.db.execute('INSERT OR REPLACE INTO observations VALUES(?,?,?,?,?)',(mid,run['target'],fingerprint,int(retain),m['observedAt']))
                    self.db.execute('INSERT OR REPLACE INTO selection_cache VALUES(?,?)',(selection['keys'][i],json.dumps(selection['decisions'][i])))
                    if not retain: continue
                old=self.db.execute('SELECT fingerprint FROM messages WHERE id=?',(mid,)).fetchone()
                if old and old[0]==fingerprint: continue
                payload=json.dumps(m,ensure_ascii=False)
                self.db.execute('INSERT INTO messages VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET fingerprint=excluded.fingerprint,payload=excluded.payload,observed=excluded.observed',(mid,run['target'],identity,fingerprint,payload,m['observedAt']))
                self.db.execute('INSERT OR IGNORE INTO revisions VALUES(?,?,?,?,?)',(rid,mid,fingerprint,payload,m['observedAt']))
                self.db.execute('INSERT OR IGNORE INTO jobs(id,revision) VALUES(?,?)',(rid,rid))
                if selection is not None:
                    self.db.execute('UPDATE jobs SET result=? WHERE id=?',(json.dumps(selection['decisions'][i]),rid))
                new+=int(old is None); changed+=int(old is not None)
            # Require three consecutive anchors, not a single repeated word or timestamp.
            boundary=False
            live = batch.get('mode') == 'live'
            require(not live or target['adapter'] == 'discord-bot', 'live mode requires Discord bot')
            if not live and len(baseline)>=3:
                for i in range(len(identities)-2):
                    if any(identities[i:i+3]==baseline[j:j+3] for j in range(len(baseline)-2)): boundary=True
            reason=batch.get('stopReason','continue')
            require(reason in ['continue','requested-range-reached','explicit-source-end','budget-exhausted','cancelled','retryable-error','access-blocked','anchor-lost'],'invalid stop reason')
            if boundary: reason='known-boundary'
            complete=reason in ['known-boundary','requested-range-reached','explicit-source-end']
            require(not live or not complete, 'live events cannot complete history')
            require(not complete or batch.get('coverageVerified') is True,'coverage evidence required')
            if not seen: seen=identities[:12]
            # Partial runs remain active: a later begin resumes rather than skipping the gap.
            if not live:
                self.db.execute('UPDATE runs SET state=?,cursor=?,seen=?,reason=?,updated=? WHERE id=?',('complete' if complete else 'active',json.dumps(batch.get('cursor',{})),json.dumps(seen),reason,now(),run['id']))
            if complete:
                self.db.execute('INSERT INTO boundaries VALUES(?,?,?) ON CONFLICT(target) DO UPDATE SET anchors=excluded.anchors,updated=excluded.updated',(run['target'],json.dumps(seen or baseline),now()))
                self.db.execute('INSERT OR REPLACE INTO boundary_policies VALUES(?,?)',(run['target'],selection['metrics']['ruleVersion'] if selection else 0))
            result=dict(new=new,changed=changed,stopReason=reason,complete=complete,runId=run['id'])
            if selection is not None: result['selection']=selection['metrics']
            self.db.execute('INSERT INTO batches VALUES(?,?,?)',(batch['batchId'],run['id'],json.dumps(result)))
            self.db.execute('INSERT INTO batch_inputs VALUES(?,?)',(batch['batchId'],digest(batch)))
        return result
    def pending(self, limit=50):
        rows=self.db.execute("SELECT j.id,j.result,r.payload,m.target FROM jobs j JOIN revisions r ON j.revision=r.id JOIN messages m ON r.message=m.id WHERE j.state IN ('pending','failed') ORDER BY r.observed,j.id LIMIT ?",(min(limit,100),)).fetchall()
        return [dict(id=r['id'],target=r['target'],message=json.loads(r['payload']),decision=json.loads(r['result']) if r['result'] else None) for r in rows]
    def apply_event(self, command):
        require(command['operationId'] and command['evidence'],'event evidence required')
        previous=self.db.execute('SELECT id FROM changes WHERE id=?',(command['operationId'],)).fetchone()
        if previous: return {'duplicate':True}
        for evidence in command['evidence']:
            require(self.db.execute('SELECT id FROM revisions WHERE id=?',(evidence,)).fetchone(),'unknown evidence revision')
        eid=command['eventId']; old=self.db.execute('SELECT * FROM events WHERE id=?',(eid,)).fetchone()
        require(command.get('expectedVersion',0)==(old['version'] if old else 0),'event version conflict')
        event=command['event']; require(event['status'] in ['proposed','confirmed','cancelled','completed'],'invalid status')
        require(event['kind'] in ['work','crime','personal'],'invalid kind')
        require(event.get('title') and isinstance(event.get('participants'),list),'invalid event')
        if event.get('end'):
            require(event.get('start') and datetime.fromisoformat(event['end'])>=datetime.fromisoformat(event['start']),'invalid interval')
        for person in event['participants']: require(self.db.execute('SELECT id FROM people WHERE id=?',(person,)).fetchone(),'unknown person')
        v=(old['version'] if old else 0)+1
        event={**event,'id':eid,'version':v,'evidence':command['evidence'],'updatedAt':now()}
        with self.db:
            self.db.execute('INSERT INTO events VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET version=excluded.version,payload=excluded.payload,updated=excluded.updated',(eid,v,json.dumps(event,ensure_ascii=False),now()))
            self.db.execute('INSERT INTO changes VALUES(?,?,?,?)',(command['operationId'],eid,json.dumps({'before':json.loads(old['payload']) if old else None,'after':event},ensure_ascii=False),now()))
            self.db.execute('INSERT INTO outbox(event,version,payload) VALUES(?,?,?)',(eid,v,json.dumps(event,ensure_ascii=False)))
        return event
    def snapshot(self):
        events=[json.loads(r[0]) for r in self.db.execute('SELECT payload FROM events')]
        excluded={r[0] for r in self.db.execute('SELECT r.id FROM revisions r JOIN messages m ON r.message=m.id JOIN source_event_policy p ON p.target=m.target WHERE p.excluded=1')}
        links={}
        for row in self.db.execute('SELECT event,revision,label FROM event_evidence_links'):
            links.setdefault(row[0],[]).append((row[1],row[2]))
        for event in events:
            extra=links.get(event['id'],[])
            if extra:
                event['evidence']=list(dict.fromkeys(event.get('evidence',[])+[x[0] for x in extra]))[-30:]
                event['source']=' · '.join(dict.fromkeys([event.get('source','일정')]+[x[1] for x in extra]))
            if any(ref in excluded for ref in event.get('evidence',[])): event['excluded']=True
        sources=[dict(r) for r in self.db.execute('SELECT t.id,t.label,t.adapter,r.reason,r.updated FROM targets t LEFT JOIN runs r ON r.id=(SELECT id FROM runs WHERE target=t.id ORDER BY started DESC LIMIT 1)')]
        blocked={r[0] for r in self.db.execute('SELECT target FROM source_event_policy WHERE excluded=1')}
        for source in sources:
            if source['id'] in blocked:source['reason']='excluded-by-user'
        return dict(schemaVersion=1,events=events,people=[json.loads(r[0]) for r in self.db.execute('SELECT payload FROM people')],sources=sources,generatedAt=now())
