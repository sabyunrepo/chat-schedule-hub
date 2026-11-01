# 네이버 IMAP — 제한 파일럿

런타임 등록·실제 인증·제한 파일럿 완료. 상시 증분 수집은 미완료. [실행 안내](../MAIL_CALENDAR_RUNBOOK.md)에 검증 결과와 한계를 기록했다.

imap.naver.com:993 TLS. 앱 비밀번호, read-only EXAMINE/BODY.PEEK, 폴더별 UIDVALIDITY/UID. 웹 로그인과 IMAP 인증은 별개다.

인증 절차, 수집 범위, capability 제한, 공통 입력 확장, 체크포인트와 수용 기준은 [메일·캘린더 연결 계획](../MAIL_CALENDAR_PLAN.md)을 따른다. 어댑터 구현 후 해당 검증 결과를 이 문서에 추가한다.
