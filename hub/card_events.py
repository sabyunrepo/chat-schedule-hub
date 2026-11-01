"""Conservative extraction of explicit Kakao schedule cards already collected."""
import json
import re
from datetime import datetime,timezone,timedelta
from .core import digest,message_fingerprint

CARD=re.compile(r'(?P<month>\d{1,2})\s+(?P<day>\d{1,2})\s+(?P<title>.+?)\s+(?P<year>20\d{2})년\s*(?P<m>\d{1,2})월\s*(?P<d>\d{1,2})일\s*\([월화수목금토일]\)(?:\s*(?P<ampm>오전|오후)\s*(?P<h>\d{1,2}):(?P<minute>\d{2}))?')

def parse_card(text, kind='personal'):
    match=CARD.search(text.replace('\n',' '))
    if not match:return None
    g=match.groupdict()
    if int(g['month'])!=int(g['m']) or int(g['day'])!=int(g['d']):return None
    title=g['title'].strip();date=f"{g['year']}-{int(g['m']):02}-{int(g['d']):02}"
    try:datetime.fromisoformat(date)
    except ValueError:return None
    start=None
    if g['ampm']:
        h=int(g['h']);minute=int(g['minute'])
        if not 1<=h<=12 or not 0<=minute<60:return None
        start=date+f"T{h%12+(12 if g['ampm']=='오후' else 0):02}:{minute:02}:00+09:00"
    negotiated=bool(re.search(r'일정\s*협의|시간\s*협의|일협|모이면|날짜\s*협의',title))
    status='cancelled' if '일정이 취소되었습니다' in text else 'proposed'
    clean=re.sub(r'\[(?:모집중?|마감|랏\d+)(?:/일정협의)?\]|\((?:모집중?|마감)\)','',title)
    key=re.sub(r'\s+','',clean)
    tail=text.replace('\n',' ')[match.end():]
    location=re.sub(r'참석여부 응답하기|일정 확인하기','',tail).strip(' ~')
    if len(location)>100:location=''
    event=dict(title=title,start=None if negotiated else start,end=None,kind=kind,status=status,
               participants=[],needsReview=True,source='카카오톡 일정 카드',
               description=f'오픈채팅 모집/공지 · 참석 확정 아님. 카드 날짜 {date}'+(' · 일정/시간 협의 중' if negotiated else '')+'\n'+text[:1800])
    if location:event['location']=location
    return (key,date,start),event


def materialize(store, kind='personal'):
    groups={};seen=0
    for row in store.db.execute('SELECT id,target,payload FROM messages'):
        m=json.loads(row['payload']);card=parse_card(m.get('text',''),kind)
        if not card:continue
        seen+=1;key,event=card;identity=(row['target'],*key)
        stamp=m.get('sentAt') or ''
        revision=digest([row['id'],message_fingerprint(m)])
        groups.setdefault(identity,[]).append((stamp,revision,event))
    applied=0
    for key,items in groups.items():
        items.sort(key=lambda x:x[0]);latest=items[-1];event=latest[2]
        # Same-time contradictory cards are review candidates, never silently confirmed.
        evidence=list(dict.fromkeys(x[1] for x in items))[-30:]
        eid='kakao-card:'+digest(key)
        old=store.db.execute('SELECT version,payload FROM events WHERE id=?',(eid,)).fetchone()
        content={**event,'evidence':evidence}
        operation='card-v1:'+digest([eid,content])
        result=store.apply_event(dict(operationId=operation,eventId=eid,expectedVersion=old['version'] if old else 0,evidence=evidence,event=event))
        applied+=int(not result.get('duplicate',False))
    return dict(cards=seen,eventGroups=len(groups),applied=applied,freeTextExtractionComplete=False)
