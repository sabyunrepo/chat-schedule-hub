# 메일·캘린더 실제 연결

2026-11-01: Gmail·네이버 IMAP·Google Calendar 인증 및 제한 파일럿 성공. 상시 동기화는 아직 구현되지 않았다. 계획과 현황을 구분한다.

| 소스 | 조회 | 보안 메일 제외 | 저장 | 동일 입력 재처리 |
| --- | ---: | ---: | ---: | --- |
| Gmail INBOX | 10 | 1 | 근거 9개 | 신규 0, 모델 호출 0 |
| 네이버 INBOX | 10 | 6 | 근거 4개 | 신규 0, 모델 호출 0 |
| 기본 Google Calendar | 10 | 해당 없음 | 일정 10개 | 신규·변경·일정 반영 0 |

메일은 Decisions 선별 근거 저장까지이며 확정 일정 추출 완료가 아니다. Calendar는 구조화 일정을 공통 events/changes/outbox에 반영했다. 세 경로 모두 범위 전체 완료가 아니다. Calendar는 선택 기간의 첫 페이지이고 Gmail에도 후속 페이지가 있다. 네이버 최근 30일 검색은 43개를 반환했으며 그중 최근 10개를 확인했다. 실제 본문·계정·캘린더 ID·토큰은 저장소 밖에 있다.

## 설치와 인증

Google 경로는 Python 3.11 이상 가상환경을 권장한다. `python -m pip install -r requirements-mail.txt` 후 실행한다. 네이버는 표준 라이브러리를 사용한다.

기본 개인 경로: `~/Library/Application Support/ChatScheduleHub/`

- `google-client.json`: Desktop OAuth client JSON, 권한 0600.
- `google-token.json`: OAuth refresh/access token, 권한 0600, 런타임에서 갱신.
- `naver-app.key`: 네이버 앱 비밀번호, 권한 0600.
- `openai.key`: 기존 Decisions 키.
- `mail-calendar.sqlite`: 세 새 경로의 로컬 저장소. 카카오톡·Discord DB와 별개이며 같은 Store/선별/일정 코드를 사용한다.
- `google-calendars.json`: 실제 API로 확인한 선택 가능한 캘린더 목록, 권한 0600.
- `*-pilot-report.json`: 본문 없는 실행 결과.

```sh
python -u -m hub.sources.mail_calendar google-auth
python -m hub.sources.mail_calendar google-probe
python -m hub.sources.mail_calendar naver-probe --account YOUR_NAVER_ID
python -m hub.sources.mail_calendar gmail-pilot --limit 10 --allow-external-processing
python -m hub.sources.mail_calendar naver-pilot --account YOUR_NAVER_ID --limit 10 --allow-external-processing
python -m hub.sources.calendar_pilot --calendar primary --limit 10
```

인증 명령이 출력하는 Google URL을 Aside에서 열고 읽기 권한에 동의한다. 로컬 127.0.0.1 callback은 10분 안에 완료한다. Google Cloud 프로젝트 생성 한도로 이번 개인 파일럿은 기존 프로젝트에 별도 Moa Desktop 클라이언트를 만들었다. 기존 동의 화면 이름은 유지했다. 공개 플러그인의 자체 OAuth 배포·검증은 별도 작업이다.

네이버 IMAP/SMTP 사용 설정을 활성화했다. 클라이언트는 EXAMINE과 BODY.PEEK만 사용하고 SMTP는 연결하지 않는다. 공개 패키지에 계정/키를 넣지 않는다. 새 설치자는 자신의 앱 비밀번호를 로컬 비밀 저장소에 등록해야 한다.

## 제한과 다음 단계

- 현재 adapterVersion 0.1.0은 `bounded-pilot`, 동기화 커서 없음이다. 수집 반복 시 최근 페이지를 다시 조회할 수 있으나 같은 입력은 선별 캐시로 모델 호출을 생략한다. 이 기능을 historyId/syncToken/UID 증분 수집으로 설명하지 않는다.
- 메일은 최근 30일 INBOX 최대 20개만 처리한다. 개별 메일 1MB/정규화 본문 90KB를 넘으면 실패하고 완료로 표시하지 않는다. 첨부 본문과 원격 이미지는 읽지 않는다. 기본 보안 제목 제외 규칙은 모든 민감 정보를 찾아내는 분류기가 아니다.
- Calendar는 과거 30일~미래 180일 첫 페이지 최대 20개, 반복 일정은 API 전개 인스턴스를 사용한다. cancellation에 이전 일정이 없으면 gap으로 남긴다. 실제 수정·취소 이벤트 수신은 미검증, 합성 재수집/취소 검증만 통과했다.
- 공통 Store가 structuredPayload를 의미 지문에 포함한다. 기존 메시지 지문은 유지한다. Calendar는 별도 모듈에서 정규화해 같은 revisions/events/outbox로 연결하며 모델 추출을 생략한다.
- 웹에는 아직 새 데이터 동기화를 실행하지 않았다. 개인 Sites에 보내기 전 기존 데이터와 합쳐도 덮어쓰기/삭제가 없는지 확인하고 승인된 목적지·인증으로 동기화한다.
- 상시 확대 전 [계획](MAIL_CALENDAR_PLAN.md)의 전체 페이지 처리, 원자적 checkpoint, historyId/syncToken/UID, 취소 복구와 대상 선택을 구현해야 한다. 서비스 자동 실행은 등록하지 않았다.

## 검증

Python unittest 75개 통과. 신규 검증: 인증 파일 권한, HTML 정규화·스크립트 제외, 보안 메일 제외, 계정 격리, IMAP 읽기 전용 명령, 재전달 모델 호출 0, 캘린더 종일 종료·변경·취소·중복 반영 방지. 실제 인증과 파일럿은 위 표대로 별도 수행했다. 저장소 변경과 공개 릴리스/마켓 심사는 별개다.
