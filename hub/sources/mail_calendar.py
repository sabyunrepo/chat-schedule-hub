"""Read-only connection probes and bounded pilots; no background sync claims."""
import argparse
import base64
import email
import email.policy
import imaplib
import json
import os
import re
import ssl
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
from ..core import Store, digest, now, require
from ..selection import select_ingest

ROOT = Path.home() / 'Library/Application Support/ChatScheduleHub'
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly',
          'https://www.googleapis.com/auth/calendar.events.readonly',
          'https://www.googleapis.com/auth/calendar.calendarlist.readonly']


def secret(path):
    p = Path(path)
    require(p.is_file() and not p.is_symlink() and not p.stat().st_mode & 0o077, 'credential must be an owner-only regular file')
    return p.read_text().strip()


def private_write(path, value):
    p = Path(path); p.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=p.parent)
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(value); f.flush(); os.fsync(f.fileno())
        os.replace(temp, p)
    finally:
        if os.path.exists(temp): os.unlink(temp)


class GoogleReadOnly:
    def __init__(self, token_file):
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request, AuthorizedSession
        self.path = token_file
        self.credentials = Credentials.from_authorized_user_info(json.loads(secret(token_file)))
        if not self.credentials.valid:
            require(bool(self.credentials.refresh_token), 'Google reauthentication required')
            self.credentials.refresh(Request())
            private_write(token_file, self.credentials.to_json())
        self.session = AuthorizedSession(self.credentials)

    def get(self, service, route, params=None):
        bases = {'gmail': 'https://gmail.googleapis.com/gmail/v1/users/me/',
                 'calendar': 'https://www.googleapis.com/calendar/v3/'}
        require(service in bases and not route.startswith('/') and '://' not in route and '..' not in route, 'invalid route')
        r = self.session.get(bases[service] + route, params=params, timeout=30, allow_redirects=False)
        require(r.status_code == 200, f'Google {service} HTTP {r.status_code}')
        require(len(r.content) <= 5_000_000, 'API response exceeds pilot budget')
        return r.json()

    def profile(self):
        return self.get('gmail', 'profile')

    def calendars(self):
        result = []; token = None
        for _ in range(10):
            page = self.get('calendar', 'users/me/calendarList', {'maxResults': 100, **({'pageToken': token} if token else {})})
            result.extend(page.get('items', [])); token = page.get('nextPageToken')
            if not token: return result
        raise ValueError('calendar inventory budget exhausted')


def normalize_mail(raw, origin_id, stamp, locator, *, thread=None):
    require(len(raw) <= 1_000_000, 'mail exceeds pilot size budget')
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    subject = str(msg.get('Subject', ''))
    # Do not send credential/reset/verification content to the model.
    if re.search(r'인증\s*(번호|코드)|비밀번호|보안\s*(경고|코드)|verification\s*code|password|security alert|one.time.pass', subject, re.I):
        return None
    body = msg.get_body(preferencelist=('plain', 'html'))
    text = body.get_content() if body else ''
    if body and body.get_content_type() == 'text/html':
        from html.parser import HTMLParser
        class Plain(HTMLParser):
            def __init__(self): super().__init__(); self.parts=[]; self.hidden=0
            def handle_starttag(self, tag, attrs):
                if tag in ('script','style'): self.hidden+=1
                if tag in ('p','br','div','li'): self.parts.append('\n')
            def handle_endtag(self, tag):
                if tag in ('script','style'): self.hidden=max(0,self.hidden-1)
            def handle_data(self, data):
                if not self.hidden: self.parts.append(data)
        parser=Plain(); parser.feed(text); text=''.join(parser.parts)
    require(len(text) <= 90000, 'mail text exceeds pilot budget')
    return dict(originId=origin_id, identityQuality='stable', text=subject+'\n'+text,
                authorRef=str(msg.get('From','')), authorDisplayName=str(msg.get('From','')),
                sentAt=stamp, observedAt=now(), timestampPrecision='received-time', provenance='official-protocol',
                observationKind='observed', sourceLocator=locator, threadRef=thread,
                attachments=[{'filename': p.get_filename(), 'status':'not-collected'} for p in msg.iter_attachments()])


class NaverReadOnly:
    def __init__(self, username, key_file, factory=imaplib.IMAP4_SSL):
        require(re.fullmatch(r'[A-Za-z0-9_.-]+(?:@naver\.com)?', username), 'invalid Naver account')
        self.username = username.lower().removesuffix('@naver.com')
        self.client = factory('imap.naver.com', 993, ssl_context=ssl.create_default_context(), timeout=25)
        try:
            typ, _ = self.client.login(self.username, secret(key_file))
            require(typ == 'OK', 'Naver authentication failed')
        except Exception:
            self.client.shutdown(); raise

    def close(self):
        try: self.client.logout()
        except (OSError, imaplib.IMAP4.error): pass

    def page(self, since, limit=20):
        require(1 <= limit <= 20, 'pilot limit must be 1..20')
        typ, _ = self.client.select('INBOX', readonly=True)
        require(typ == 'OK', 'INBOX read-only selection failed')
        validity = self.client.response('UIDVALIDITY')[1]
        require(validity and validity[0], 'missing UIDVALIDITY')
        typ, found = self.client.uid('search', None, 'SINCE', since.strftime('%d-%b-%Y'))
        require(typ == 'OK', 'IMAP search failed')
        ids = found[0].split() if found and found[0] else []
        messages=[]; skipped=0
        for uid in ids[-limit:]:
            typ, meta = self.client.uid('fetch', uid, '(UID RFC822.SIZE)')
            require(typ == 'OK', 'IMAP metadata failed')
            size = re.search(rb'RFC822.SIZE (\d+)', b' '.join(x for x in meta if isinstance(x,bytes)))
            require(size and int(size[1]) <= 1_000_000, 'mail exceeds pilot size budget')
            typ, data = self.client.uid('fetch', uid, '(UID INTERNALDATE BODY.PEEK[])')
            require(typ == 'OK', 'IMAP read failed')
            chunks = [x for x in data if isinstance(x, tuple)]
            require(len(chunks)==1, 'missing or ambiguous IMAP body')
            header, raw=chunks[0]
            stamp=re.search(rb'INTERNALDATE "([^"]+)"',header)
            require(stamp, 'missing received date')
            received=datetime.strptime(stamp[1].decode(), '%d-%b-%Y %H:%M:%S %z')
            if received < since: continue
            message=normalize_mail(raw, validity[0].decode()+':'+uid.decode(), received.isoformat(),
                                   {'service':'naver','folder':'INBOX','uid':uid.decode()})
            if message: messages.append(message)
            else: skipped+=1
        return messages, dict(fetched=min(len(ids),limit), matched=len(ids), securityExcluded=skipped,
                              uidValidity=validity[0].decode(), coverageComplete=False)


def store_mail(store, adapter, account, messages, provider, lower, upper):
    connection=digest([adapter,account]); target=adapter+':'+connection+':inbox'
    store.register_target(target, adapter, connection, adapter+' INBOX', {'since':lower.isoformat(),'until':upper.isoformat()})
    run=store.begin(target, restart=True)
    batch=dict(schemaVersion=1,batchId=str(uuid.uuid4()),runId=run['id'],targetId=target,
               verifiedTarget=True,externalProcessingAllowed=True,messages=messages,
               stopReason='budget-exhausted',coverageVerified=False,cursor={'kind':'bounded-pilot-no-sync-cursor'})
    first=select_ingest(store,batch,provider)
    batch['batchId']=str(uuid.uuid4())
    repeat=select_ingest(store,batch,provider)
    return {'result':first,'repeat':repeat,'coverageComplete':False}


def gmail_pilot(store, api, provider, limit):
    upper=datetime.now(timezone.utc); lower=upper-timedelta(days=30)
    account=api.profile()['emailAddress']
    page=api.get('gmail','messages',{'labelIds':'INBOX','q':'after:'+str(int(lower.timestamp())), 'maxResults':limit})
    messages=[]; excluded=0
    for item in page.get('messages',[]):
        raw=api.get('gmail','messages/'+quote(item['id'],safe=''),{'format':'raw'})
        stamp=datetime.fromtimestamp(int(raw['internalDate'])/1000,timezone.utc)
        if not lower<=stamp<=upper: continue
        encoded=raw['raw']; data=base64.urlsafe_b64decode(encoded+'='*(-len(encoded)%4))
        m=normalize_mail(data,raw['id'],stamp.isoformat(),{'service':'gmail','account':account,'threadId':raw['threadId'],'messageId':raw['id']},thread=raw['threadId'])
        if m: m['provenance']='official-api'; messages.append(m)
        else: excluded+=1
    return {**store_mail(store,'gmail-api',account,messages,provider,lower,upper),
            'fetched':len(page.get('messages',[])),'securityExcluded':excluded,'hasMore':bool(page.get('nextPageToken'))}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['google-auth','google-probe','gmail-pilot','naver-probe','naver-pilot'])
    p.add_argument('--client-file',type=Path,default=ROOT/'google-client.json')
    p.add_argument('--token-file',type=Path,default=ROOT/'google-token.json')
    p.add_argument('--key-file',type=Path,default=ROOT/'naver-app.key')
    p.add_argument('--account'); p.add_argument('--limit',type=int,default=10)
    p.add_argument('--allow-external-processing',action='store_true')
    args=p.parse_args(); require(1<=args.limit<=20,'pilot limit must be 1..20')
    if args.command=='google-auth':
        from google_auth_oauthlib.flow import InstalledAppFlow
        config=json.loads(secret(args.client_file)); require('installed' in config,'Desktop OAuth client required')
        flow=InstalledAppFlow.from_client_config(config,SCOPES,autogenerate_code_verifier=True)
        creds=flow.run_local_server(host='127.0.0.1',port=0,open_browser=False,timeout_seconds=600,
                                   authorization_prompt_message='Open this URL in Aside:\n{url}',success_message='Moa 연결 완료. 이 창을 닫아도 됩니다.',access_type='offline',prompt='consent')
        require(set(SCOPES)<=set(creds.granted_scopes or creds.scopes or []),'required read scopes not granted')
        private_write(args.token_file,creds.to_json()); print(json.dumps({'authenticated':True})); return
    if args.command.startswith('google') or args.command.startswith('gmail'):
        api=GoogleReadOnly(args.token_file)
        if args.command=='google-probe':
            profile=api.profile(); calendars=api.calendars()
            private_write(ROOT/'google-calendars.json',json.dumps(calendars,ensure_ascii=False))
            print(json.dumps({'gmail':True,'calendarCount':len(calendars)})); return
    else:
        require(args.account,'explicit account required'); api=NaverReadOnly(args.account,args.key_file)
        if args.command=='naver-probe':
            try:
                typ,_=api.client.select('INBOX',readonly=True); require(typ=='OK','INBOX access failed')
                print(json.dumps({'authenticated':True,'readOnly':True}))
            finally: api.close()
            return
    require(args.allow_external_processing,'external processing must be enabled')
    from ..providers import providers
    store=Store(ROOT/'mail-calendar.sqlite'); (ROOT/'mail-calendar.sqlite').chmod(0o600)
    provider=providers.create('openai-decisions')
    if args.command=='gmail-pilot': report=gmail_pilot(store,api,provider,args.limit)
    else:
        upper=datetime.now(timezone.utc); lower=upper-timedelta(days=30)
        try: messages,report=api.page(lower,args.limit)
        finally: api.close()
        report.update(store_mail(store,'naver-imap',api.username,messages,provider,lower,upper))
    private_write(ROOT/(args.command+'-report.json'),json.dumps(report,ensure_ascii=False))
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':
    try: main()
    except Exception as exc:
        # Never print provider responses, credentials, email contents or OAuth callback URLs.
        print(json.dumps({'errorType':type(exc).__name__,'error':'Connection or collection failed; cursor not advanced'}))
        raise SystemExit(1)
