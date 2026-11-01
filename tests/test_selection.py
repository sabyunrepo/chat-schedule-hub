import unittest,json
from hub.core import Store
from hub.selection import select_ingest
from hub.providers import OpenAIDecisions,ProviderError

class Fake:
    name='test';model='test'
    def __init__(self, intents=None, fail=False):self.calls=0;self.intents=intents or {};self.fail=fail
    def classify_page(self,messages,indices,context):
        self.calls+=1
        if self.fail:raise ProviderError('failure')
        return {i:{'intent':self.intents.get(i,'other'),'confidence':.99,'relevance':.9 if i in self.intents else .01} for i in indices}

class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.s=Store(':memory:');self.s.register_target('t','fixture','a','test',{'since':'2026-10-01T00:00:00+00:00','until':'2026-12-01T00:00:00+00:00'})
        self.b={'schemaVersion':1,'batchId':'b','runId':self.s.begin('t')['id'],'targetId':'t','verifiedTarget':True,'externalProcessingAllowed':True,'messages':[{'originId':str(i),'text':'private '+str(i),'sentAt':'2026-11-01T00:00:00+00:00','observedAt':'2026-11-01T01:00:00+00:00'} for i in range(7)],'stopReason':'budget-exhausted','cursor':{'page':1}}
    def test_only_relevant_and_neighbors_retained(self):
        r=select_ingest(self.s,self.b,Fake({3:'schedule'}));self.assertEqual(r['selection']['retained'],3)
        texts=[j['message']['text'] for j in self.s.pending()];self.assertEqual(set(texts),{'private 2','private 3','private 4'})
        raw=' '.join(str(tuple(r)) for r in self.s.db.execute('SELECT * FROM observations'));self.assertNotIn('private',raw)
    def test_failure_does_not_advance_or_persist(self):
        with self.assertRaises(ProviderError):select_ingest(self.s,self.b,Fake(fail=True))
        self.assertEqual(self.s.begin('t')['cursor'],'{}');self.assertEqual(self.s.db.execute('SELECT count(*) FROM observations').fetchone()[0],0)
    def test_repeated_page_no_api_and_no_duplicate(self):
        p=Fake();select_ingest(self.s,self.b,p);self.b['batchId']='retry';r=select_ingest(self.s,self.b,p)
        self.assertEqual(p.calls,1);self.assertEqual(r['selection']['apiCalls'],0);self.assertEqual(r['selection']['cacheHits'],7)
    def test_changed_message_reclassified(self):
        p=Fake();select_ingest(self.s,self.b,p);self.b['batchId']='edit';self.b['messages'][0]['text']='내일 취소';select_ingest(self.s,self.b,p);self.assertEqual(p.calls,2)
    def test_scope_checked_before_api(self):
        p=Fake();self.b['messages'][0]['sentAt']='2026-01-01T00:00:00+00:00'
        with self.assertRaises(ValueError):select_ingest(self.s,self.b,p)
        self.assertEqual(p.calls,0)
    def test_uncertain_retained(self):
        r=select_ingest(self.s,self.b,Fake({0:'uncertain'}));self.assertEqual(r['selection']['retained'],2)
    def test_irrelevant_uncertain_greetings_not_retained(self):
        class GreetingProvider(Fake):
            def classify_page(self,messages,indices,context):
                return {i:{'intent':'uncertain','confidence':.9,'relevance':0} for i in indices}
        for m in self.b['messages']:m['text']='안녕'
        result=select_ingest(self.s,self.b,GreetingProvider())
        self.assertEqual(result['selection']['retained'],0)
        self.assertEqual(self.s.pending(),[])

    def test_narrower_policy_accepts_v6_run(self):
        select_ingest(self.s,self.b,Fake())
        old=json.loads(self.s.db.execute('SELECT result FROM batches').fetchone()[0])
        old['selection']['ruleVersion']=6
        with self.s.db:self.s.db.execute('UPDATE batches SET result=?',(json.dumps(old),))
        self.b['batchId']='v7-page'
        self.assertEqual(select_ingest(self.s,self.b,Fake())['selection']['ruleVersion'],7)
    def test_dropped_messages_still_form_boundary(self):
        self.b.update(stopReason='requested-range-reached',coverageVerified=True);select_ingest(self.s,self.b,Fake())
        self.b.update(batchId='next',runId=self.s.begin('t')['id'],stopReason='continue');r=select_ingest(self.s,self.b,Fake());self.assertEqual(r['stopReason'],'known-boundary');self.assertEqual(len(self.s.pending()),0)
    def test_provider_rejects_incomplete_or_refusal(self):
        p=OpenAIDecisions(transport=lambda body:{'answers':[{'type':'choice','name':'m0','choice':'other','confidence':.99}]})
        with self.assertRaises(ProviderError):p.classify_page([{},{}],[0,1])
        p=OpenAIDecisions(transport=lambda body:{'answers':[{'type':'refusal','name':'m0'}]})
        with self.assertRaises(ProviderError):p.classify_page([{}],[0])
    def test_answer_name_not_position(self):
        p=OpenAIDecisions(transport=lambda body:{'answers':[{'type':'choice','name':'m1','choice':'other','confidence':.99},{'type':'choice','name':'m0','choice':'schedule','confidence':.9}]})
        p.transport=lambda body:{'answers':[{'type':'predicate','name':'r0','probability':.9},{'type':'choice','name':'m1','choice':'other','confidence':.99},{'type':'predicate','name':'r1','probability':.01},{'type':'choice','name':'m0','choice':'schedule','confidence':.9}]}
        self.assertEqual(p.classify_page([{},{}],[0,1])[0]['intent'],'schedule')

    def test_time_hint_survives_false_negative(self):
        self.b['messages'][3]['text']='4시간 남았네요'
        r=select_ingest(self.s,self.b,Fake())
        self.assertEqual(r['selection']['retained'],1)
        self.assertEqual(self.s.pending()[0]['message']['text'],'4시간 남았네요')

    def test_batch_id_cannot_hide_changed_payload(self):
        p=Fake();select_ingest(self.s,self.b,p)
        self.b['messages'][0]['text']='modified'
        with self.assertRaises(ValueError):select_ingest(self.s,self.b,p)
        self.assertEqual(p.calls,1)

    def test_short_join_request_survives_false_negative(self):
        self.b['messages'][3]['text']='보이스 ㄱㄱ'
        select_ingest(self.s,self.b,Fake())
        self.assertEqual([j['message']['originId'] for j in self.s.pending()],['3'])

    def test_pending_preserves_decision_for_extraction(self):
        select_ingest(self.s,self.b,Fake({3:'schedule'}))
        item=next(j for j in self.s.pending() if j['message']['originId']=='3')
        self.assertEqual(item['decision']['intent'],'schedule')

    def test_correction_and_distant_reply_evidence_retained(self):
        self.b['messages'][6].update(text='정정합니다',replyToRef={'targetId':'t','identity':'0'})
        select_ingest(self.s,self.b,Fake())
        self.assertEqual({j['message']['originId'] for j in self.s.pending()},{'0','6'})

    def test_missing_cross_room_evidence_blocks_completion(self):
        self.b['messages'][6].update(text='정정합니다',replyToRef={'targetId':'other','identity':'0'})
        self.b.update(stopReason='requested-range-reached',coverageVerified=True)
        with self.assertRaisesRegex(ValueError,'unresolved reply'):
            select_ingest(self.s,self.b,Fake())
        self.assertEqual(len(self.s.pending()),0)
        self.assertEqual(self.s.db.execute('SELECT count(*) FROM boundaries').fetchone()[0],0)
        self.b.update(stopReason='budget-exhausted',coverageVerified=False)
        result=select_ingest(self.s,self.b,Fake())
        self.assertFalse(result['complete'])
        self.assertEqual(result['selection']['evidenceGaps'],[{'targetId':'other','identity':'0'}])

    def test_changed_reply_creates_revision_and_reclassifies(self):
        self.b['messages'][3].update(text='정정합니다',replyToRef={'targetId':'t','identity':'0'})
        p=Fake();select_ingest(self.s,self.b,p)
        self.b['batchId']='reply-change';self.b['messages'][3]['replyToRef']['identity']='1'
        select_ingest(self.s,self.b,p)
        revisions=[j for j in self.s.pending() if j['message']['originId']=='3']
        self.assertEqual(len(revisions),2);self.assertEqual(p.calls,2)

    def test_cycle_in_reply_chain_terminates(self):
        self.b['messages'][6].update(text='정정합니다',replyToRef={'targetId':'t','identity':'0'})
        self.b['messages'][0]['replyToRef']={'targetId':'t','identity':'6'}
        result=select_ingest(self.s,self.b,Fake())
        self.assertEqual(result['selection']['retained'],2)

    def test_old_policy_boundary_does_not_skip_discarded_evidence(self):
        self.b.update(stopReason='requested-range-reached',coverageVerified=True)
        select_ingest(self.s,self.b,Fake())
        with self.s.db:self.s.db.execute('UPDATE boundary_policies SET version=1')
        self.assertEqual(self.s.begin('t')['baseline'],'[]')

    def test_earlier_page_gap_blocks_clean_final_page(self):
        self.b['messages'][6].update(text='정정합니다',replyToRef={'targetId':'t','identity':'missing'})
        select_ingest(self.s,self.b,Fake())
        self.b.update(batchId='final-page',messages=[],stopReason='requested-range-reached',coverageVerified=True)
        with self.assertRaisesRegex(ValueError,'unresolved reply'):
            select_ingest(self.s,self.b,Fake())
        self.b['messages']=[{'originId':'missing','text':'original','observedAt':'2026-11-01T01:00:00+00:00'}]
        result=select_ingest(self.s,self.b,Fake())
        self.assertTrue(result['complete'])
        self.assertTrue(any(j['message']['originId']=='missing' for j in self.s.pending()))

    def test_policy_change_in_partial_run_requires_reobservation(self):
        select_ingest(self.s,self.b,Fake())
        old=json.loads(self.s.db.execute('SELECT result FROM batches').fetchone()[0])
        old['selection']['ruleVersion']=1
        with self.s.db:self.s.db.execute('UPDATE batches SET result=?',(json.dumps(old),))
        self.b['batchId']='new-policy'
        p=Fake()
        with self.assertRaisesRegex(ValueError,'retention policy changed'):
            select_ingest(self.s,self.b,p)
        self.assertEqual(p.calls,0)
        new=self.s.begin('t',restart=True)
        self.assertNotEqual(new['id'],self.b['runId']);self.assertEqual(new['baseline'],'[]')
        self.assertEqual(new['cursor'],'{}')
