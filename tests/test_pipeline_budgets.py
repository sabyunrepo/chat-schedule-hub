import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from hub.pipeline import cycle, extraction_budgets, extract_bounded


class PipelineBudgetTests(unittest.TestCase):
    def test_fallback_and_single_override(self):
        self.assertEqual(extraction_budgets({'jobsPerSource':1,'jobsPerSourceByName':{'kakao':8}}),
                         {'discord':1,'kakao':8,'mail-calendar':1})
        self.assertEqual(extraction_budgets({})['kakao'],5)

    def test_invalid_budgets_rejected_before_work(self):
        for value in [0,51,True,1.5,'8',None]:
            with self.subTest(value=value),self.assertRaises(ValueError):
                extraction_budgets({'jobsPerSourceByName':{'kakao':value}})
        for overrides in [[],{'unknown':1}]:
            with self.assertRaises(ValueError):extraction_budgets({'jobsPerSourceByName':overrides})

    def test_fifty_jobs_remain_bounded_and_aggregate(self):
        def result(store,provider,limit):return {'processed':limit,'applied':1,'failed':0,'modelCalls':limit}
        with patch('hub.pipeline.process',side_effect=result) as process:
            report=extract_bounded(Mock(),Mock(),50)
        self.assertEqual([c.args[2] for c in process.call_args_list],[20,20,10])
        self.assertEqual(report,{'processed':50,'applied':3,'failed':0,'modelCalls':50})

    def test_failure_does_not_get_immediately_retried(self):
        with patch('hub.pipeline.process',return_value={'processed':19,'applied':0,'failed':1,'modelCalls':20}) as process:
            report=extract_bounded(Mock(),Mock(),50)
        self.assertEqual(process.call_count,1)
        self.assertEqual(report['failed'],1)

    def run_cycle(self, *, changed=False, push=False, keychain_failure=False, supplied_token=None, origin='https://example.chatgpt.site'):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            config={'externalProcessingAllowed':True,'sources':['kakao','discord'],'jobsPerSource':1,
                    'jobsPerSourceByName':{'kakao':8},'siteAccess':'macos-keychain','pushEnabled':push}
            (root/'pipeline.json').write_text(json.dumps(config))
            (root/'update.json').write_text(json.dumps({'siteOrigin':origin}))
            for db in ['kakao-live.sqlite','discord-live.sqlite']:(root/db).touch()
            with patch('hub.pipeline.Store'),patch('hub.pipeline.extractors.create'),patch('hub.pipeline.materialize',return_value={}),\
                 patch('hub.pipeline.extract_bounded',return_value={'processed':0}) as extract,\
                 patch('hub.pipeline.prepare',return_value={'records':[{}]} if changed else None) as prepare,\
                 patch('hub.pipeline.secret',return_value='pairing') as secret,\
                 patch('hub.pipeline.deliver',return_value={'ok':True}) as deliver,\
                 patch('hub.site_access.service_token',side_effect=RuntimeError('blocked') if keychain_failure else None,return_value='access') as token,\
                 patch('hub.push.cycle',return_value={'sent':0}) as push_cycle,\
                 patch('hub.pipeline.private_write'):
                report=cycle(root,site_token=supplied_token)
                if origin.endswith('/'):
                    self.assertTrue(all(c.args[1]==origin.rstrip('/') for c in prepare.call_args_list))
                return report,extract,secret,deliver,token,push_cycle

    def test_unchanged_sources_skip_all_authentication_and_delivery(self):
        report,extract,secret,deliver,token,push=self.run_cycle()
        self.assertEqual([c.args[2] for c in extract.call_args_list],[8,1])
        self.assertEqual(report['kakao']['sync']['state'],'unchanged')
        secret.assert_not_called();deliver.assert_not_called();token.assert_not_called();push.assert_not_called()

    def test_push_still_gets_token_without_source_changes(self):
        _,_,secret,deliver,token,push=self.run_cycle(push=True)
        token.assert_called_once();push.assert_called_once()
        secret.assert_not_called();deliver.assert_not_called()

    def test_changed_sources_share_one_authentication_attempt(self):
        _,_,secret,deliver,token,_=self.run_cycle(changed=True)
        token.assert_called_once();self.assertEqual(deliver.call_count,2)

    def test_failed_access_keeps_pending_and_does_not_repeat_prompt(self):
        report,_,secret,deliver,token,push=self.run_cycle(changed=True,push=True,keychain_failure=True)
        token.assert_called_once();deliver.assert_not_called();secret.assert_not_called();push.assert_not_called()
        self.assertTrue(report['kakao']['sync']['pendingRetained'])
        self.assertEqual(report['push']['state'],'awaiting_site_access')

    def test_supplied_token_used_only_when_needed(self):
        _,_,secret,deliver,token,_=self.run_cycle(supplied_token='existing')
        token.assert_not_called();secret.assert_not_called();deliver.assert_not_called()

    def test_origin_is_canonical_before_preparing_batch(self):
        self.run_cycle(changed=True,origin='https://example.chatgpt.site/')
