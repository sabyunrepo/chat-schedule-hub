# 자동화 연결 0.4.1

## 변경

- 추출 전용 Restricted Responses 키를 분리했다. `HUB_EXTRACTION_API_KEY`, `HUB_EXTRACTION_API_KEY_FILE`, 앱 데이터의 `openai-extraction.key` 순으로 사용하며, 없을 때만 기존 OpenAI 설정으로 돌아간다. 제작자 키는 배포하지 않는다.
- Mac 주기 수집의 `siteAccess: "macos-keychain"`은 사이트 origin에 묶인 서비스 자격 증명을 시스템 키체인에서 읽는다. Sites Git 배포 토큰과 별개다. 잠김·회수·인증 실패 시 미전송 데이터를 보존하며, 개인정보/비밀이 포함될 수 있는 오류 본문은 출력하지 않는다.
- 사이트 MCP: `schedule_status`, `schedule_list`, `schedule_attention`, `schedule_apply_delta`. Sites가 전달한 사용자 ID로 범위를 제한하며 변경분은 기존 v2 멱등 프로토콜을 재사용한다. MCP가 Mac 앱 제어 권한을 제공하지는 않는다.
- Web Push: 사용자 동작으로 구독, 사용자별 저장, 최대 20개 기기, 매 회 기기당 1개 알림, 5분 임대·최대 3회 재시도, 404/410 구독 제거. 수집기 15분 주기에 발송한다. 잠금 화면에는 개인 일정 내용을 보내지 않는다.

## 설치·운영

기존 Python 환경에 `requirements-mail.txt`를 설치한다. Mac에서는 `swiftc scripts/site-keychain.swift -o .runtime/site-keychain`으로 전용 도우미를 빌드한다. 시스템 키체인의 service는 `com.chatschedulehub.site-access`, account는 정확한 사이트 origin이다. 도우미 set 입력은 숨긴 stdin/프로세스 파이프로만 제공한다. 키를 argv·소스·임시 파일·로그에 넣지 않는다. 기존 키체인 항목을 사용할 때 도우미를 재빌드하면 macOS 재승인이 필요할 수 있다. Git 자격 증명은 여기에 저장하지 않는다.

`pipeline.json`의 `siteAccess`를 `macos-keychain`으로 설정하면 `python -m hub.pipeline`만으로 주기 전송한다. 서비스 키 만료/회수 시 Sites 연결에서 현재 서비스 인증을 받아 같은 항목을 갱신한다. 플랫폼에서 보장하지 않은 무기한 유효성을 가정하지 않는다. `--site-token-stdin` 수동 경로도 유지한다.

푸시는 `hub.push.public_key(root, create=True)`로 앱 데이터에 소유자 전용 VAPID 키를 최초 생성한 뒤 `pushEnabled:true`로 켠다. 같은 키를 재사용한다. 공개키가 서버 설정과 다르면 발송을 중단하며 임의 교체하지 않는다. 사이트의 `푸시 알림 켜기`를 기기마다 눌러 권한을 부여한다. iOS는 홈 화면 설치 앱이 필요할 수 있다.

Mac이 잠자기/오프라인이면 수집·알림이 멈춘다. 이 구조는 24시간 클라우드 수집기가 아니다. 발송 후 서버 ack 전 종료되면 재전달할 수 있으며 OS tag/Push Topic으로 표시를 합친다. 브라우저 권한, 절전·집중 모드에 따라 표시가 지연될 수 있다. 구독 갱신이 필요하면 앱에서 알림을 껐다 켠다.

## 확인된 범위

기존 키는 간헐 성공 후 401이 반복됐다. 새 전용 키로 합성 2회와 실제 Discord·카카오톡·메일 각 1건 추출을 통과했다. 카카오톡 결과는 일정 후보 없음으로 정상 종료했다. 다음 무인 접근 파이프라인에서 실제 수집·추출·증분 전송까지 성공했다. 캘린더 3개는 fetched/applied 0이며 메일은 페이지 크기 3으로 이어 수집했다. 전체 이력 완료를 뜻하지 않는다.

추출 키의 현재 운영 만료일은 2026-12-01이다. 교체 전 자동 추출 상태를 확인한다. 현재는 키 만료 사전 알림을 구현하지 않았다.

회귀: Python 99개, TypeScript, MCP 인증·사용자 격리·오류 비밀 보호, Push URL 제한, SQL 임대 경합·사용자 격리·오래된 ack·재시도 제한. 실제 휴대폰 잠금 중 푸시 수신과 Dot에서 새로 연결한 도구 호출은 별도 수용 확인이 필요하다.

공식 참고: [Apple Keychain](https://developer.apple.com/documentation/security/using-the-keychain-to-manage-user-secrets), [Push API](https://developer.mozilla.org/en-US/docs/Web/API/Push_API), [pywebpush](https://github.com/web-push-libs/pywebpush).


운영 사이트 배포 성공: MCP 선언을 플랫폼에서 확인했다. 개인 플러그인은 이미 설치된 상태이나 이 대화의 도구 목록에는 새 도구가 아직 나타나지 않았다. 새 Dot/ChatGPT 대화에서 도구 노출과 사용자 인증을 확인해야 한다. 서비스 인증만 넣은 운영 /mcp 요청은 플랫폼에서 HTTP 401로 거절했다. MCP는 개인 플러그인의 사용자 인증 연결을 통해 호출해야 한다. 서버의 사용자 ID 없는 도구 호출 거절은 단위 테스트로 확인했다.

운영 푸시 공개키 등록과 대기열 조회 성공. 아직 등록 기기가 없어 claimed/sent=0이며 수신 완료로 보고하지 않는다. 3개 소스 즉시 재전송은 모두 0건이었다.
