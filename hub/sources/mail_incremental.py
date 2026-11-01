"""Bounded Gmail received-time windows; commit cursor only after selection succeeds."""
import base64
import json
from datetime import datetime,timedelta,timezone
from urllib.parse import quote
from .mail_calendar import normalize_mail,store_mail
from ..core import digest

def gmail_collect(store,api,provider,limit=20):
    if not 1<=limit<=20:raise ValueError('limit 1..20')
    account=api.profile()['emailAddress'];key=digest(['gmail',account])
    store.db.executescript('CREATE TABLE IF NOT EXISTS mail_cursors(id TEXT PRIMARY KEY,payload TEXT NOT NULL); CREATE TABLE IF NOT EXISTS mail_seen(account TEXT NOT NULL,id TEXT NOT NULL,PRIMARY KEY(account,id));')
    old=store.db.execute('SELECT payload FROM mail_cursors WHERE id=?',(key,)).fetchone()
    current=datetime.now(timezone.utc)
    state=json.loads(old[0]) if old else {'since':int((current-timedelta(days=30)).timestamp())}
    lower=state['since'];upper=state.get('until') or int(current.timestamp());token=state.get('page')
    params={'labelIds':'INBOX','q':f'after:{lower-1} before:{upper+1}','maxResults':limit}
    if token:params['pageToken']=token
    try:page=api.get('gmail','messages',params)
    except ValueError as exc:
        if token and 'HTTP 400' in str(exc):
            state.pop('page',None)
            with store.db:store.db.execute('UPDATE mail_cursors SET payload=? WHERE id=?',(json.dumps(state),key))
        raise
    messages=[];ids=[];excluded=0;fetched=0
    for item in page.get('messages',[]):
        if store.db.execute('SELECT 1 FROM mail_seen WHERE account=? AND id=?',(key,item['id'])).fetchone():continue
        raw=api.get('gmail','messages/'+quote(item['id'],safe=''),{'format':'raw'});fetched+=1
        stamp=datetime.fromtimestamp(int(raw['internalDate'])/1000,timezone.utc)
        if not lower<=stamp.timestamp()<=upper:continue
        encoded=raw['raw'];data=base64.urlsafe_b64decode(encoded+'='*(-len(encoded)%4))
        message=normalize_mail(data,raw['id'],stamp.isoformat(),{'service':'gmail','account':account,'threadId':raw['threadId'],'messageId':raw['id']},thread=raw['threadId'])
        ids.append(raw['id'])
        if message:messages.append(message)
        else:excluded+=1
    result=store_mail(store,'gmail-api',account,messages,provider,datetime.fromtimestamp(lower,timezone.utc),datetime.fromtimestamp(upper,timezone.utc)) if messages else None
    next_page=page.get('nextPageToken')
    new={'since':lower,'until':upper,'page':next_page} if next_page else {'since':max(lower,upper-86400)}
    # One-day overlap catches late inbox delivery; mail_seen avoids repeated body/model reads.
    with store.db:
        store.db.executemany('INSERT OR IGNORE INTO mail_seen VALUES(?,?)',[(key,i) for i in ids])
        store.db.execute('INSERT INTO mail_cursors VALUES(?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',(key,json.dumps(new)))
    return {'fetched':fetched,'securityExcluded':excluded,'hasMore':bool(next_page),'result':result,'deletions':'unsupported','lateInboxBeyondOverlap':'not-covered'}


def naver_collect(store,api,provider,limit=5):
    key=digest(['naver',api.username]);current=datetime.now(timezone.utc)
    store.db.execute('CREATE TABLE IF NOT EXISTS mail_cursors(id TEXT PRIMARY KEY,payload TEXT NOT NULL)')
    old=store.db.execute('SELECT payload FROM mail_cursors WHERE id=?',(key,)).fetchone()
    state=json.loads(old[0]) if old else {'since':(current-timedelta(days=30)).isoformat(),'uid':0,'validity':None}
    lower=datetime.fromisoformat(state['since'])
    messages,report=api.page(lower,limit,after_uid=state['uid'],expected_validity=state['validity'])
    result=store_mail(store,'naver-imap',api.username,messages,provider,lower,current) if messages else None
    state.update(uid=report['lastUid'],validity=report['uidValidity'])
    with store.db:store.db.execute('INSERT INTO mail_cursors VALUES(?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',(key,json.dumps(state)))
    return {**report,'result':result}
