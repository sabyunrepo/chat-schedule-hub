# 상시 수집 현황 — 2026-11-01

이 문서는 이전 계획의 Gateway 미구현 상태를 대체한다. Discord 상시 감시는 실행 중이고 카카오톡은 파일럿 단계다.

## Discord

discord.py 2.7.1 Gateway로 두 서버에 연결했다. 신규·raw 수정·명시 삭제 이벤트를 ID 전용 SQLite 큐로 처리한다. 본문은 재조회 후 Decisions로 선별한다. 동일 의미·문맥 재전달은 모델 호출을 생략하고, 처리 중 들어온 수정은 generation으로 보존한다. live 처리는 미완료 이력 커서를 덮어쓰지 않는다.

- 실제 허용 메시지: 처리 1, 모델 호출 1, 보존 1, 오류 0.
- Gateway 강제 연결 종료 시험: 약 1초 후 RESUME, 불필요한 모델 호출 0.
- 두 서버에서 채널·활성 스레드 17개의 ID 조회 지점 기록. 과거 이력 완료 수가 아니다.
- 약 3분 40초 시점 CPU 0.0%, RSS 약 41MB, 큐 0, 오류 0, 유휴 모델 호출 0. 장기 부하 시험은 아니다.
- 전체 테스트 49개 통과. 실제 사용자 메시지 수정·삭제는 수행하지 않았고 상태 전이는 합성 검증했다.

사용자 LaunchAgent `com.chatschedulehub.discord`가 로그인 시 시작하고 비정상 종료 후 재시작한다. 설치는 `.runtime/discord-venv`에 requirements-discord.txt 설치 후 `python3 scripts/install-discord-service.py`로 한다. 비공개 설정에서 liveCollectionEnabled와 externalProcessingAllowed를 활성화해야 한다.

상태 파일: 사용자 Library/Application Support/ChatScheduleHub/discord-status.json. 중지 명령: `launchctl bootout gui/$(id -u)/com.chatschedulehub.discord`.

현재 initialHistoryEnabled=false. 15분마다 코드로 신규 ID와 최근 20개를 재확인한다. 과거 30일 전체 이력과 전체 보관·비공개 스레드는 미완료다. 오프라인 중 오래된 수정·삭제의 완전 복원은 보장하지 않는다. Mac 절전·종료 중에는 수집되지 않는다. 일정 추출 및 Sites 자동 동기화는 이 워커에 아직 연결하지 않았다.

## 카카오톡

실제 오픈채팅 모집방 읽기는 3.98~4.75초였다. 스크롤 전후 고유 연속 3행으로 40개 겹침을 확인했다. 추가 스크롤에서 접근성 행 수가 55에서 83으로 증가했으나 최초 30일 도달은 미확인이다. 발언 날짜와 카드의 모임 날짜는 구분해야 한다.

모집 완료 후 카드 취소·삭제 사례가 있다. 카드 취소를 실제 모임 취소로 단정하지 않는다.

`hub/sources/kakao_anchors.py`는 두 관찰의 고유 3행 겹침으로 발생 키를 유지한다. 원문 대신 지문과 키만 저장한다. 첫 관찰·모호한 반복·새 행은 미확인으로 남긴다. 합성 시험 5개 통과. 실제 UI 관찰을 이 모듈과 select-ingest에 자동 연결하는 작업, 수정 식별, 전체 방·30일 탐색은 미완료다. 이 보조 모듈의 상태는 수집 완료 체크포인트가 아니다.
