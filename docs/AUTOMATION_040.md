# 자동 반영·확인함·달력 0.4.0

## 구현과 실제 상태

- `hub.pipeline`: 기존 승인 소스만 단일 잠금 안에서 수집 → 후보 추출 → 명시 일정/메일 근거 → 증분 전송. 한 번에 처리할 메일·분석 작업 수를 설정한다. 카카오톡 새 UI 수집은 하지 않는다.
- Google Calendar: 기존 범위 -30일~+180일. syncToken을 받으면 사용하며, 현재 실제 bounded 조회에는 토큰이 없어 `updatedMin`으로 수정분 조회한다. 날짜 범위가 앞으로 이동하도록 하루마다 bounded refresh한다. 토큰 410이면 체크포인트만 초기화하고 일정/사람의 기록은 유지한다. 실제 캘린더 3개 재조회에서 fetched/applied 모두 0 확인.
- Gmail: 받은편지함의 고정 시각 범위와 pageToken을 저장한다. 저장·Decisions 성공 후만 커서를 전진한다. ID별 처리 여부로 본문 재조회/모델 호출을 줄인다. 하루 겹침을 사용하므로 그보다 오래된 메일을 나중에 받은편지함에 옮기는 동작과 삭제는 포괄하지 않는다.
- 네이버: INBOX 읽기 전용, BODY.PEEK, UIDVALIDITY+UID 오름차순. 최근 30일 초기 범위를 작은 페이지로 이어 읽는다. UIDVALIDITY 변경은 해당 범위를 재검증하며 원문 부재로 삭제하지 않는다.
- ExtractionProvider: Decisions 선별과 별도로 Responses 구조화 추출을 분리했다. 교체는 `extractors` 레지스트리로 한다. revision별 결과 캐시, 최대 3회 실패 재시도, 근거 발췌 검증. 후보는 제안/확인 필요/참여자 미확인으로만 생성한다. 다른 메시지의 일정과 임의 병합하거나 내 참석을 추정하지 않는다.
- 실제 추출은 **미완료**. 프로젝트 전용 키에 Responses Write를 저장했으나 검증 호출은 `api.responses.write` 401이 지속됐다. 운영 설정 `extractionEnabled=false`로 반복 실패 호출을 중지했다. 인증 복구 후 합성/제한 실데이터 검증을 통과하고 활성화해야 한다.
- 로컬 수집 LaunchAgent는 15분 간격으로 등록했다. Mac이 켜져 있어야 한다. 매 실행의 사이트 접근 토큰이 없으면 `awaiting_site_access`로 남기며 미전송 변경을 보존한다. **무인 사이트 전송까지 완료된 상태가 아니다.**

## 화면

- 확인함: 검토 후보와 내 확정 일정 중 시간이 겹치는 후보. 종료 시각 없는 일정·종일 일정은 시간 충돌로 단정하지 않는다. 공유 캘린더 타인의 일정은 내 중복 약속으로 보지 않는다.
- 의견·처리완료·문제없음·재열기를 owner별 D1에 저장한다. optimistic version으로 다른 기기 충돌을 차단하고 별도 감사 이력을 보존한다. 새 revision이면 이전 처리 기록을 유지하고 다시 표시한다. 처리완료는 원본 일정 확정/취소가 아니다.
- 알림: 이 배포 이후 사이트가 받는 일정 버전 변경과 내 확정 일정의 24시간/1시간 리마인더. 최초 수입을 변경 알림으로 만들지 않는다.
- `앱 열림 알림`: 명시적으로 알림 권한을 켠 세션에서 브라우저 알림을 제공한다. **앱 종료/휴대폰 잠금 중 푸시 보장은 미구현**이다. 알림 허용·실기기 전달은 별도 확인 대상이다.
- 월간 달력: 서울 시간 기준 월 이동, 사람·종류·상태 필터 저장, 날짜 선택 상세 목록, 좁은 화면에서는 날짜별 건수와 목록 사용.

## 실행

프로젝트 루트에서 `python -m hub.pipeline`을 실행한다. Python 3.13 환경의 `requirements-mail.txt`를 사용한다. `--site-token-stdin`은 `{ "siteAccessToken": "..." }`를 세션 메모리/stdin에서만 받는다. 파일·명령 인자에 토큰을 저장하지 않는다.

앱 데이터의 `pipeline.json`은 다음 키를 사용한다. 실제 계정·캘린더 ID는 패키지 밖에 둔다.

```json
{"sources":["discord","kakao","mail-calendar"],"externalProcessingAllowed":true,"extractionEnabled":false,"extractionProvider":"openai-responses","jobsPerSource":1,"gmail":true,"mailPageSize":3,"calendars":[]}
```

`naverAccount`를 설정하면 이미 연결한 네이버 앱 비밀번호를 재사용한다. `calendars` 항목은 `{id,kind,associateMe}`이며 공유 캘린더의 `associateMe`를 임의로 켜지 않는다.

`python scripts/install-pipeline-service.py`는 준비된 `.runtime/pipeline-venv`와 개인 설정으로 LaunchAgent를 등록한다. `launchctl bootout gui/$(id -u)/com.chatschedulehub.pipeline`로 중단할 수 있다. Discord Gateway 서비스와 별개다. 등록 시 즉시 추가 수집하지 않는다.

## 검증 및 제한

Python 회귀 테스트 94개, TypeScript, 빌드, 충돌 경계/본인 소유 테스트와 DB 마이그레이션·중복 전송·사용자 격리 검증 통과. 실제 확인함의 검토 중 저장과 월간 달력 조회를 확인했다. 서버에서 거절된 로컬 연결 키를 재발급·교체한 뒤 메일/Calendar 변경 레코드 5개를 전송했고, 즉시 반복은 전송 0건이었다. 실제 의견 내용이나 일정 확정 여부를 테스트 목적으로 변경하지 않았다.

Dot 업데이트 스킬은 재사용 가능하지만 이 세션의 브라우저 접근 호스트는 사용 불가였고 Dot 원격 실행을 입증하지 못했다. 로컬 수집·화면 배포·Dot 연결·푸시 전달을 구분한다.

공식 계약: [Calendar sync](https://developers.google.com/workspace/calendar/api/guides/sync), [Gmail 목록](https://developers.google.com/workspace/gmail/api/guides/list-messages), [구조화 출력](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses).
