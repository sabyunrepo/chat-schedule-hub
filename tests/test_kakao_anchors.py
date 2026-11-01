import unittest
from hub.core import Store
from hub.sources.kakao_anchors import KakaoAnchors

class KakaoAnchorTests(unittest.TestCase):
 def setUp(self):self.s=Store(':memory:');self.a=KakaoAnchors(self.s.db)
 def rows(self,*texts):return [{'text':x,'sentAt':None,'authorRef':None} for x in texts]
 def test_first_view_not_verified(self):
  r=self.a.observe('room',self.rows('a','b','c'));self.assertEqual(r['messages'],[])
 def test_dated_revisit_preserves_keys_after_unrelated_window(self):
  rows=[{**r,'sentAt':'2026-11-01T10:00:00+09:00'} for r in self.rows('a','b','c','d')]
  self.a.observe('room',rows);first=self.a.observe('room',rows)
  self.a.observe('room',self.rows('x','y','z'))
  revisited=KakaoAnchors(self.s.db).observe('room',rows)
  self.assertEqual([m['occurrenceKey'] for m in first['messages']], [m['occurrenceKey'] for m in revisited['messages']])
  self.assertEqual(revisited['matchedRows'],4)
  self.assertNotIn('2026',str([tuple(r) for r in self.s.db.execute('SELECT * FROM kakao_anchor_history')]))
 def test_undated_revisit_remains_unconfirmed(self):
  rows=self.rows('a','b','c');self.a.observe('room',rows);self.a.observe('room',rows)
  self.a.observe('room',self.rows('x','y','z'))
  self.assertEqual(self.a.observe('room',rows)['messages'],[])
 def test_reordered_page_cannot_use_history(self):
  rows=[{**r,'sentAt':'2026-11-01T10:00:00+09:00'} for r in self.rows('a','b','c','d','e','f')]
  self.a.observe('room',rows);self.a.observe('room',rows)
  self.assertEqual(self.a.observe('room',rows[3:]+rows[:3])['messages'],[])
 def test_overlap_preserves_occurrence_and_waits_for_new_rows(self):
  self.a.observe('room',self.rows('a','b','c','d'))
  verified=self.a.observe('room',self.rows('a','b','c','d'))
  shifted=self.a.observe('room',self.rows('b','c','d','e'))
  self.assertEqual([m['occurrenceKey'] for m in shifted['messages']],[m['occurrenceKey'] for m in verified['messages'][1:]])
  self.assertEqual(shifted['unconfirmed'],1)
 def test_repeated_words_cannot_be_anchor(self):
  self.a.observe('room',self.rows('네','네','네','네'))
  self.assertEqual(self.a.observe('room',self.rows('네','네','네','네'))['messages'],[])
 def test_room_scope_and_no_plaintext_persistence(self):
  self.a.observe('one',self.rows('private a','private b','private c'))
  self.assertEqual(self.a.observe('two',self.rows('private a','private b','private c'))['messages'],[])
  raw=str([tuple(x) for x in self.s.db.execute('SELECT * FROM kakao_windows')]);self.assertNotIn('private',raw)
 def test_edit_is_not_claimed_as_same_message(self):
  self.a.observe('room',self.rows('a','b','c','d','e'))
  result=self.a.observe('room',self.rows('a','b','changed','d','e'))
  self.assertFalse(result['editsIdentifiable']);self.assertFalse(result['coverageVerified'])
  self.assertEqual(result['messages'],[])
