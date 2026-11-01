import unittest
from hub.core import Store, digest
from hub.sources.kakao_collection import filter_rows
from hub.sources.kakao_anchors import KakaoAnchors
from hub.sources.kakao_ui import parse_window
class Safety(unittest.TestCase):
 def test_counts_and_gap(self):
  start='2026-10-02T17:00:00+09:00'; end='2026-11-01T17:00:00+09:00'
  def r(text,date=start,**kw):return dict(text=text,sentAt=date,authorDisplayName='A',reviewedSchedule=True,**kw)
  rows=[r('모임 시간'),r('송금 결제'),r('모임 장소'),r('모임 변경'),r('과거',date='2026-10-01T00:00:00+09:00'),r('날짜없음',date=None),dict(text='확인',sentAt=end,authorDisplayName='A',reviewedSchedule=False),dict(text='모임',sentAt=end)]
  filtered,counts=filter_rows(rows,start,end)
  self.assertEqual(counts,dict(period=1,financial=1,undated=1,non_schedule=1,hold=1,allowed=3))
  self.assertEqual(sum(counts.values()),len(rows))
  s=Store(':memory:');a=KakaoAnchors(s.db)
  self.assertEqual(a.observe('t',filtered)['matchedRows'],0)
  self.assertEqual(a.observe('t',filtered)['matchedRows'],0)
  raw=str([tuple(x) for x in s.db.execute('SELECT * FROM kakao_windows')])
  for row in [rows[1],rows[4],rows[5]]:
   self.assertNotIn(row['text'],raw)
   self.assertNotIn(digest({k:row.get(k) for k in ('text','sentAt','authorRef','authorDisplayName','contentKind')}),raw)
 def test_author_explicit_only(self):
  s='Window: "T", App: 카카오톡.\n\t\t2 표\n\t\t\t3 row\n\t\t\t\t4 text Help: 2026. 10. 8., Value: 오후 6:54 작성자\n\t\t\t\t5 텍스트 엔트리 영역 모임\n\t\t6 스크롤 막대 (settable, float) 1'
  self.assertEqual(parse_window(s)['rows'][0]['authorDisplayName'],'작성자')
 def test_cli_reviewed_end_to_end(self):
  import io,sys,os,json,tempfile,sqlite3
  from unittest.mock import patch
  from hub.cli import main
  class Provider:
   name='test';model='test'
   def classify_page(self,messages,indices,context):return {i:{'intent':'schedule','relevance':1,'confidence':1} for i in indices}
  rows=[{'text':'모임 일정 '+str(i),'sentAt':'2026-10-10T09:00:00+09:00','authorDisplayName':'시험','reviewedSchedule':True} for i in range(3)]
  data={'target':'synthetic','label':'fixture','observations':[rows,rows],'latest':'2026-10-10T09:00:00+09:00','quiet':False,'since':'2026-10-02T00:00:00+09:00','until':'2026-11-01T00:00:00+09:00','externalProcessingAllowed':True}
  with tempfile.TemporaryDirectory() as d:
   out=io.StringIO()
   with patch.dict(os.environ,{'HUB_DB':d+'/test.sqlite'}),patch.object(sys,'argv',['hub','kakao-reviewed']),patch.object(sys,'stdin',io.StringIO(json.dumps(data))),patch.object(sys,'stdout',out),patch('hub.providers.providers.create',return_value=Provider()):main()
   result=json.loads(out.getvalue()); self.assertEqual(result['matched'],3)
   self.assertEqual(sqlite3.connect(d+'/test.sqlite').execute('select count(*) from messages').fetchone()[0],3)
 def test_all_held_does_not_modify_existing_state(self):
  from hub.sources.kakao_collection import collect
  s=Store(':memory:'); a=KakaoAnchors(s.db)
  rows=[{'text':'일정 '+str(i),'sentAt':'2026-10-10T09:00:00+09:00','authorRef':None} for i in range(3)]
  a.observe('t',rows);a.observe('t',rows)
  before=[tuple(x) for x in s.db.execute('select * from kakao_windows')]
  history=[tuple(x) for x in s.db.execute('select * from kakao_anchor_history')]
  result=collect(s,'t','fixture',[rows,rows],'2026-10-10T09:00:00+09:00',False,'2026-10-02T00:00:00+09:00','2026-11-01T00:00:00+09:00',None)
  self.assertEqual(result['state'],'held')
  self.assertEqual(before,[tuple(x) for x in s.db.execute('select * from kakao_windows')])
  self.assertEqual(history,[tuple(x) for x in s.db.execute('select * from kakao_anchor_history')])
  self.assertEqual(s.db.execute('select count(*) from runs').fetchone()[0],0)
  self.assertEqual(a.observe('t',[None,None,None])['matchedRows'],0)
  self.assertEqual(before,[tuple(x) for x in s.db.execute('select * from kakao_windows')])
 def test_preexisting_authorless_anchor_keys_survive_author_field(self):
  s=Store(':memory:');a=KakaoAnchors(s.db)
  rows=[{'text':'synthetic '+str(i),'sentAt':'2026-10-10T09:00:00+09:00','authorRef':None} for i in range(3)]
  a.observe('t',rows); old=a.observe('t',rows)
  fresh=[dict(row,authorDisplayName='synthetic author') for row in rows]
  new=a.observe('t',fresh)
  self.assertEqual([x['occurrenceKey'] for x in old['messages']],[x['occurrenceKey'] for x in new['messages']])
 def test_empty_observations_do_not_write(self):
  from hub.sources.kakao_collection import collect
  s=Store(':memory:')
  r=collect(s,'t','fixture',[[],[]],'2026-10-10T09:00:00+09:00',False,'2026-10-02T00:00:00+09:00','2026-11-01T00:00:00+09:00',None)
  self.assertEqual(r['state'],'held')
  self.assertEqual(s.db.execute('select count(*) from targets').fetchone()[0],0)
