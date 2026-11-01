# ChatGPT Dot 원격 수집 검토

확인: 2026-11-01. **가능한 구성은 확인했으나 이 계정의 Dot 연결/실제 원격 실행은 미검증**이다.

## 권장 구조

Dot 지시 → 연결된 Mac의 Codex 작업 → 이 프로젝트의 로컬 수집기/DB → 개인 Sites 증분 동기화.

Dot은 자체 클라우드 컴퓨터가 있다. ChatGPT 데스크톱 앱에서 Dot 프로필 → Computers → Your computer → Allow access로 로컬 컴퓨터를 연결하면 로컬 Work/Codex 작업, 스킬, 브라우저를 사용할 수 있다. Mac은 온라인이고 ChatGPT 앱이 열려 있어야 한다. Codex 연결이나 Work Sync만으로 Dot 접근이 허용되지는 않는다.

- 카카오톡: 이 Mac의 앱 로그인·복원 상태·접근성/화면 권한·실제 GUI 입력 경로가 필요하다. 클라우드 브라우저만으로 수집할 수 있다고 가정하지 않는다. 현재 추가 수집 중단 요청을 유지한다.
- Discord: 기존 정식 봇을 계속 실행하고 Dot은 상태 확인·복구·수동 갱신을 지시한다. 매번 에이전트가 서버/채널을 순회하는 방식으로 바꾸지 않는다.
- Gmail/네이버/Calendar: 현재 인증은 Mac의 개인 파일에 있다. Dot의 로컬 작업에서 재사용할 수 있는지 probe로 확인한다. 현재 bounded pilot 한계를 유지한다. 기존 Google 연결 플러그인은 Dot과 권한을 공유할 수 있지만 로컬 OAuth 파일이 클라우드에 자동 복사된다는 뜻이 아니다.
- Sites: 설치된 Sites 연결과 현재 접근 권한으로 사이트 서비스 접근 토큰을 받아 세션 메모리/stdin으로 전달한다. 키를 프롬프트·저장소에 넣지 않는다. 0.4.1부터 사이트 MCP를 제공한다. 최신 연결은 AUTOMATION_041.md를 따른다. 만료 토큰만으로 무기한 무인 동기화를 보장하지 않는다.

## Dot에 전달할 작업 예시

> 연결된 Mac에서 `/Users/sabyun/chat-schedule-hub`의 AGENTS.md와 skills/collect-schedules/SKILL.md, docs/INCREMENTAL_SYNC.md를 읽어. 기존 Discord 봇과 수집 DB 상태를 확인하고, 허용된 새 변경분만 처리해서 개인 모아 사이트에 증분 반영해. 카카오톡 추가 수집은 재개하지 말고 메일/캘린더는 기존 제한 파일럿 범위를 유지해. 다른 사람에게 메시지를 보내거나 외부 일정/메일을 수정하지 마. 신규/변경/중복/미확인과 실제 전송 건수를 보고해.

예약 실행은 단발 실제 실행이 통과한 후 사용자가 주기를 정했을 때 등록한다. 중복 실행 방지·GUI 단일 실행·실패 재시도·인증 만료·오프라인 복구를 검증한다. Dot의 proactive research 자체가 항상 브라우저/컴퓨터를 제어할 수 있다는 뜻은 아니다. 명시한 작업/예약과 해당 실행의 권한을 확인한다.

## 실제 검증 순서

1. 사용자 직접 로컬 접근 허용 → Dot이 프로젝트 지침을 읽는 단발 작업.
2. 비밀값 없이 probe, DB 상태·봇 상태 확인.
3. 소규모 변경 1건을 처리하고 재실행 0건 전송 확인.
4. 필요할 때만 카카오톡 재개 승인 후 GUI 단일 방 검증.
5. 그 다음 예약 실행. 이 문서 작성 시 예약·권한 변경은 수행하지 않았다.

공식 근거: [Dot 시작하기](https://help.openai.com/en/articles/20001530-getting-started-with-your-dot), [Dot 권한과 안전](https://help.openai.com/en/articles/20001529-dots-privacy-security-and-safety-faqs). 제품 지원과 실제 사용자 계정 활성화는 별개다.

## 실행 가능한 업데이트 스킬 (0.3.3)

[update-schedules](../skills/update-schedules/SKILL.md)를 플러그인에 포함했다. 별도 MCP 등록 없이 연결된 Mac의 로컬 실행 능력을 사용하는 경로다. 이 업데이트는 Dot의 계정 권한이나 전역 설정을 바꾸지 않는다.

```sh
python3 -m hub.update status
python3 -m hub.update materialize
```

`~/Library/Application Support/ChatScheduleHub/update.json`에는 `{"siteOrigin":"https://YOUR-PRIVATE-SITE"}`만 설정한다. `site-sync.key`는 권한 600으로 별도 보관한다. `sync` 명령은 Sites 도구에서 받은 접근 토큰을 JSON stdin의 `siteAccessToken`으로 읽는다. 토큰을 붙여 넣는 셸 명령이나 파일을 만들지 않는다. 접근 토큰 획득 도구가 없는 호스트에서는 동기화 단계가 차단될 수 있다.

Dot 요청 예시:
> 연결된 Mac의 모아 플러그인에서 update-schedules 스킬을 사용해 상태를 확인하고 저장된 일정 변경분을 내 사이트에 반영해. 실제 전송과 남은 미분석을 구분해 알려줘.

이 명령은 신규 수집·일반 대화 추출을 자동 완료하지 않는다. 새 수집은 collect-schedules로 연결한다. 현재 추가 카카오톡 순회는 중단 상태다. 업데이트 명령끼리는 같은 OS 잠금을 사용하지만 Gateway 수집기는 SQLite 트랜잭션으로 병행한다. 프로세스 종료 시 잠금은 해제되며 잠금 파일을 삭제하지 않는다.

검증: 합성 잠금 충돌/실패 해제/미설정 소스/토큰 누락 테스트와 실제 DB 상태 조회·로컬 반영 2회 성공. 두 차례 모두 신규 반영 0건. 동기화 명령도 실제 3개 DB에서 성공했으며 변경 없음으로 HTTP 요청·전송 각각 0건이었다. 이 결과는 새로운 인증이나 실제 전송의 검증은 아니다. 실제 Dot에서 스킬을 찾아 실행하는 수용 검증은 미완료다.
