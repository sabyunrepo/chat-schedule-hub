import unittest
from hub.core import Store, REGISTRY
from hub.providers import OpenAIDecisions, ProviderError

class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.s=Store(':memory:');self.s.register_target('t','fixture','a','Test',{'since':'2026-10-01T00:00:00+00:00','until':'2026-12-01T00:00:00+00:00'})
    def batch(self,ids,reason='budget-exhausted',run=None):
        return {'schemaVersion':1,'batchId':str(ids)+reason,'runId':(run or self.s.begin('t'))['id'],'targetId':'t','verifiedTarget':True,'messages':[{'originId':str(i),'text':'같은 문장','sentAt':'2026-11-01T01:00:00+00:00','observedAt':'2026-11-01T02:00:00+00:00'} for i in ids],'cursor':{'last':ids[-1] if ids else None},'stopReason':reason,'coverageVerified':reason=='requested-range-reached'}
    def test_resume_partial_without_gap(self):
        b=self.batch([9,8,7]);self.s.ingest(b); resumed=self.s.begin('t');self.assertEqual(resumed['id'],b['runId']);self.assertEqual(resumed['state'],'active');self.assertEqual(self.s.db.execute('SELECT count(*) FROM boundaries').fetchone()[0],0)
        self.s.ingest(self.batch([6,5,4],'requested-range-reached',resumed));self.assertEqual(len(self.s.pending()),6)
    def test_duplicate_batch_and_same_text_distinct(self):
        b=self.batch([3,2,1]);self.s.ingest(b);self.s.ingest(b);self.assertEqual(len(self.s.pending()),3)
    def test_overlap_stop(self):
        self.s.ingest(self.batch([3,2,1],'requested-range-reached'));b=self.batch([4,3,2,1]);b['coverageVerified']=True;self.assertEqual(self.s.ingest(b)['stopReason'],'known-boundary')
    def test_atomic_failure(self):
        b=self.batch([1,2]);del b['messages'][1]['originId']
        with self.assertRaises(ValueError): self.s.ingest(b)
        self.assertEqual(len(self.s.pending()),0)
    def test_target_isolation(self):
        b=self.batch([1]);b['targetId']='other'
        with self.assertRaises(ValueError): self.s.ingest(b)
    def test_explicit_coverage_required(self):
        b=self.batch([1],'requested-range-reached');b['coverageVerified']=False
        with self.assertRaises(ValueError): self.s.ingest(b)
        self.assertEqual(len(self.s.pending()),0)
    def test_revision_and_event_versions(self):
        b=self.batch([1]);self.s.ingest(b);b['batchId']='edit';b['messages'][0]['text']='다음날로 변경';self.s.ingest(b);self.assertEqual(len(self.s.pending()),2)
        with self.s.db:self.s.db.execute('INSERT INTO people VALUES(?,?)',('p','{"id":"p","name":"테스트"}'))
        c={'operationId':'op','eventId':'e','expectedVersion':0,'evidence':[self.s.pending()[0]['id']],'event':{'title':'모임','status':'proposed','kind':'crime','participants':['p'],'start':None,'end':None}}
        self.assertEqual(self.s.apply_event(c)['version'],1);self.assertTrue(self.s.apply_event(c)['duplicate'])
        c['operationId']='op2'
        with self.assertRaises(ValueError):self.s.apply_event(c)
    def test_provider_injection(self):
        p=OpenAIDecisions(transport=lambda body:{'answers':[{'type':'choice','choice':'attendance','confidence':.8}]});self.assertEqual(p.decide([])['intent'],'attendance')
        with self.assertRaises(ProviderError):OpenAIDecisions(transport=lambda body:{'answers':[{'type':'refusal'}]}).decide([])

if __name__=='__main__':unittest.main()
