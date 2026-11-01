import unittest
from hub.sources.kakao_collection import eligibility


class KakaoPolicyTests(unittest.TestCase):
    def test_quiet_wins_even_when_recent(self):
        self.assertEqual(eligibility(True,'2026-11-01T00:00:00+09:00','2026-10-02T00:00:00+09:00'),'excluded-quiet')

    def test_inactive_and_unknown(self):
        self.assertEqual(eligibility(False,'2026-09-30T00:00:00+09:00','2026-10-02T00:00:00+09:00'),'excluded-inactive')
        self.assertEqual(eligibility(False,None,'2026-10-02T00:00:00+09:00'),'needs-verification')

    def test_active_boundary(self):
        self.assertEqual(eligibility(False,'2026-10-02T00:00:00+09:00','2026-10-02T00:00:00+09:00'),'eligible')
