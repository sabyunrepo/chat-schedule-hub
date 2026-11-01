---
name: collect-schedules
description: 카카오톡 Mac 앱과 Discord 웹의 지정 대화를 컴퓨터 유즈로 증분 수집하고 일정 허브에 반영한다. 실행 환경에 컴퓨터 유즈가 있어야 하며 방·기간이 지정되어야 한다.
---

# 일정 수집

플러그인 루트에서 `python3 -m hub.cli <command>`를 실행한다. JSON 입력은 stdin으로 전달한다. `HUB_DB` 미지정 시 사용자 앱 데이터 폴더를 사용한다. 비밀값은 인수나 로그로 전달하지 않는다.

1. `sources`로 지원 경로를 확인한다. 호스트가 제공하는 컴퓨터 유즈 도구 문서를 먼저 읽고, 없으면 `driver_unavailable`로 보고한다. 내부 엔드포인트나 Orca로 임의 대체하지 않는다.
2. 사용자가 허용한 계정·방·기간을 확인한다. 목록을 스크롤해 대상을 발견하되 가시 구간을 전체 목록으로 간주하지 않는다. 카톡 일반/오픈채팅과 Discord 서버/채널/스레드를 구분한다.
3. `register`에 target, adapter(kakao-mac/discord-web), connection, label, config:{since,until}를 전달한다. ID는 계정·서버·방 범위로 고정한다. `begin` 결과의 cursor/seen/baseline으로 미완료 실행을 먼저 재개한다.
4. UI로 실제 대상을 확인하고 페이지를 관찰한다. `ingest` 입력은 docs/SOURCE_ADAPTER_CONTRACT.md와 examples/batch.json을 따른다. 원본 ID를 볼 수 없으면 주변 문맥과 순서를 확인한 occurrenceKey를 만들고 identityQuality=verified-anchor를 사용한다. 식별이 불확실한 메시지는 임의 키로 중복 병합하지 말고 수집 공백으로 보고한다.
5. 메시지 컨테이너를 겹쳐 스크롤한다. 새 상태로 요소를 다시 찾고 로딩이 끝났는지 확인한다. 화면의 범위 밖 메시지는 배치에서 제외한다. 반복 문구 하나로 종료하지 않는다. ingest 결과 complete까지 반복하되 예산·사용자 중단 시 cursor와 stopReason을 저장한다.
6. 마지막 30일처럼 범위가 지정된 경우 실제 날짜 경계에 도달한 증거가 있어야 requested-range-reached와 coverageVerified=true를 보낸다. 스레드는 별도 target으로 처리한다. 가려진 메시지/첨부는 읽었다고 하지 않는다.
7. `pending`으로 분석 대기 메시지를 얻는다. 외부 API 처리가 허용된 범위만 `decide`로 분류한다. 필요한 앞뒤 맥락을 포함하고 결과를 자유 형식 날짜 추출로 오해하지 않는다. Codex가 원문에서 일정 후보를 추출해 `person`과 `apply`로 반영한다. 근거 revision ID와 expectedVersion을 반드시 전달한다. 불명확하면 needsReview=true로 둔다.
8. `sync`는 사용자가 설정한 개인 Sites에만 수행한다. API 키 설정 없이 분류를 실행한 척하지 않는다. UI 수집 완료, 분석 완료, 동기화 완료를 따로 보고한다.

카톡 전체방 요청은 방 목록 수집 후 각 방에 적용한다. 새 방은 새 target으로 등록한다. Discord 서버를 지정하면 접근 가능한 채널 목록을 확인하고 권한 없음·미열람을 구별한다. 스크롤 없는 단일 화면은 30일 수집 완료 증거가 아니다.
