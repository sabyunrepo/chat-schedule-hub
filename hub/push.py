"""Bounded Web Push delivery. Never logs subscriptions, payloads or credentials."""
import base64
import json
from urllib.parse import urlsplit
from .sources.mail_calendar import secret, private_write


def allowed_endpoint(endpoint):
    u = urlsplit(endpoint)
    h = u.hostname or ''
    return u.scheme == 'https' and not u.username and not u.password and not u.port and not u.fragment and (
        h in ('fcm.googleapis.com', 'web.push.apple.com', 'updates.push.services.mozilla.com') or
        any(h.endswith(s) for s in ('.push.apple.com', '.push.services.mozilla.com', '.notify.windows.com')))


def public_key(root, create=False):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    path = root / 'push-vapid.key'
    if not path.exists() and create:
        key = ec.generate_private_key(ec.SECP256R1())
        private_write(path, key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode())
    key = serialization.load_pem_private_key(secret(path).encode(), password=None)
    return base64.urlsafe_b64encode(key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)).decode().rstrip('=')


def cycle(root, origin, site_token):
    import requests
    from pywebpush import webpush, WebPushException
    class NoRedirects(requests.Session):
        def request(self, method, url, **kwargs):
            if not allowed_endpoint(url):
                raise ValueError('unsupported_push_service')
            kwargs['allow_redirects'] = False
            return super().request(method, url, **kwargs)
    headers={'Authorization':'Bearer '+secret(root/'site-sync.key'),
             'OAI-Sites-Authorization':'Bearer '+site_token}
    def request(payload):
        r=requests.post(origin+'/api/push/dispatch',json=payload,headers=headers,timeout=30,allow_redirects=False)
        if r.status_code!=200:raise RuntimeError('push_dispatch_failed')
        return r.json()
    if not request({'action':'configure','publicKey':public_key(root)}).get('ok'):
        raise RuntimeError('push_key_mismatch')
    jobs=request({'action':'poll'})['jobs']
    if not isinstance(jobs,list) or len(jobs)>20:raise ValueError('push_budget_exceeded')
    report={'claimed':len(jobs),'sent':0,'retry':0,'gone':0}
    with NoRedirects() as session:
        for job in jobs:
            result='retry'
            try:
                if not allowed_endpoint(job['info']['endpoint']):raise ValueError('unsupported_push_service')
                response=webpush(job['info'],data='{}',vapid_private_key=str(root/'push-vapid.key'),
                    vapid_claims={'sub':origin},timeout=10,ttl=900,requests_session=session,
                    headers={'Topic':'moa-schedule-update'})
                if response.status_code in (200,201,202):result='sent'
            except WebPushException as exc:
                if exc.response is not None and exc.response.status_code in (404,410):result='gone'
            except Exception:
                pass
            request({'action':'ack','subscription':job['subscription'],'item':job['item'],'lease':job['lease'],'result':result})
            report[result]+=1
    return report
