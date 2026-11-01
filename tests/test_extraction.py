import unittest
from unittest.mock import Mock
from hub.core import Store
from hub.extraction import process, validate
from tests.test_mail_calendar import Provider
from hub.sources.mail_calendar import store_mail
from datetime import datetime, timezone

class ExtractionTests(unittest.TestCase):
 def fixture(self):
  s=Store(':memory:');t=datetime.now(timezone.utc)
  store_mail(s,'gmail-api','fixture',[{'originId':'1','text':'2026-12-10 14:00 meeting','observedAt':t.isoformat(),'sentAt':t.isoformat()}],Provider(),t,t)
  p=Mock();p.extract.return_value={'action':'candidate','title':'Meeting','start':'2026-12-10T14:00:00+09:00','end':None,'kind':'work','location':None,'reason':'확인 필요','quote':'meeting'}
  return s,p
 def test_repeat_has_no_model_call_or_duplicate(self):
  s,p=self.fixture();self.assertEqual(process(s,p)['applied'],1);self.assertEqual(process(s,p)['modelCalls'],0)
  self.assertEqual(p.extract.call_count,1);e=s.snapshot()['events'][0];self.assertEqual(e['participants'],[]);self.assertTrue(e['needsReview'])
 def test_error_remains_retryable_and_is_bounded(self):
  s,p=self.fixture();p.extract.side_effect=RuntimeError('private provider error')
  for _ in range(3):self.assertEqual(process(s,p)['failed'],1)
  self.assertEqual(process(s,p)['modelCalls'],0);self.assertEqual(len(s.pending()),1)
  self.assertEqual(s.db.execute('SELECT error FROM jobs').fetchone()[0],'RuntimeError')
 def test_ungrounded_quote_is_rejected(self):
  s,p=self.fixture();p.extract.return_value['quote']='invented';self.assertEqual(process(s,p)['failed'],1);self.assertEqual(s.snapshot()['events'],[])
 def test_excluded_room_not_processed(self):
  s,p=self.fixture();target=s.db.execute('SELECT id FROM targets').fetchone()[0]
  with s.db:s.db.execute('INSERT INTO source_event_policy VALUES(?,1,?)',(target,'excluded'))
  self.assertEqual(process(s,p)['modelCalls'],0)
