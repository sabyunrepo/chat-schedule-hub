# Discord 정식 봇 — 제한 REST 파일럿 구현

Current runtime status (supersedes earlier pending Gateway status): [2026-11-01 continuous collection](../CONTINUOUS_COLLECTION.md).

사용자가 Discord 웹 UI에서 공식 bot API/Gateway로 전환을 승인했다. SourceRegistry에 등록하고 `hub/sources/discord_bot.py`의 인증·목록·한 페이지 수집·정규화를 공통 select-ingest에 연결했다. Gateway 상시 실행, 자동 30일 페이지 순회, 보관 스레드 탐색은 아직 미구현이다. 아래 항목은 목표 계약이며 현재 capability는 sources 출력이 기준이다. [상세 계획](../DISCORD_BOT_PLAN.md)을 따른다.

실행: `python3 -m hub.sources.discord_bot probe`. 제한 선별 파일럿: `python3 -m hub.sources.discord_bot pilot --guild GUILD_ID --channel CHANNEL_ID --allow-external-processing`. 기본 최대 16개, 최대 허용 32개이며 최근 30일 밖 메시지는 저장·AI 전송하지 않는다. 실제 ID/토큰은 사용자 앱 데이터 설정에만 둔다. 기본 파일럿 DB는 운영 DB와 분리한다. 전체 기간 완료를 선언하지 않는다. 같은 페이지 재전달의 캐시를 검증하며, 페이지 문맥 변화 시 전체 재분류하는 기존 캐시 한계는 남아 있다.

- transport: official-api, driver: discord.py worker.
- identity: connection/guild/channel/message ID. thread는 별도 target과 parentTargetId.
- history: 최초 30일 페이지 탐색. 활성/보관 스레드 목록은 독립적으로 탐색.
- resume: 대상별 ID 커서와 초기 수집 구간 상태. Gateway 연결 복원 실패 시 이력 보충.
- edits: raw update + 기존 revision/현재 본문 재조회. 부분 payload와 embed-only 변경 구분.
- deletions: 명시 이벤트만 삭제 증거. 오프라인 기간의 삭제·이전 수정 본문은 완전 복구 보장 불가.
- attachments: 메타데이터 우선. 해석하지 않은 파일/이미지는 누락 상태로 표시.
- permissions: 읽기 최소 권한과 Message Content Intent. 비공개 스레드 포함 봇이 볼 수 없는 범위는 미수집.
- cost: 코드가 발견/중복 제거/커서/큐를 관리하고 새 내용과 필요한 문맥만 Decisions에 전달.
- validation: 단일 채널·스레드에서 이력/이벤트/복구/누락/비용 검증 후 두 서버 전체 접근 범위로 확대.
