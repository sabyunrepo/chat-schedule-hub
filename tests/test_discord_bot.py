import unittest
from hub.sources.discord_bot import normalize, target_id, DiscordBot
from hub.core import Store
from hub.selection import select_ingest
from tests.test_selection import Fake


class DiscordTests(unittest.TestCase):
    def raw(self, text='내일 3시 모임'):
        return {'id':'100','channel_id':'20','timestamp':'2026-11-01T00:00:00+00:00',
                'content':text,'author':{'id':'40','username':'fixture'}}

    def test_partial_edit_requires_refetch(self):
        m=self.raw();del m['content']
        with self.assertRaises(ValueError):normalize(m,'a','10','20')

    def test_normalization_is_stable_and_scoped(self):
        m=self.raw();m['message_reference']={'message_id':'50','channel_id':'21','guild_id':'10'}
        result=normalize(m,'a','10','20',thread=True)
        self.assertEqual(result['replyToRef'],{'targetId':target_id('a','10','21'),'identity':'50'})
        self.assertEqual(result['threadRef'],'20')
        with self.assertRaises(ValueError):normalize(m,'a','10','99')

    def test_scope_checked_before_fetch(self):
        api=object.__new__(DiscordBot);api.guilds={'10'};calls=[]
        api.get=lambda route:calls.append(route)
        with self.assertRaises(ValueError):api.page('11','20')
        self.assertEqual(calls,[])

    def test_channel_guild_checked_before_message_read(self):
        api=object.__new__(DiscordBot);api.guilds={'10'};calls=[]
        def get(route):calls.append(route);return {'guild_id':'11'}
        api.get=get
        with self.assertRaises(ValueError):api.page('10','20')
        self.assertEqual(calls,['/channels/20'])

    def test_edit_keeps_identity_and_revision_history(self):
        s=Store(':memory:');t=target_id('a','10','20')
        s.register_target(t,'discord-bot','a','fixture',{'since':'2026-10-01T00:00:00+00:00','until':'2026-12-01T00:00:00+00:00'})
        b={'schemaVersion':1,'batchId':'one','runId':s.begin(t)['id'],'targetId':t,
           'verifiedTarget':True,'externalProcessingAllowed':True,'stopReason':'budget-exhausted',
           'messages':[normalize(self.raw(),'a','10','20')]}
        p=Fake({0:'schedule'});select_ingest(s,b,p)
        b['batchId']='two';m=self.raw('내일 4시로 변경');m['edited_timestamp']='2026-11-01T01:00:00+00:00'
        b['messages']=[normalize(m,'a','10','20')];r=select_ingest(s,b,p)
        self.assertEqual(r['changed'],1)
        self.assertEqual(s.db.execute('SELECT COUNT(*) FROM messages').fetchone()[0],1)
        self.assertEqual(s.db.execute('SELECT COUNT(*) FROM revisions').fetchone()[0],2)
        b['batchId']='three';r=select_ingest(s,b,p)
        self.assertEqual(r['changed'],0);self.assertEqual(r['selection']['apiCalls'],0)

    def test_uncertain_low_relevance_not_discarded(self):
        s=Store(':memory:');s.register_target('t','fixture','a','test',{'since':'2026-10-01T00:00:00+00:00','until':'2026-12-01T00:00:00+00:00'})
        class Uncertain(Fake):
            def classify_page(self,messages,indices,context):
                return {i:{'intent':'uncertain','confidence':.2,'relevance':.01} for i in indices}
        b={'schemaVersion':1,'batchId':'u','runId':s.begin('t')['id'],'targetId':'t','verifiedTarget':True,
           'externalProcessingAllowed':True,'stopReason':'budget-exhausted','messages':[normalize(self.raw('그쪽으로요'),'a','10','20')]}
        self.assertEqual(select_ingest(s,b,Uncertain())['selection']['retained'],1)
