import unittest
from hub.card_events import parse_card
class CardTests(unittest.TestCase):
 def test_explicit_and_negotiated(self):
  key,e=parse_card('작성자 11 8 [모집중]소녀는 S에 빠진다 2026년 11월 8일 (일) 오후 1:00 ~ 온라인 참석여부 응답하기')
  self.assertEqual(e['start'],'2026-11-08T13:00:00+09:00');self.assertEqual(e['status'],'proposed');self.assertEqual(e['participants'],[])
  _,e=parse_card('12 26 (일정협의) 클리셰 2026년 12월 26일 (토) 오전 12:50 ~ 일정 확인하기');self.assertIsNone(e['start'])
 def test_cancel_and_invalid(self):
  _,e=parse_card('일정이 취소되었습니다. 10 12 데드컬트 2026년 10월 12일 (월) 오후 8:00 ~');self.assertEqual(e['status'],'cancelled')
  self.assertIsNone(parse_card('내일 만나요'));self.assertIsNone(parse_card('11 8 제목 2026년 11월 9일 (월) 오후 1:00'))
