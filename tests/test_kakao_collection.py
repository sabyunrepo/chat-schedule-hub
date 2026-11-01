import unittest
from hub.sources.kakao_collection import eligibility


class KakaoPolicyTests(unittest.TestCase):
    def test_revisit_does_not_duplicate_or_reclassify(self):
        from hub.core import Store
        from hub.sources.kakao_collection import collect
        class Provider:
            name='test';model='test'
            def classify_page(self,messages,indices,context):
                return {i:{'intent':'schedule','relevance':1,'confidence':1} for i in indices}
        store=Store(':memory:')
        args=dict(store=store,target='t',label='test',latest='2026-11-01T00:00:00+09:00',quiet=False,
                  since='2026-10-02T00:00:00+09:00',until='2026-11-02T00:00:00+09:00',provider=Provider())
        def rows(prefix):return [{'text':prefix+str(i),'sentAt':'2026-11-01T00:00:00+09:00','authorRef':None} for i in range(3)]
        first=rows('first');second=rows('second')
        collect(**args,observations=[first,first])
        collect(**args,observations=[second,second])
        result=collect(**args,observations=[first,first])
        self.assertEqual(store.db.execute('SELECT count(*) FROM messages').fetchone()[0],6)
        self.assertEqual(result['batches'][0]['new'],0)
        self.assertEqual(result['batches'][0]['selection']['apiCalls'],0)

    def test_quiet_wins_even_when_recent(self):
        self.assertEqual(eligibility(True,'2026-11-01T00:00:00+09:00','2026-10-02T00:00:00+09:00'),'excluded-quiet')

    def test_inactive_and_unknown(self):
        self.assertEqual(eligibility(False,'2026-09-30T00:00:00+09:00','2026-10-02T00:00:00+09:00'),'excluded-inactive')
        self.assertEqual(eligibility(False,None,'2026-10-02T00:00:00+09:00'),'needs-verification')

    def test_active_boundary(self):
        self.assertEqual(eligibility(False,'2026-10-02T00:00:00+09:00','2026-10-02T00:00:00+09:00'),'eligible')
