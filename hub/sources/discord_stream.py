"""Durable ID queue and shared selective ingestion for Discord Gateway events."""
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from ..core import Store, digest, now, require
from ..selection import select_ingest, RULE_VERSION
from ..providers import providers
from .discord_bot import target_id


class Queue:
    def __init__(self, db, guilds):
        self.db = db
        self.guilds = {str(g) for g in guilds}
        db.executescript('''
        CREATE TABLE IF NOT EXISTS discord_queue(
          guild TEXT NOT NULL,channel TEXT NOT NULL,message TEXT NOT NULL,kind TEXT NOT NULL,
          generation INTEGER NOT NULL DEFAULT 1,attempts INTEGER NOT NULL DEFAULT 0,
          due REAL NOT NULL, PRIMARY KEY(guild,channel,message));
        CREATE INDEX IF NOT EXISTS discord_queue_due ON discord_queue(due);
        CREATE TABLE IF NOT EXISTS discord_seen(
          target TEXT NOT NULL,message TEXT NOT NULL,semantic TEXT NOT NULL,decision_key TEXT NOT NULL,
          PRIMARY KEY(target,message));
        CREATE TABLE IF NOT EXISTS discord_dependencies(
          target TEXT NOT NULL,dependency TEXT NOT NULL,message TEXT NOT NULL,
          PRIMARY KEY(target,dependency,message));
        CREATE TABLE IF NOT EXISTS discord_coverage(
          channel TEXT PRIMARY KEY,guild TEXT NOT NULL,cursor TEXT,since TEXT NOT NULL,
          state TEXT NOT NULL,updated TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS discord_gaps(
          channel TEXT NOT NULL,message TEXT NOT NULL,reason TEXT NOT NULL,updated TEXT NOT NULL,
          PRIMARY KEY(channel,message,reason));
        ''')

    def enqueue(self, guild, channel, message, kind='fetch'):
        guild, channel, message = map(str, (guild, channel, message))
        if guild not in self.guilds: return False
        require(channel.isdigit() and message.isdigit() and kind in ('fetch','delete'), 'invalid queue item')
        # A real deletion is terminal; stale create/update events must not resurrect it.
        self.db.execute('''INSERT INTO discord_queue VALUES(?,?,?,?,1,0,?)
          ON CONFLICT(guild,channel,message) DO UPDATE SET
          kind=CASE WHEN discord_queue.kind='delete' THEN 'delete' ELSE excluded.kind END,
          generation=discord_queue.generation+1,attempts=0,due=excluded.due''',
          (guild, channel, message, kind, time.time()))
        return True

    def next(self):
        row = self.db.execute('SELECT * FROM discord_queue WHERE due<=? ORDER BY due LIMIT 1',(time.time(),)).fetchone()
        return dict(row) if row else None

    def ack(self, item):
        self.db.execute('DELETE FROM discord_queue WHERE guild=? AND channel=? AND message=? AND generation=?',
                        (item['guild'],item['channel'],item['message'],item['generation']))

    def fail(self, item, reason):
        with self.db:
            self.gap(item['channel'], item['message'], reason)
            self.db.execute('''UPDATE discord_queue SET attempts=attempts+1,due=?
                WHERE guild=? AND channel=? AND message=? AND generation=?''',
                (time.time()+min(3600, 5*2**min(item['attempts'],10)),
                 item['guild'],item['channel'],item['message'],item['generation']))

    def gap(self, channel, message, reason):
        self.db.execute('INSERT OR REPLACE INTO discord_gaps VALUES(?,?,?,?)',(str(channel),str(message),reason,now()))


def semantic(message):
    return digest({k:message.get(k) for k in ('text','authorRef','sentAt','attachments','replyToRef','threadRef','observationKind')})


def process(dbpath, config, item, observation, context_messages=(), provider=None):
    """Runs off the Gateway event loop; own SQLite connection, bounded plaintext in memory."""
    s = Store(dbpath)
    try:
        q = Queue(s.db, config['guildAllowlist'])
        require(item['guild'] in q.guilds, 'guild outside allowlist')
        target = target_id(config['applicationId'],item['guild'],item['channel'])
        previous = s.db.execute('SELECT * FROM discord_seen WHERE target=? AND message=?',(target,item['message'])).fetchone()
        mid = digest([target,item['message']])
        old = s.db.execute('SELECT payload FROM messages WHERE id=?',(mid,)).fetchone()
        if item['kind']=='delete':
            if not old:
                with s.db:
                    q.gap(item['channel'],item['message'],'explicit-deletion-unretained')
                    s.db.execute('INSERT OR REPLACE INTO discord_seen VALUES(?,?,?,?)',(target,item['message'],'deleted','deleted'))
                    q.ack(item)
                return {'deleted':1,'apiCalls':0}
            observation = {**json.loads(old[0]), 'text':'', 'observedAt':now(), 'observationKind':'explicit-deletion'}
        elif previous and previous['semantic']=='deleted':
            with s.db:q.ack(item)
            return {'duplicate':1,'apiCalls':0}
        require(observation and observation['originId']==item['message'], 'missing full observation')
        fp = semantic(observation)
        provider = provider or providers.create(config.get('provider','openai-decisions'))
        full_context = list(context_messages)
        context_messages = [{k:m.get(k) for k in ('originId','text','sentAt','authorRef','replyToRef','attachments','observationKind')}
                            for m in context_messages]
        context = json.dumps(context_messages,ensure_ascii=False)
        key = digest([fp,context,provider.name,provider.model,RULE_VERSION])
        if previous and previous['decision_key']==key:
            with s.db:q.ack(item)
            return {'duplicate':1,'apiCalls':0}
        stamp = datetime.now(timezone.utc)
        ref = observation.get('replyToRef') or {}
        evidence = [m for m in full_context if ref.get('targetId')==target and m['originId']==ref.get('identity')]
        lower = min([datetime.fromisoformat(m['sentAt']) for m in [observation]+evidence]+[stamp-timedelta(days=30)])
        s.register_target(target,'discord-bot',config['applicationId'],'Discord',{'since':lower.isoformat(),'until':stamp.isoformat()})
        run=s.begin(target)
        prior_policy=s.db.execute("SELECT result FROM batches WHERE run=? AND json_type(result,'$.selection') IS NOT NULL LIMIT 1",(run['id'],)).fetchone()
        if prior_policy and json.loads(prior_policy[0])['selection']['ruleVersion']!=RULE_VERSION:
            run=s.begin(target,restart=True)
        batch={'schemaVersion':1,'batchId':str(uuid.uuid4()),'runId':run['id'],'targetId':target,
               'verifiedTarget':True,'externalProcessingAllowed':True,'mode':'live',
               'messages':evidence+[observation],'stopReason':'continue','coverageVerified':False}
        if item['kind']=='delete':
            decision={'intent':'review','relevance':1,'reason':'explicit-deletion'}
            result=s.ingest(batch,selection={'keep':{0},'decisions':{0:decision},'keys':{0:key},
                'metrics':{'ruleVersion':RULE_VERSION,'apiCalls':0,'retained':1,'evidenceGaps':[]}})
        else:
            result=select_ingest(s,batch,provider,context)
        with s.db:
            s.db.execute('INSERT OR REPLACE INTO discord_seen VALUES(?,?,?,?)',
                         (target,item['message'],'deleted' if item['kind']=='delete' else fp,key))
            s.db.execute('DELETE FROM discord_dependencies WHERE target=? AND message=?',(target,item['message']))
            for m in context_messages:
                s.db.execute('INSERT OR IGNORE INTO discord_dependencies VALUES(?,?,?)',(target,m['originId'],item['message']))
            if previous and previous['semantic']!=fp:
                for dependent in s.db.execute('SELECT message FROM discord_dependencies WHERE target=? AND dependency=?',(target,item['message'])).fetchall():
                    q.enqueue(item['guild'],item['channel'],dependent[0])
            q.ack(item)
        return {'apiCalls':result.get('selection',{}).get('apiCalls',0),'retained':result.get('selection',{}).get('retained',0),
                'changed':result['changed'],'evidenceGapCount':len(result.get('selection',{}).get('evidenceGaps',[]))}
    finally:s.db.close()
