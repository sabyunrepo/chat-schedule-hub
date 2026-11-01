import unittest
from hub.core import Store
from hub.delta_sync import prepare,acknowledge,deliver

class DeltaTests(unittest.TestCase):
    def setUp(self):
        self.store=Store(':memory:');self.origin='https://test.example'
        self.store.register_target('room','kakao-mac','account','Room',{'since':'2026-10-01T00:00:00Z','until':'2026-11-01T00:00:00Z'})
    def test_retry_noop_and_single_change(self):
        first=prepare(self.store,self.origin)
        self.assertEqual(first,prepare(self.store,self.origin))
        with self.assertRaises(ValueError):acknowledge(self.store,self.origin,first,{'ok':False})
        acknowledge(self.store,self.origin,first,{'ok':True,'sequence':first['sequence']})
        self.assertIsNone(prepare(self.store,self.origin))
        self.store.db.execute("UPDATE targets SET label='Changed' WHERE id='room'")
        second=prepare(self.store,self.origin)
        self.assertEqual(len(second['records']),1);self.assertEqual(second['sequence'],2)
        self.assertEqual(second['installationId'],first['installationId'])
    def test_destinations_and_no_deletion(self):
        first=prepare(self.store,self.origin)
        other=prepare(self.store,'https://other.example')
        self.assertNotEqual(first['installationId'],other['installationId'])
        acknowledge(self.store,self.origin,first,{'ok':True,'sequence':1})
        self.store.db.execute("DELETE FROM targets WHERE id='room'")
        self.assertIsNone(prepare(self.store,self.origin))
    def test_failure_keeps_pending_and_zero_request_replay(self):
        def fail(batch):raise OSError('offline')
        with self.assertRaises(OSError):deliver(self.store,self.origin,'a','b',send=fail)
        pending=prepare(self.store,self.origin)
        report=deliver(self.store,self.origin,'a','b',send=lambda b:{'ok':True,'sequence':b['sequence']})
        self.assertEqual(report['records'],len(pending['records']))
        self.assertEqual(deliver(self.store,self.origin,'a','b',send=fail)['batches'],0)
