import unittest
from hub.core import Store,digest,message_fingerprint
from hub.sources.calendar_pilot import collect

class OwnershipTests(unittest.TestCase):
 def test_calendar_pagination_and_owner_retention(self):
  class API:
   def calendars(self):return [{'id':'main','primary':True},{'id':'shared','summary':'Team'}]
   def profile(self):return {'emailAddress':'me@example.com'}
   def get(self,service,route,params):
    n='2' if params.get('pageToken') else '1'
    return {'items':[{'id':'e'+n,'summary':'Meeting','status':'confirmed','start':{'date':'2026-11-02'},'end':{'date':'2026-11-03'}}],**({'nextPageToken':'next'} if n=='1' else {})}
  api=API();s=Store(':memory:')
  report=collect(s,api,'primary',max_pages=2)
  self.assertEqual(report['new'],2);self.assertTrue(report['coverageComplete'])
  pid=s.snapshot()['people'][0]['id'];self.assertTrue(s.snapshot()['people'][0]['isMe'])
  self.assertTrue(all(e['participants']==[pid] for e in s.snapshot()['events']))
  self.assertEqual(collect(s,api,'primary',max_pages=2)['applied'],0)
  for e in s.snapshot()['events']:
   self.assertTrue(e['evidence'])
   self.assertEqual(len(e['evidenceDetails']),1)
   detail=e['evidenceDetails'][0]
   self.assertIn('Google Calendar',detail['source'])
   self.assertIn('Meeting',detail['excerpt'])
   self.assertIn('2026-11-02',detail['excerpt'])
  self.assertFalse(collect(s,api,'shared',max_pages=1)['coverageComplete'])
  self.assertTrue(any(not p['isMe'] for p in s.snapshot()['people']))
 def test_source_exclusion_survives_reprocessing(self):
  s=Store(':memory:');s.register_target('t','kakao-mac','a','Recruitment',{'since':'2026-10-01','until':'2026-11-02'})
  run=s.begin('t');m={'originId':'1','identityQuality':'stable','text':'meeting','observedAt':'2026-11-01T00:00:00Z'}
  s.ingest({'schemaVersion':1,'batchId':'b','runId':run['id'],'targetId':'t','verifiedTarget':True,'messages':[m],'stopReason':'budget-exhausted'})
  rid=digest([digest(['t','1']),message_fingerprint(m)])
  event={'title':'Recruitment','status':'proposed','kind':'crime','participants':[],'start':None,'end':None}
  s.apply_event({'operationId':'op','eventId':'e','evidence':[rid],'event':event})
  with s.db:s.db.execute('INSERT INTO source_event_policy VALUES(?,1,?)',('t','not mine'))
  self.assertTrue(s.snapshot()['events'][0]['excluded'])
  s.apply_event({'operationId':'op2','eventId':'e','expectedVersion':1,'evidence':[rid],'event':{**event,'title':'Changed'}})
  self.assertTrue(s.snapshot()['events'][0]['excluded'])
 def test_mail_clock_formats(self):
  from hub.mail_evidence import reminder_time
  for clock in ('오후 5:30','오후 5시 30분'):
   self.assertEqual(reminder_time('알림: 과제 - 2026. 10. 12. (월) '+clock+' - 오후 6시 (GMT+9)')[1],'2026-10-12T17:30:00+09:00')
  self.assertIsNone(reminder_time('행사 안내 11월'))
