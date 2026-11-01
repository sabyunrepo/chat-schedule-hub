import json, os, urllib.request
from urllib.parse import urlparse

def sync(store, config):
    origin=config['origin'].rstrip('/')
    u=urlparse(origin)
    if u.scheme!='https' or u.username or u.password or u.path not in ['', '/'] or u.query or u.fragment: raise ValueError('HTTPS origin required')
    token=os.environ.get('HUB_SYNC_TOKEN'); site_token=os.environ.get('HUB_SITE_ACCESS_TOKEN')
    if not token or not site_token: raise ValueError('HUB_SYNC_TOKEN and HUB_SITE_ACCESS_TOKEN required')
    snapshot=store.snapshot(); snapshot['installationId']=config['installationId']; snapshot['sequence']=config['sequence']
    payload=json.dumps(snapshot,ensure_ascii=False).encode()
    if len(payload)>900000: raise ValueError('Snapshot too large: narrow sync scope')
    headers={'Content-Type':'application/json','Authorization':'Bearer '+token,'OAI-Sites-Authorization':'Bearer '+site_token}
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs): return None
    req=urllib.request.Request(origin+'/api/sync',data=payload,headers=headers)
    with urllib.request.build_opener(NoRedirect).open(req,timeout=30) as response: result=json.load(response)
    # Only mark exact exported versions; later revisions remain queued.
    with store.db:
        for event in snapshot['events']: store.db.execute('UPDATE outbox SET sent=1 WHERE event=? AND version<=?',(event['id'],event['version']))
    return result
