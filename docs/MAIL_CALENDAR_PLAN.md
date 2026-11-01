# Gmail·네이버 메일·Google Calendar 연결 계획

작성: 2026-11-01. 상태: 세 경로의 인증·제한 파일럿 구현 및 실제 검증 완료. 상시 증분 수집은 미구현. 최신 결과는 [실행 안내](MAIL_CALENDAR_RUNBOOK.md)를 따른다.
이 문서가 새 소스 범위의 기준이며 기존 카카오톡·Discord 실행 상태를 변경하지 않는다. 카카오톡은 사용자 요청에 따라 현재 수집량에서 멈추고 추가 순회를 하지 않는다.

Aside 실확인: Google 로그인·Calendar 화면 접근, 네이버 로그인·메일 환경설정 접근 성공. 이후 사용자 구현 요청으로 네이버 IMAP/SMTP를 사용함으로 저장하고 앱 비밀번호를 발급해 실제 인증했다.

## 연결 방식

| 소스 / 예정 adapterId | 연결 | 변경 수집 | 현재 확인 |
| --- | --- | --- | --- |
| Gmail / gmail-api | 공식 Gmail API, OAuth 읽기 권한 | historyId | Aside Google 로그인 확인. API 인증·파일럿 완료 |
| 네이버 / naver-imap | 공식 IMAP SSL, 앱 비밀번호 | 폴더별 UIDVALIDITY + UID | Aside 로그인·메일 접근 확인. IMAP 활성화·앱 비밀번호 인증·파일럿 완료 |
| Google Calendar / google-calendar-api | 공식 Calendar API, OAuth 읽기 권한 | 캘린더별 syncToken | Aside 캘린더 화면 접근 확인. API 인증·파일럿 완료 |

Aside는 계정·설정·동의 화면 확인에 사용한다. 상시 수집기는 웹 화면 반복 스캔이나 브라우저 쿠키 추출 대신 공식 API/IMAP을 쓴다. Aside 로그인은 플러그인 OAuth 연결 완료를 뜻하지 않는다. 현재 세션에 제공되는 Gmail 도구를 재배포 가능한 인증 수단으로 간주하지 않는다.

## Aside에서 연결하는 순서

1. Google Cloud 프로젝트를 선택하거나 전용 프로젝트를 만들고 Gmail API와 Calendar API를 활성화한다. 기존 다른 앱의 자격 증명을 재사용하지 않는다.
2. OAuth 앱 이름·지원 연락처·대상 사용자를 설정한다. 개인 파일럿은 테스트 사용자로 시작하고 로컬 수집기용 Desktop OAuth client를 만든다. 로컬 루프백 콜백, state 검증, 지원되는 PKCE 흐름을 구현한다.
3. Gmail은 `https://www.googleapis.com/auth/gmail.readonly`, Calendar는 `https://www.googleapis.com/auth/calendar.events.readonly`와 `https://www.googleapis.com/auth/calendar.calendarlist.readonly`만 요청한다. 기능별 동의를 분리할 수 있게 하고 부분 동의는 해당 연결에만 반영한다.
4. OAuth callback의 계정 식별자를 확인하고 refresh token은 OS Keychain 또는 앱 전용 0600 파일에 보관한다. 저장소·CLI 인자·로그·사이트 번들에는 넣지 않는다. 재인증/연결 해제와 수집 일시정지를 구분한다.
5. 네이버는 Aside 로그인 후 메일 환경설정 → POP3/IMAP 설정 → IMAP 사용 상태를 확인한다. 이미 켜진 설정을 껐다 켜지 않는다. 2단계 인증과 앱 비밀번호를 준비한다. 비밀번호는 채팅에 입력하지 않고 로컬 보안 입력으로 등록한다.
6. `imap.naver.com:993` TLS 인증서 검증 연결 후 폴더 목록과 읽기 접근만 검사한다. 네이버 앱 비밀번호 자체는 읽기 전용 범위가 아니므로 클라이언트에서 EXAMINE/read-only와 BODY.PEEK를 강제한다. SMTP 발송 기능은 구현하지 않는다.
7. 소스 연결 화면에서 계정 → 대상 → 기간 → 파일럿 → 활성화 순서로 진행한다. `연결 필요 / 권한 필요 / 검증 중 / 연결됨 / 재인증 / 일시정지 / 오류`를 구분한다. 등록만으로 연결됨을 표시하지 않는다.

Google 공개 배포는 개인 테스트 설정과 별개다. Gmail readonly는 restricted scope이므로 배포 형태·데이터 처리 위치에 따른 검증 요건을 확인한다. 테스트 상태 토큰 수명과 재인증은 운영 전 확인한다. 개인 파일럿의 client를 공개 패키지에 기본 자격 증명으로 넣지 않는다.

## 수집 범위와 실행 순서

제안 기본값이며 대상 선택과 최초 범위는 연결 설정에 명시한다.

- 메일: 최근 30일, 수신함 한 곳 최대 20개 파일럿. 통과 후 선택한 폴더/라벨로 확대. 스팸·휴지통·첨부 본문은 기본 제외, 보낸메일은 별도 선택. 읽지 않음 조건을 수집 커서로 사용하지 않는다.
- 캘린더: 기본 캘린더 하나에서 과거 30일~향후 180일 표시 범위로 파일럿. 실제 API 목록에서 안정적 ID를 선택한다. 공휴일·생일·공유 캘린더를 자동으로 전부 포함하지 않는다. 크라임씬용 캘린더는 사용자가 선택한 calendarId에 분류 규칙을 저장한다. 개인 캘린더 이름/ID는 공개 설정에 기록하지 않는다.
- 초기 동기화와 이후 변경 동기화를 분리한다. 5분 폴링으로 시작하고 서버 호출 제한·지연을 측정해 조정한다. 변경 없는 구간은 모델 호출 0회를 목표로 한다. Push/IDLE은 1차 필수가 아니다.
- 먼저 Google Calendar 정규화/동기화, 이어 Gmail, 마지막 네이버 순서로 구현·검증한다. OAuth 기반은 Google 두 경로가 공유한다. 실제 사용자 인증을 기다리는 동안 합성 검증과 네이버 전송 구현을 진행할 수 있다.

## 소스별 증분·복구

### Gmail

초기 historyId를 먼저 확보하고 지정 기간의 messages.list 페이지를 처리한 뒤 baseline 이후 history를 재생해 초기 수집 중 도착한 메일을 놓치지 않는다. 계정 + message.id가 원본 ID이며 threadId는 맥락 그룹이다. 여러 라벨에서 같은 메일을 다시 저장하지 않도록 계정 단일 논리 target으로 통합한다.

historyId는 연속 숫자가 아니므로 임의 증가하지 않는다. 모든 페이지 저장 후 반환된 최종 historyId를 커밋한다. 만료 404는 선택 범위 제한 재동기화와 공백 기록으로 처리한다. 라벨 이동·읽음 변경은 본문 수정으로 모델에 재전송하지 않는다. 답장은 새 메시지로 처리하고 필요한 스레드 맥락만 보완한다. 삭제된 메일을 모임 취소로 해석하지 않는다.

### 네이버 IMAP

폴더 + UIDVALIDITY + UID를 원본 식별자로 사용한다. 메시지 순번은 커서가 아니다. UIDVALIDITY 변경은 기존 UID 재사용으로 간주해 제한 재동기화한다. UID 범위 조회 뒤 실제 반환 UID가 저장된 경우만 커서를 전진시킨다. 빈 범위를 임의로 완료 처리하지 않는다.

폴더 이동은 새 UID가 될 수 있다. Message-ID는 없는 경우·충돌 가능성을 고려한 연결 후보이며 단독으로 강제 병합하지 않는다. 서버 CAPABILITY 확인 전 IDLE/CONDSTORE/QRESYNC 지원을 가정하지 않는다. 삭제는 명시적 VANISHED 또는 성공한 범위 대조로만 기록하고 접속 실패를 삭제로 처리하지 않는다.

MIME plain/html을 안전한 텍스트로 변환한다. remote image·외부 링크를 자동으로 불러오지 않는다. 크기/파트 수 제한과 디코딩 오류를 기록한다. INTERNALDATE와 메일 Date 헤더를 구분하고, 상대 날짜 해석에 불명확한 시각을 꾸미지 않는다. 첨부와 ICS는 후속 단계다.

### Google Calendar

calendarId + event.id로 식별하고 etag/updated와 의미 필드의 지문으로 수정 이력을 추적한다. 모든 페이지 저장 뒤 마지막 nextSyncToken을 커밋한다. 증분 요청에 금지된 timeMin/timeMax/orderBy 등 필터를 섞지 않는다. 초기 쿼리 정책을 커서와 함께 고정한다.

표시 범위와 동기화 범위를 분리한다. 반복 master/예외를 보존하는 동기화 정책을 먼저 검증하고 표시 기간의 인스턴스는 별도 제한 조회/전개한다. 시간이 흘러 미래 일정이 표시 범위에 진입하는 경우에도 누락되지 않도록 범위 확장 작업을 둔다. 기간 필터만 이동시키면서 기존 syncToken을 재사용하지 않는다.

410은 해당 계정·캘린더의 소스 캐시만 재구축한다. 사람의 검토 의견·처리완료 이력·다른 소스 근거는 삭제하지 않는다. 재구축 완료 전에 기존 일정이 모두 취소된 것처럼 표시하지 않는다.

status=cancelled, 반복 예외(originalStartTime/recurringEventId), 종일 날짜의 exclusive end, 원래 시간대를 보존한다. 정보가 제한된 busy 일정에 제목·참여자를 추정해 넣지 않는다. 공개 휴일을 특정 인물의 약속으로 처리하지 않는다.

## 공통 파이프라인에 붙이는 방법

`SourceRegistry → 연결 probe → 대상 선택 → SourceAdapter.collect → 공통 저장/선별 → 일정/변경 이력 → 기존 SQLite/outbox → Sites D1`

- 신규 메일은 기존 MessageObservation과 select-ingest를 사용한다. Decisions는 일정·비교 가능한 사실·정정·필요한 답글만 보존한다. 인증번호·비밀번호 재설정 등 명확한 보안 메일은 로컬 제외 규칙을 우선 적용하고 본문을 모델에 보내지 않는다. 제목 키워드만으로 모든 일정 메일을 탈락시키지 않는다.
- 캘린더는 `CalendarObservation`을 공통 입력의 별도 타입으로 추가해야 한다. 시작 시각을 메시지 sentAt에 억지로 넣지 않는다. structuredPayload가 revision 지문에 포함되도록 저장 계약과 검증을 함께 확장한다. 현재 구현은 sentAt=None인 공통 관찰에 structuredPayload/contentKind를 넣으며 revision 지문 확장까지 완료했다. 독립 CalendarObservation 타입 분리는 후속 작업이다.
- 캘린더의 날짜·장소·상태는 결정적으로 정규화한다. Decisions는 모임 연결·크라임씬 분류·착오 검토 후보 판단에만 사용한다. 매 폴링마다 변하지 않은 일정을 재분석하지 않는다.
- 메일 초대와 Calendar의 iCalUID/주최자/반복 인스턴스는 동일 모임 후보 연결에 사용하되 원본 근거는 각각 유지한다. 제목과 시간만 같다고 강제 병합하지 않는다. 캘린더 취소·메일 삭제·개인 불참을 구분한다.
- 계정별 불투명 connectionId, 대상별 cursor를 사용하고 메일/캘린더 커서와 카톡 경계를 공유하지 않는다. 수집·분석·웹 동기화 지점은 분리한다.
- 기존 SQLite와 Sites D1이면 충분하다. 새 DB 서비스는 추가하지 않는다. 추후 source_connections, source checkpoints, calendar revisions를 마이그레이션하고 `(connection_id,target_id,origin_id)` 고유키와 변경 큐 인덱스를 둔다.

## 추가 소스 작업 체크리스트

1. `.agents/skills/add-collection-source/SKILL.md`와 공통 계약을 읽는다.
2. `docs/sources/<adapter-id>.md`에 인증·capability·ID·수정/삭제·커서 손실·한계를 작성한다.
3. `hub/sources/<adapter>.py`에 전송/정규화만 구현한다. 공통 저장·AI·일정 엔진을 복제하지 않는다.
4. 설정 검증과 비밀 참조, probe, listTargets, bounded collect를 구현한 뒤 `hub/core.py`의 SourceRegistry에 등록한다. 계획 상태를 실행 가능한 adapter로 미리 등록하지 않는다.
5. 공통 타입 확장 및 SQLite migration을 작성하고 기존 소스 회귀를 확인한다.
6. 테스트 통과 후 계정/대상 하나로 파일럿, 이후 연결 화면과 배포 스킬에 노출한다.

## 완료 기준

- 합성: 페이지 중간 실패/재개, 저장 실패 시 커서 유지, 재전달 중복 0, 같은 ID의 다른 계정 격리, OAuth 만료/부분 동의, Gmail 404, Calendar 410, IMAP UIDVALIDITY 변경.
- 의미: 캘린더 반복/종일/이동/취소, 메일 답장/라벨 이동, 삭제와 약속 취소 구분, 검토 의견 보존.
- 실제: 선택 대상 최대 20개로 UI와 결과 대조, 신규·중복·누락·소요 시간·모델 호출 수 기록. 이메일 읽음 상태 변화 없음 확인. 두 번째 변경 없는 실행의 신규 저장·모델 호출 0 확인.
- 공개 패키지: 개인 ID/본문/토큰 제외, 스킬 링크 확인, OAuth 배포 요건 확인. 사이트 배포·PWA 설치와 별개로 기록.

## 공식 근거

- [Gmail 동기화](https://developers.google.com/workspace/gmail/api/guides/sync)
- [Gmail 권한 범위](https://developers.google.com/workspace/gmail/api/auth/scopes)
- [Google OAuth 설정](https://developers.google.com/workspace/guides/configure-oauth-consent)
- [Calendar 권한](https://developers.google.com/workspace/calendar/api/auth)
- [Calendar 증분 동기화](https://developers.google.com/workspace/calendar/api/guides/sync)
- [Calendar events.list 제약](https://developers.google.com/workspace/calendar/api/v3/reference/events/list)
- [네이버 IMAP 서버 설정](https://help.naver.com/service/30029/contents/21351?lang=ko&osType=COMMONOS)
- [네이버 2단계 인증·앱 비밀번호 의무화](https://help.naver.com/notice/noticeView.help?lang=ko&noticeNo=22533&page=1&serviceNo=30029)
