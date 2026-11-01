import unittest
from hub.core import Store
from hub.sources.mail_incremental import gmail_collect
from tests.test_mail_calendar import Provider

class GmailTests(unittest.TestCase):
 def test_cursor_failure_and_page_resume(self):
  class API:
   calls=[];fail=False
   def profile(self):return {'emailAddress':'test@example.com'}
   def get(self,service,route,params):
    self.calls.append(params)
    if self.fail:raise RuntimeError('network')
    return {'messages':[],**({} if params.get('pageToken') else {'nextPageToken':'second'})}
  s=Store(':memory:');api=API()
  self.assertTrue(gmail_collect(s,api,Provider())['hasMore'])
  before=s.db.execute('SELECT payload FROM mail_cursors').fetchone()[0]
  api.fail=True
  with self.assertRaises(RuntimeError):gmail_collect(s,api,Provider())
  self.assertEqual(s.db.execute('SELECT payload FROM mail_cursors').fetchone()[0],before)
  api.fail=False;self.assertFalse(gmail_collect(s,api,Provider())['hasMore']);self.assertEqual(api.calls[-1]['pageToken'],'second')
