---
name: collect-schedules
description: 모아 일정 허브에 카카오톡 UI, Discord 봇, Gmail·네이버 메일, Google Calendar의 허용된 데이터를 수집하고 근거·일정·동기화 상태를 구분해 반영한다.
---

# 일정 수집

플러그인 루트에서 실행한다. 사용자별 데이터와 자격 증명은 패키지 밖 앱 데이터에 둔다. 현재 대화에서 승인된 계정·대상·기간과 중단 요청을 우선한다. 수집·분석·사이트 동기화·전체 범위 완료를 별개로 보고한다.

## 경로 선택

- 카카오톡: [UI 복구 절차](../../docs/KAKAO_UI_RECOVERY.md), `hub.sources.kakao_ui`, `kakao_collection`, `kakao_anchors`를 사용한다. 호스트 컴퓨터 유즈가 필요하다. 도구가 없으면 `driver_unavailable`; 비공개 API/다른 드라이버로 몰래 대체하지 않는다.
- Discord: 기본은 정식 봇이다. [운영 안내](../../docs/CONTINUOUS_COLLECTION.md)와 [봇 계약](../../docs/sources/discord-bot.md)를 읽는다. 웹 경로는 이전 파일럿이며 자동 확대하지 않는다.
- Gmail·네이버·Calendar: [메일·캘린더 실행 안내](../../docs/MAIL_CALENDAR_RUNBOOK.md)를 읽고 `connect-mail-calendar` 스킬을 따른다. 현재 제한 파일럿이며 상시 커서 동기화를 지원한다고 말하지 않는다.
- 새 소스: `add-collection-source` 스킬과 [공통 계약](../../docs/SOURCE_ADAPTER_CONTRACT.md)을 따른다.

## 카카오톡 관찰과 재개

1. `python3 -m hub.cli sources`로 경로를 확인한다. `register`에는 계정 범위 target, adapter, connection, label, config:{since,until}를 JSON stdin으로 전달한다. `begin`의 cursor/seen/baseline으로 미완료 구간을 먼저 재개한다.
2. 조용한 채팅방 보관함과 최근 지정 기간 비활동 방을 본문/모델 처리 전에 제외한다. 상태 미확인은 비활동으로 단정하지 않는다. 일반방·오픈채팅 목록의 가상 스크롤을 처리한다.
3. 실제 방 이름을 확인하고 전체 AX 관찰 두 개를 `kakao-observe`로 전달한다. 표시 인덱스·읽지 않은 인원은 메시지 ID가 아니다. 카드 안 모임 시각을 발언 시각으로 쓰지 않는다. 날짜 구분선과 날짜별 기존 앵커를 함께 사용한다.
4. 한 명만 GUI를 조작한다. 요소 스크롤 실패 시 최신 화면에서 확인한 좌표로 복구하고, 실제 화면 변화와 저장 결과를 확인한다. 무변화·창 이동·로그인·복원 대기·권한 오류는 완료 증거가 아니다.
5. 화면을 겹쳐 관찰한다. 원본 ID가 없으면 검증된 occurrenceKey만 사용하고, 같은 짧은 문구 하나로 중단하지 않는다. 이전 저장 위치에 도달해도 중간 공백이 있으면 먼저 메운다.
6. 기본 저장은 최대 32개 `select-ingest`. 외부 처리 승인 범위만 Decisions에 보낸다. 실패 시 해당 구간 체크포인트를 전진시키지 않는다. `requested-range-reached`는 날짜 경계의 실제 증거가 있을 때만 사용한다.

## 선별·일정 반영

- `hub.selection.RULE_VERSION`을 실행 시 확인한다. 숫자를 스킬에 고정하지 않는다. 보존 정책이 호환되지 않는 실행만 명시적으로 restart한다.
- 일정뿐 아니라 사실·조건·정정·개인 불참과 필요한 답글을 보존한다. 이미지·첨부 미해석은 별도 공백이다. 모임 전체 취소와 한 사람 불참을 구별한다.
- replyToRef는 `{targetId,identity}`로 실제 확인한 값만 전달한다. evidenceGaps가 있으면 범위 완료로 선언하지 않는다. 날짜·작성자가 없으면 null, 관찰 시각을 발언/수정 시각으로 꾸미지 않는다.
- `pending`에서 이미 저장된 decision을 재사용한다. 메일·대화의 Decisions 의도 분류를 일정 추출 완료로 혼동하지 않는다. 근거 revision과 expectedVersion을 사용해 `person`, `apply`로 일정을 반영한다. 불확실하면 검토 필요로 남긴다.
- Calendar 파일럿은 구조화 입력을 같은 revisions/events/outbox로 반영한다. 사람의 의견·처리완료 기록을 수집으로 덮어쓰지 않는다.
- `sync`는 [증분 동기화 계약](../../docs/INCREMENTAL_SYNC.md)에 따라 설정된 개인 Sites에만 수행한다. 여러 로컬 DB를 잘못 동기화해 기존 일정을 덮어쓰지 않도록 설치 ID·sequence·병합 동작을 먼저 확인한다.

## 보고

관찰/제외/보존/신규/변경/중복/공백, 실제 범위, 종료 이유, 모델 호출·지연을 본문 없이 보고한다. 파일럿이 통과해도 미수집 스레드·폴더·페이지가 있으면 전체 완료가 아니다. 새 인증이나 사용자 확인이 필요하면 준비된 구체적 화면과 이유만 안내하고 다른 독립 작업은 계속한다.

Dot 원격 실행 검토와 설정은 [Dot 안내](../../docs/DOT_REMOTE_COLLECTION.md)를 따른다. 실제 로컬 연결을 확인하기 전 원격 수집 완료로 보고하지 않는다.
