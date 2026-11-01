import unittest
from hub.core import Store
from hub.sources.kakao_incremental import KakaoScan, run_scan

class Provider:
    name='test'; model='test'
    def __init__(self): self.calls=0; self.fail=False
    def classify_page(self,messages,indices,context):
        self.calls+=1
        if self.fail: raise RuntimeError('synthetic failure')
        return {i:{'intent':'schedule','relevance':1,'confidence':1} for i in indices}

def rows(*numbers):
    return [dict(text=f'일정 {i}',sentAt=f'2026-10-{i:02}T09:00:00+09:00',
                 authorDisplayName='synthetic',reviewedSchedule=True) for i in numbers]

class IncrementalTests(unittest.TestCase):
    def setUp(self):
        self.store=Store(':memory:'); self.scan=KakaoScan(self.store); self.provider=Provider()
        self.scope=dict(target='t',label='fixture',since='2026-10-01T00:00:00+09:00',
                        until='2026-11-01T00:00:00+09:00',quiet=False,latest='2026-10-30T00:00:00+09:00')
        self.scan.start(**self.scope)
    def step(self, page, **kw):
        return self.scan.step('t','fixture',[page,page],self.provider,quiet=False,latest=self.scope['latest'],**kw)
    def test_completed_boundary_stops_repeated_history(self):
        page=rows(20,21,22)
        self.assertEqual(self.step(page,at_latest=True,source_end=True)['state'],'complete')
        calls=self.provider.calls
        self.scan.start(**self.scope)
        result=self.step(page,at_latest=True)
        self.assertEqual(result['reason'],'known-boundary')
        self.assertEqual(result['action'],'stop')
        self.assertEqual(calls,self.provider.calls)
    def test_new_messages_on_boundary_page_are_saved_before_stopping(self):
        self.step(rows(20,21,22),at_latest=True,source_end=True)
        self.scan.start(**self.scope)
        result=self.step(rows(20,21,22,23),at_latest=True)
        self.assertEqual(result['reason'],'known-boundary')
        self.assertEqual(self.store.db.execute('select count(*) from messages').fetchone()[0],4)
    def test_partial_restart_seeks_frontier_without_model_and_continues_older(self):
        self.step(rows(20,21,22),at_latest=True)
        self.scan=KakaoScan(self.store)  # fresh controller, durable DB state
        self.assertTrue(self.scan.start(**self.scope)['resuming'])
        before=self.provider.calls
        self.assertEqual(self.step(rows(24,25,26),at_latest=True)['state'],'seeking')
        self.assertEqual(self.provider.calls,before)
        self.assertEqual(self.step(rows(20,21,22))['action'],'scroll-older')
        self.assertEqual(self.step(rows(19,20,21,22),source_end=True)['state'],'complete')
        self.assertEqual(self.store.db.execute('select count(*) from messages').fetchone()[0],4)
        # New messages observed while seeking are intentionally deferred to next pass.
        self.scan.start(**self.scope)
        self.assertEqual(self.step(rows(20,21,22,24,25,26),at_latest=True)['state'],'complete')
        self.assertEqual(self.store.db.execute('select count(*) from messages').fetchone()[0],7)
    def test_failure_does_not_advance_committed_frontier(self):
        self.step(rows(20,21,22),at_latest=True)
        before=self.scan.status('t')
        self.provider.fail=True
        with self.assertRaises(RuntimeError): self.step(rows(19,20,21,22))
        self.assertEqual(self.scan.status('t'),before)
        self.provider.fail=False
        self.assertEqual(self.step(rows(19,20,21,22))['state'],'scanning')
    def test_jump_does_not_close_gap_or_advance(self):
        self.step(rows(20,21,22),at_latest=True)
        before=self.scan.status('t')
        self.assertEqual(self.step(rows(10,11,12),source_end=True)['state'],'gap-detected')
        self.assertEqual(self.scan.status('t'),before)
    def test_missing_anchor_budget_and_no_progress(self):
        self.step(rows(20,21,22),at_latest=True)
        self.scan.start(**dict(self.scope,max_pages=1))
        self.step(rows(24,25,26),at_latest=True)
        self.assertEqual(self.step(rows(23,24,25))['state'],'anchor-lost')
        self.scan.start(**self.scope)
        self.step(rows(24,25,26),at_latest=True)
        self.step(rows(24,25,26))
        self.assertEqual(self.step(rows(24,25,26))['state'],'no-content-progress')
    def test_unreviewed_or_empty_never_overwrites_frontier(self):
        self.step(rows(20,21,22),at_latest=True); before=self.scan.status('t')
        page=rows(19,20,21,22);page[0]['reviewedSchedule']=None
        self.assertEqual(self.step(page)['state'],'needs-review')
        self.assertEqual(self.scan.status('t'),before)
    def test_target_policy_and_range_isolation(self):
        with self.assertRaises(ValueError): self.scan.step('t','wrong',[rows(1,2,3)]*2,self.provider,quiet=False,latest=self.scope['latest'])
        self.assertEqual(self.scan.start(**dict(self.scope,quiet=True))['action'],'stop')
        self.assertEqual(self.store.db.execute('select count(*) from messages').fetchone()[0],0)
    def test_host_driver_loop_scrolls_and_stops(self):
        frames=[rows(20,21,22),rows(19,20,21,22)]
        outer=self
        class Driver:
            index=0; scrolls=0
            def open_latest(self,target): self.index=0
            def observe_pair(self):
                page=frames[self.index]
                return dict(target='t',label='fixture',observations=[page,page],quiet=False,
                            latest=outer.scope['latest'],at_latest=self.index==0,source_end=self.index==1)
            def scroll_older(self): self.index+=1;self.scrolls+=1
        driver=Driver()
        self.assertEqual(run_scan(self.scan,driver,self.provider,**self.scope)['state'],'complete')
        self.assertEqual(driver.scrolls,1)
    def test_reviewed_exclusions_keep_gaps_without_blocking_safe_overlap(self):
        page=rows(20,21,22,23)
        page[-1]['reviewedSchedule']=False
        result=self.step(page,at_latest=True,source_end=True)
        self.assertEqual(result['state'],'complete')
        self.assertEqual(self.store.db.execute('select count(*) from messages').fetchone()[0],3)
    def test_changed_message_is_not_skipped_by_old_boundary(self):
        self.step(rows(20,21,22),at_latest=True,source_end=True)
        self.scan.start(**self.scope)
        page=rows(20,21,22);page[1]['text']='일정 변경'
        self.assertEqual(self.step(page,at_latest=True)['action'],'scroll-older')
    def test_cli_scan_workflow(self):
        import io,sys,os,json,tempfile
        from unittest.mock import patch
        from hub.cli import main
        with tempfile.TemporaryDirectory() as directory:
            def command(name,data):
                out=io.StringIO()
                with patch.dict(os.environ,{'HUB_DB':directory+'/test.sqlite'}),patch.object(sys,'argv',['hub',name]),patch.object(sys,'stdin',io.StringIO(json.dumps(data))),patch.object(sys,'stdout',out),patch('hub.providers.providers.create',return_value=self.provider):
                    main()
                return json.loads(out.getvalue())
            self.assertEqual(command('kakao-scan-start',self.scope)['action'],'open-latest')
            frame=dict(target='t',label='fixture',quiet=False,latest=self.scope['latest'],
                       externalProcessingAllowed=True,observations=[rows(20,21,22)]*2,atLatest=True,sourceEnd=True)
            self.assertEqual(command('kakao-scan-step',frame)['state'],'complete')
            self.assertEqual(command('kakao-scan-status',{'target':'t'})['phase'],'complete')
