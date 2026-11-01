import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from hub.core import Store
from hub.sources.mail_calendar import normalize_mail, private_write, secret, store_mail, NaverReadOnly

class Provider:
    name='test'; model='test'
    def classify_page(self,messages,indices,context):
        return {i:{'relevance':1,'intent':'schedule','confidence':1} for i in indices}

class MailTests(unittest.TestCase):
    def test_security_mail_excluded(self):
        self.assertIsNone(normalize_mail(b'Subject: Password reset\r\n\r\nsecret', '1','2026-11-01T00:00:00+00:00',{}))
    def test_html_no_remote_fetch(self):
        m=normalize_mail(b'Subject: meeting\r\nContent-Type: text/html\r\n\r\n<p>Meet tomorrow</p><script>secret</script><img src="https://x">','1','2026-11-01T00:00:00+00:00',{})
        self.assertIn('Meet tomorrow',m['text']);self.assertNotIn('secret',m['text']);self.assertNotIn('https://x',m['text'])
    def test_private_storage(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'key';private_write(p,'test');self.assertEqual(secret(p),'test');p.chmod(0o644)
            with self.assertRaises(ValueError):secret(p)
    def test_replay_and_account_isolation(self):
        store=Store(':memory:'); stamp=datetime(2026,11,1,tzinfo=timezone.utc)
        m=normalize_mail(b'Subject: meeting\r\n\r\nTomorrow at 3', '1',stamp.isoformat(),{})
        r=store_mail(store,'naver-imap','one',[m],Provider(),stamp,stamp)
        self.assertEqual(r['result']['new'],1);self.assertEqual(r['repeat']['new'],0)
        self.assertEqual(r['repeat']['selection']['apiCalls'],0)
        self.assertEqual(store_mail(store,'naver-imap','two',[m],Provider(),stamp,stamp)['result']['new'],1)
    def test_readonly_imap(self):
        class Fake:
            def select(self,folder,readonly): self.readonly=readonly; return 'OK',[]
            def response(self,key): return key,[b'12']
            def uid(self,cmd,*args):
                if cmd=='search':return 'OK',[b'1']
                if args[1]=='(UID RFC822.SIZE)':return 'OK',[b'1 (UID 1 RFC822.SIZE 64)']
                assert args[1]=='(UID INTERNALDATE BODY.PEEK[])'
                return 'OK',[(b'1 (UID 1 INTERNALDATE "01-Nov-2026 12:00:00 +0900")',b'Subject: meeting\r\n\r\nTomorrow')]
        api=NaverReadOnly.__new__(NaverReadOnly); api.client=Fake()
        messages,report=api.page(datetime(2026,10,1,tzinfo=timezone.utc))
        self.assertTrue(api.client.readonly); self.assertEqual(messages[0]['originId'],'12:1')
        self.assertFalse(report['coverageComplete'])


class CalendarTests(unittest.TestCase):
    def test_calendar_change_replay_and_cancel(self):
        from hub.sources.calendar_pilot import collect
        class API:
            item={'id':'e1','summary':'Meeting','status':'confirmed','start':{'date':'2026-11-02'},'end':{'date':'2026-11-03'},'updated':'2026-11-01T00:00:00Z'}
            def calendars(self):return [{'id':'c1','primary':True,'summary':'Test'}]
            def profile(self):return {'emailAddress':'test@example.com'}
            def get(self,*args):return {'items':[self.item]}
        api=API();store=Store(':memory:')
        self.assertEqual(collect(store,api,'primary')['applied'],1)
        self.assertEqual(collect(store,api,'primary')['applied'],0)
        api.item={**api.item,'start':{'date':'2026-11-04'},'end':{'date':'2026-11-05'}}
        self.assertEqual(collect(store,api,'primary')['changed'],1)
        api.item={'id':'e1','status':'cancelled'}
        self.assertEqual(collect(store,api,'primary')['applied'],1)
        event=store.snapshot()['events'][0]
        self.assertEqual(event['status'],'cancelled');self.assertTrue(event['endExclusive'])
        self.assertEqual(event['version'],3)

if __name__=='__main__':unittest.main()
