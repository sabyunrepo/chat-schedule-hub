import json
import tempfile
import unittest
from pathlib import Path
from hub.core import Store
from hub.sources.discord_stream import Queue, process
from hub.sources.discord_bot import normalize,target_id
from tests.test_selection import Fake


class StreamTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'test.sqlite'
        self.s=Store(self.path);self.q=Queue(self.s.db,['10'])
        self.cfg={'guildAllowlist':['10'],'applicationId':'30'}
    def tearDown(self):self.s.db.close();self.tmp.cleanup()
    def add(self,kind='fetch'):
        with self.s.db:self.q.enqueue('10','20','100',kind)
        return self.q.next()
    def msg(self,text='내일 3시에 모임'):
        return normalize({'id':'100','channel_id':'20','content':text,'timestamp':'2026-11-01T00:00:00+00:00','author':{'id':'40'}},'30','10','20')
    def test_id_queue_survives_restart(self):
        self.add();other=Store(self.path);q=Queue(other.db,['10'])
        self.assertEqual(q.next()['message'],'100');other.db.close()
        self.assertNotIn('content',[r['name'] for r in self.s.db.execute('PRAGMA table_info(discord_queue)')])
    def test_scope_rejected(self):
        self.assertFalse(self.q.enqueue('99','20','100'));self.assertIsNone(self.q.next())
    def test_newer_edit_not_lost_by_old_ack(self):
        old=self.add();self.add()
        with self.s.db:self.q.ack(old)
        self.assertEqual(self.q.next()['generation'],2)
    def test_delete_is_terminal_in_queue(self):
        self.add('delete');self.add('fetch');self.assertEqual(self.q.next()['kind'],'delete')
    def test_failure_keeps_retryable_id(self):
        item=self.add();self.q.fail(item,'failure')
        self.assertEqual(self.s.db.execute('SELECT attempts FROM discord_queue').fetchone()[0],1)
    def test_unchanged_and_metadata_only_no_model(self):
        provider=Fake({0:'schedule'})
        process(self.path,self.cfg,self.add(),self.msg(),provider=provider)
        m=self.msg();m['editedAt']='2026-11-01T00:01:00+00:00'
        result=process(self.path,self.cfg,self.add(),m,provider=provider)
        self.assertEqual(result['apiCalls'],0);self.assertEqual(provider.calls,1)
        self.assertIsNone(self.q.next())
    def test_edit_and_explicit_delete_keep_revisions(self):
        p=Fake({0:'schedule'})
        process(self.path,self.cfg,self.add(),self.msg(),provider=p)
        result=process(self.path,self.cfg,self.add(),self.msg('내일 4시로 변경'),provider=p)
        self.assertEqual(result['changed'],1)
        result=process(self.path,self.cfg,self.add('delete'),None,provider=p)
        self.assertEqual(result['apiCalls'],0)
        self.assertEqual(self.s.db.execute('SELECT COUNT(*) FROM revisions').fetchone()[0],3)
        result=process(self.path,self.cfg,self.add(),self.msg(),provider=p)
        self.assertEqual(result['apiCalls'],0)
    def test_provider_failure_leaves_queue_and_no_seen(self):
        with self.assertRaises(Exception):process(self.path,self.cfg,self.add(),self.msg(),provider=Fake(fail=True))
        self.assertIsNotNone(self.q.next());self.assertEqual(self.s.db.execute('SELECT COUNT(*) FROM discord_seen').fetchone()[0],0)
    def test_context_observation_time_does_not_invalidate(self):
        ctx=self.msg('앞선 이야기');ctx['originId']='99'
        p=Fake({0:'schedule'})
        process(self.path,self.cfg,self.add(),self.msg(),[ctx],provider=p)
        ctx['observedAt']='later'
        result=process(self.path,self.cfg,self.add(),self.msg(),[ctx],provider=p)
        self.assertEqual(result['apiCalls'],0)
    def test_live_does_not_advance_history_cursor(self):
        target=target_id('30','10','20')
        self.s.register_target(target,'discord-bot','30','test',{'since':'2026-10-01T00:00:00+00:00','until':'2026-12-01T00:00:00+00:00'})
        r=self.s.begin(target)
        with self.s.db:self.s.db.execute('UPDATE runs SET cursor=? WHERE id=?',(json.dumps({'before':'88'}),r['id']))
        process(self.path,self.cfg,self.add(),self.msg(),provider=Fake({0:'schedule'}))
        self.assertEqual(json.loads(self.s.begin(target)['cursor']),{'before':'88'})
