"""Bounded read-only Google Calendar pilot into the common event/outbox store."""
import argparse
import json
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
from ..core import Store, digest, now, message_fingerprint, require
from .mail_calendar import ROOT, GoogleReadOnly, private_write


def normalize_event(raw, calendar_id, kind='personal'):
    require(kind in ('personal','crime','work'), 'invalid calendar category')
    require(raw.get('id') and raw.get('start') and raw.get('end'), 'partial calendar event')
    start=raw['start'].get('dateTime') or raw['start'].get('date')
    end=raw['end'].get('dateTime') or raw['end'].get('date')
    require(start and end, 'missing event interval')
    status={'confirmed':'confirmed','tentative':'proposed','cancelled':'cancelled'}.get(raw.get('status'))
    require(status, 'unsupported calendar status')
    return dict(title=raw.get('summary') or '비공개 일정', start=start,end=end,status=status,kind=kind,
                participants=[],location=raw.get('location'),allDay='date' in raw['start'],
                timezone=raw['start'].get('timeZone'),endExclusive='date' in raw['end'],
                calendarId=calendar_id,sourceEventId=raw['id'],source='google-calendar-api',
                sourceLocator=raw.get('htmlLink'),recurringEventId=raw.get('recurringEventId'),
                originalStartTime=raw.get('originalStartTime'),iCalUID=raw.get('iCalUID'),
                attendees=raw.get('attendees',[]),organizer=raw.get('organizer'))


def collect(store,api,calendar_id,kind='personal',limit=20):
    require(1<=limit<=20,'pilot limit must be 1..20')
    calendars=api.calendars()
    if calendar_id=='primary':
        chosen=next((x for x in calendars if x.get('primary')),None)
    else: chosen=next((x for x in calendars if x['id']==calendar_id),None)
    require(chosen is not None,'calendar outside accessible inventory')
    calendar_id=chosen['id']
    # Account identity is checked by Gmail profile because both read scopes are requested.
    connection=digest(['google',api.profile()['emailAddress']])
    target='google-calendar-api:'+digest([connection,calendar_id])
    stamp=datetime.now(timezone.utc); lower=stamp-timedelta(days=30); upper=stamp+timedelta(days=180)
    page=api.get('calendar','calendars/'+quote(calendar_id,safe='')+'/events',
                 {'timeMin':lower.isoformat(),'timeMax':upper.isoformat(),'maxResults':limit,
                  'singleEvents':'true','orderBy':'startTime','showDeleted':'true'})
    store.register_target(target,'google-calendar-api',connection,chosen.get('summary','Calendar'),
                          {'since':lower.isoformat(),'until':upper.isoformat()})
    run=store.begin(target,restart=True); rows=[]; normalized={}; gaps=[]
    for raw in page.get('items',[]):
        eid=digest([target,raw['id']])
        if raw.get('status')=='cancelled' and (not raw.get('start') or not raw.get('end')):
            old=store.db.execute('SELECT payload FROM events WHERE id=?',(eid,)).fetchone()
            if not old: gaps.append({'id':raw['id'],'reason':'cancellation-without-prior-event'});continue
            event={**json.loads(old[0]),'status':'cancelled'}
            for field in ('id','version','evidence','updatedAt'):event.pop(field,None)
        else: event=normalize_event(raw,calendar_id,kind)
        # Separate structured payload; no invented message timestamp or model extraction.
        m=dict(originId=raw['id'],identityQuality='stable',text=event['title'],sentAt=None,observedAt=now(),
               editedAt=raw.get('updated'),observationKind='observed',provenance='official-api',
               sourceLocator=raw.get('htmlLink'),structuredPayload=event,contentKind='calendar-event')
        rows.append(m);normalized[raw['id']]=(eid,event)
    batch=dict(schemaVersion=1,batchId=str(uuid.uuid4()),runId=run['id'],targetId=target,
               verifiedTarget=True,messages=rows,stopReason='budget-exhausted',coverageVerified=False,
               cursor={'kind':'bounded-calendar-pilot-no-sync-token'})
    result=store.ingest(batch); applied=0
    for m in rows:
        eid,event=normalized[m['originId']]; revision=digest([digest([target,m['originId']]),message_fingerprint(m)])
        operation='calendar:'+revision
        old=store.db.execute('SELECT version FROM events WHERE id=?',(eid,)).fetchone()
        outcome=store.apply_event(dict(operationId=operation,eventId=eid,evidence=[revision],
                                       expectedVersion=old[0] if old else 0,event=event))
        applied+=int(not outcome.get('duplicate',False))
        with store.db:store.db.execute("UPDATE jobs SET state='classified',result=? WHERE id=?",(json.dumps({'provider':'structured-calendar','modelCalls':0}),revision))
    return dict(fetched=len(page.get('items',[])),new=result['new'],changed=result['changed'],
                applied=applied,modelCalls=0,gaps=gaps,hasMore=bool(page.get('nextPageToken')),coverageComplete=False)


def main():
    p=argparse.ArgumentParser();p.add_argument('--calendar',default='primary');p.add_argument('--kind',default='personal',choices=['personal','work','crime']);p.add_argument('--limit',type=int,default=10)
    args=p.parse_args();api=GoogleReadOnly(ROOT/'google-token.json');store=Store(ROOT/'mail-calendar.sqlite');(ROOT/'mail-calendar.sqlite').chmod(0o600)
    report=collect(store,api,args.calendar,args.kind,args.limit)
    report['repeat']=collect(store,api,args.calendar,args.kind,args.limit)
    private_write(ROOT/'calendar-pilot-report.json',json.dumps(report,ensure_ascii=False));print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(json.dumps({'errorType':type(exc).__name__,'error':'Calendar pilot failed; no sync cursor advanced'}));raise SystemExit(1)
