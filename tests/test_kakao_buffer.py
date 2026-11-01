import copy
import unittest
from unittest.mock import patch

from hub.core import Store
from hub.sources.kakao_buffer import collect_buffer


def rows(*values):
    return [dict(text='일정 '+str(v),sentAt='2026-10-20T12:00:00+09:00',
                 authorDisplayName='synthetic',authorRef=None,reviewedSchedule=True) for v in values]


def frames(*views):
    return [dict(observationId='capture-'+str(i),rows=copy.deepcopy(view)) for i,view in enumerate(views)]


class Provider:
    name='test';model='test'
    def __init__(self): self.calls=0; self.messages=[]
    def classify_page(self,messages,indices,context):
        self.calls+=1;self.messages.extend(messages)
        return {i:dict(intent='schedule',confidence=1,relevance=1) for i in indices}


class KakaoBufferTests(unittest.TestCase):
    def setUp(self):
        self.store=Store(':memory:');self.provider=Provider()
        self.args=dict(store=self.store,target='t',label='fixture',latest='2026-10-20T12:00:00+09:00',
                       quiet=False,since='2026-10-02T00:00:00+09:00',until='2026-11-01T00:00:00+09:00',
                       provider=self.provider)

    def test_independent_identical_frames_then_processed_frame_skips(self):
        result=collect_buffer(**self.args,frames=frames(rows(1,2,3),rows(1,2,3),rows(1,2,3)))
        self.assertEqual(result['new'],3)
        self.assertEqual(result['apiCalls'],1)
        self.assertEqual(result['processedFrames'],1)
        self.assertEqual(result['skippedFrames'],1)
        self.assertFalse(result['coverageVerified'])
        self.assertEqual(result['frames'][0]['state'],'confirmed-by-later-observation')

    def test_nonadjacent_prior_frame_can_verify_current(self):
        result=collect_buffer(**self.args,frames=frames(rows(1,2,3,4),rows(8,9,10),rows(1,2,3,4)))
        self.assertEqual(result['new'],4)
        self.assertEqual(result['collections'][0]['referenceIndex'],0)
        self.assertEqual(result['unmatchedFrames'],1)

    def test_financial_and_date_excluded_before_fingerprints_or_model(self):
        page=rows(1,2,3,4,5)
        page[3]['text']='송금 내역'
        page[4]['sentAt']='2026-09-01T12:00:00+09:00'
        with patch('hub.sources.kakao_buffer.digest',wraps=__import__('hub.core',fromlist=['digest']).digest) as hashing:
            result=collect_buffer(**self.args,frames=frames(page,page))
        self.assertEqual(result['new'],3)
        self.assertNotIn('송금 내역',str(hashing.call_args_list))
        self.assertNotIn('2026-09-01',str(hashing.call_args_list))
        self.assertEqual(len(self.provider.messages),3)
        self.assertEqual(result['frames'][0]['filterCounts']['financial'],1)

    def test_gaps_never_join_into_three_row_anchor(self):
        page=rows(1)+[None]+rows(2,3)
        result=collect_buffer(**self.args,frames=frames(page,page))
        self.assertEqual(result['state'],'held')
        self.assertEqual(self.provider.calls,0)
        self.assertEqual(self.store.db.execute('select count(*) from targets').fetchone()[0],0)

    def test_ambiguous_repeat_is_not_anchor(self):
        page=rows(1,1,1,1)
        result=collect_buffer(**self.args,frames=frames(page,page))
        self.assertEqual(result['state'],'held')
        self.assertEqual(result['apiCalls'],0)

    def test_duplicate_observation_id_and_target_mismatch_rejected(self):
        items=frames(rows(1,2,3),rows(1,2,3))
        items[1]['observationId']=items[0]['observationId']
        with self.assertRaises(ValueError):collect_buffer(**self.args,frames=items)
        items=frames(rows(1,2,3),rows(1,2,3));items[1]['target']='another'
        with self.assertRaises(ValueError):collect_buffer(**self.args,frames=items)
        self.assertEqual(self.provider.calls,0)

    def test_excluded_room_does_not_inspect_frames(self):
        result=collect_buffer(**dict(self.args,quiet=True),frames=None)
        self.assertEqual(result['state'],'excluded-quiet')
        self.assertEqual(self.provider.calls,0)

    def test_partial_frame_can_be_retried_with_more_observed_context(self):
        result=collect_buffer(**self.args,frames=frames(rows(1,2,3),rows(1,2,3,4),rows(1,2,3,4)))
        self.assertEqual(result['processedFrames'],2)
        self.assertEqual(result['new'],4)
        self.assertEqual(self.store.db.execute('select count(*) from messages').fetchone()[0],4)

    def test_provider_failure_propagates_and_replay_can_succeed(self):
        items=frames(rows(1,2,3),rows(1,2,3))
        with patch.object(self.provider,'classify_page',side_effect=RuntimeError('synthetic failure')):
            with self.assertRaises(RuntimeError):collect_buffer(**self.args,frames=items)
        self.assertEqual(self.store.db.execute('select count(*) from messages').fetchone()[0],0)
        result=collect_buffer(**self.args,frames=items)
        self.assertEqual(result['new'],3)
        replay=collect_buffer(**self.args,frames=items)
        self.assertEqual(replay['new'],0)
        self.assertEqual(replay['apiCalls'],0)

    def test_buffer_budget(self):
        with self.assertRaises(ValueError): collect_buffer(**self.args,frames=frames(*[rows(1,2,3)]*9))

    def test_cli_requires_consent_and_processes_real_frame_shape(self):
        import io, json, os, sys, tempfile
        from hub.cli import main
        data=dict(target='t',label='fixture',latest=self.args['latest'],quiet=False,
                  since=self.args['since'],until=self.args['until'],frames=frames(rows(1,2,3),rows(1,2,3)))
        with tempfile.TemporaryDirectory() as directory:
            def command(payload):
                out=io.StringIO()
                with patch.dict(os.environ,{'HUB_DB':directory+'/test.sqlite'}), patch.object(sys,'argv',['hub','kakao-buffer']), \
                     patch.object(sys,'stdin',io.StringIO(json.dumps(payload))), patch.object(sys,'stdout',out), \
                     patch('hub.providers.providers.create',return_value=self.provider):
                    main()
                return json.loads(out.getvalue())
            with self.assertRaises(ValueError): command(data)
            data['externalProcessingAllowed']=True
            self.assertEqual(command(data)['new'],3)
            self.assertEqual(command(data)['new'],0)


if __name__=='__main__':unittest.main()
