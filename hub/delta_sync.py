"""Durable per-destination delta delivery. No deletion by absence."""
import json
import urllib.request
import uuid
from urllib.parse import urlparse
from .core import digest


def prepare(store, origin):
    db=store.db
    db.executescript('''CREATE TABLE IF NOT EXISTS sync_delivery(origin TEXT PRIMARY KEY, installation TEXT NOT NULL, sequence INTEGER NOT NULL, pending TEXT);
    CREATE TABLE IF NOT EXISTS sync_fingerprints(origin TEXT NOT NULL,kind TEXT NOT NULL,id TEXT NOT NULL,hash TEXT NOT NULL,PRIMARY KEY(origin,kind,id));''')
    with db:db.execute('INSERT OR IGNORE INTO sync_delivery VALUES(?,?,0,NULL)',(origin,str(uuid.uuid4())))
    state=db.execute('SELECT * FROM sync_delivery WHERE origin=?',(origin,)).fetchone()
    if state['pending']:return json.loads(state['pending'])
    snapshot=store.snapshot();records=[]
    fingerprints={(r['kind'],r['id']):r['hash'] for r in db.execute('SELECT kind,id,hash FROM sync_fingerprints WHERE origin=?',(origin,))}
    for kind,plural in [('person','people'),('event','events'),('source','sources')]:
        for value in snapshot[plural]:
            old=fingerprints.get((kind,value['id']))
            if old!=digest(value): records.append({'kind':kind,'value':value})
            if len(records)==200:break
        if len(records)==200:break
    if not records:return None
    batch=dict(schemaVersion=2,installationId=state['installation'],sequence=state['sequence']+1,records=records)
    # Persist the exact retry body before any network request.
    with db:db.execute('UPDATE sync_delivery SET pending=? WHERE origin=? AND pending IS NULL',(json.dumps(batch,ensure_ascii=False),origin))
    return json.loads(db.execute('SELECT pending FROM sync_delivery WHERE origin=?',(origin,)).fetchone()[0])


def acknowledge(store,origin,batch,result):
    if result.get('ok') is not True or result.get('sequence')!=batch['sequence']:raise ValueError('delta not acknowledged')
    db=store.db
    with db:
        current=db.execute('SELECT pending FROM sync_delivery WHERE origin=?',(origin,)).fetchone()
        if not current or not current[0]:return
        if json.loads(current[0])!=batch:raise ValueError('pending delta changed')
        for record in batch['records']:
            value=record['value'];db.execute('INSERT INTO sync_fingerprints VALUES(?,?,?,?) ON CONFLICT(origin,kind,id) DO UPDATE SET hash=excluded.hash',(origin,record['kind'],value['id'],digest(value)))
            if record['kind']=='event':db.execute('UPDATE outbox SET sent=1 WHERE event=? AND version<=?',(value['id'],value['version']))
        db.execute('UPDATE sync_delivery SET sequence=?,pending=NULL WHERE origin=?',(batch['sequence'],origin))


def deliver(store,origin,token,site_token,send=None):
    origin=origin.rstrip('/');u=urlparse(origin)
    if u.scheme!='https' or u.username or u.password or u.path or u.query or u.fragment:raise ValueError('HTTPS origin required')
    if not token or not site_token:raise ValueError('both authentication tokens required')
    batches=records=0
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):return None
    while batches<100:
        batch=prepare(store,origin)
        if batch is None:return {'ok':True,'batches':batches,'records':records}
        payload=json.dumps(batch,ensure_ascii=False).encode()
        if len(payload)>900000:raise ValueError('delta exceeds request budget')
        if send:result=send(batch)
        else:
            req=urllib.request.Request(origin+'/api/sync',data=payload,headers={'Content-Type':'application/json','Authorization':'Bearer '+token,'OAI-Sites-Authorization':'Bearer '+site_token})
            with urllib.request.build_opener(NoRedirect).open(req,timeout=30) as response:result=json.load(response)
        acknowledge(store,origin,batch,result);batches+=1;records+=len(batch['records'])
    raise ValueError('delivery budget exhausted; pending records retained')
