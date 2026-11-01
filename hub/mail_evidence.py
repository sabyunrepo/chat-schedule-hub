"""Attach explicit Calendar reminder emails to existing, uniquely matched events."""
import json
import re
from datetime import datetime
from .core import digest,message_fingerprint

PATTERN=re.compile(r'^알림: (.+?) - (20\d{2})\. (\d{1,2})\. (\d{1,2})\. \([^)]+\) (오전|오후) (\d{1,2})(?:시(?: (\d{1,2})분)?|:(\d{2})) - .*\(GMT\+9\)')

def reminder_time(subject):
    m=PATTERN.search(subject)
    if not m:return None
    title,y,month,day,ampm,h,minute,colon_minute=m.groups();h=int(h);minute=int(minute or colon_minute or 0)
    if not 1<=h<=12 or not 0<=minute<60:return None
    try:stamp=datetime(int(y),int(month),int(day),h%12+(12 if ampm=='오후' else 0),minute).isoformat()+'+09:00'
    except ValueError:return None
    return title,stamp


def link_reminders(store):
    events=[json.loads(r[0]) for r in store.db.execute("SELECT payload FROM events WHERE json_extract(payload,'$.source')='google-calendar-api'")]
    linked=unmatched=0
    for row in store.db.execute('SELECT id,payload FROM messages'):
        message=json.loads(row['payload']);text=message.get('text','')
        if 'calendar-notification@google.com' not in message.get('authorRef',''):continue
        parsed=reminder_time(text.splitlines()[0] if text else '')
        if not parsed:continue
        title,stamp=parsed
        matches=[e for e in events if e['title']==title and e.get('start') and datetime.fromisoformat(e['start'])==datetime.fromisoformat(stamp)]
        if len(matches)!=1:unmatched+=1;continue
        revision=digest([row['id'],message_fingerprint(message)])
        with store.db:
            result=store.db.execute('INSERT OR IGNORE INTO event_evidence_links VALUES(?,?,?)',(matches[0]['id'],revision,'Gmail'))
            linked+=result.rowcount
    return {'linked':linked,'unmatched':unmatched}
