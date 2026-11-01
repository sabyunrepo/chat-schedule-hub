import unittest
from hub.sources.kakao_ui import parse_window, progress

def window(body, title='Test', position='.3'):
    return f'Window: "{title}", App: 카카오톡.\n\t\t2 표\n\t\t\t3 row (selectable)\n{body}\n\t\t31 스크롤 막대 (settable, float) {position}'

class KakaoUiTests(unittest.TestCase):
    def test_empty_trailing_row_is_not_message_text(self):
        s=window('\t\t\t\t5 text 실제 메시지\n\t\t\t30 row (selectable)')
        self.assertEqual(parse_window(s)['rows'][0]['text'],'실제 메시지')

    def test_inline_schedule_card_not_dropped(self):
        s=window('\t\t\t\t5 text Help: 2026. 11. 1., Value: 99\n오전 11:35 표시이름 15분 후에 일정이 있습니다. 11 1 모임 2026년 11월 1일 참석여부 응답하기')
        r=parse_window(s)['rows'][0]
        self.assertEqual(r['sentAt'],'2026-11-01T11:35:00+09:00')
        self.assertTrue(r['text'].startswith('표시이름 15분 후'))

    def test_shallow_scrollbar_ends_message_table(self):
        s=window('\t\t\t\t5 text 실제 메시지').replace('\t\t31 스크롤','\t31 스크롤')+'\n\t40 텍스트 창 공지'
        self.assertEqual(parse_window(s)['rows'],[{'text':'실제 메시지','sentAt':None,'authorRef':None}])

    def test_numeric_body_continuations_are_preserved(self):
        s=window('\t\t\t\t5 text Help: 2026. 10. 27., Value: 1\n오후 3:39 표시이름\n\t\t\t\t6 텍스트 엔트리 영역 후보\n12월\n17\n\n1월\n6 12 13 19\n\t\t\t\t7 이미지')
        self.assertEqual(parse_window(s)['rows'][0]['text'],'후보\n12월\n17\n\n1월\n6 12 13 19')

    def test_inline_value_time(self):
        s=window('\t\t\t\t5 텍스트 Help: 2026. 10. 6., Value: 오전 9:23\n\t\t\t\t6 텍스트 엔트리 영역 변경 알림')
        self.assertEqual(parse_window(s)['rows'][0]['sentAt'],'2026-10-06T09:23:00+09:00')

    def test_card_time_is_not_message_time(self):
        s=window('\t\t\t\t5 텍스트 Help: 2026. 10. 14., Value: 74\n\t\t\t\t6 text 모임 2026년 11월 1일 오후 5:00')
        self.assertIsNone(parse_window(s)['rows'][0]['sentAt'])

    def test_explicit_time_and_unread_count(self):
        s=window('\t\t\t\t5 텍스트 Help: 2026. 10. 14., Value: 74\n오후 2:51\n\t\t\t\t6 text 일정 변경')
        self.assertEqual(parse_window(s)['rows'][0]['sentAt'],'2026-10-14T14:51:00+09:00')
        self.assertEqual(progress(s,s.replace('Value: 74','Value: 73'))['state'],'no-content-progress')

    def test_position_alone_does_not_confirm_progress(self):
        s=window('\t\t\t\t5 text 안녕')
        self.assertEqual(progress(s,s.replace('float) .3','float) .2'))['state'],'no-content-progress')
        self.assertFalse(progress(s,s)['advanceCheckpoint'])

    def test_room_change_and_diff_rejected(self):
        s=window('\t\t\t\t5 text 안녕')
        self.assertEqual(progress(s,s.replace('"Test"','"Other"'))['state'],'target-changed')
        with self.assertRaises(ValueError):parse_window('There has been no change')

    def test_input_and_banner_are_not_messages(self):
        s=window('\t\t\t\t5 text 실제 메시지')+'\n\t40 텍스트 엔트리 영역 (settable) 입력창\n\t41 텍스트 공지'
        self.assertEqual(parse_window(s)['rows'][0]['text'],'실제 메시지')

    def test_cli_excludes_quiet_before_parsing_or_model(self):
        import io,sys,tempfile,os,json
        from unittest.mock import patch
        from hub.cli import main
        with tempfile.TemporaryDirectory() as directory:
            data={'quiet':True,'since':'2026-10-02T00:00:00+09:00','externalProcessingAllowed':True,'observations':['invalid']}
            out=io.StringIO()
            with patch.dict(os.environ,{'HUB_DB':directory+'/test.sqlite'}),patch.object(sys,'argv',['hub','kakao-observe']),patch.object(sys,'stdin',io.StringIO(json.dumps(data))),patch.object(sys,'stdout',out),patch('hub.providers.providers.create') as provider:
                main()
            self.assertEqual(json.loads(out.getvalue())['state'],'excluded-quiet')
            provider.assert_not_called()
