# REA 설치와 ChatGPT 실제 화면 분석

2026-11-01. 원본: https://github.com/morluto/rea (MIT).
프로젝트 스킬은 upstream e18594b24754ab95ebd119311cc32a1d1ad6fa13에서 설치했다.
CLI는 rea-agents 6.8.0, 격리된 Node 26.12.1이다. 전역 설정은 변경하지 않았다.

## 재설치와 실행

프로젝트 절대 경로를 아래 prefix에 넣고, 프로젝트 밖의 신뢰된 디렉터리에서 실행한다.

```sh
npm install --prefix /absolute/project/.runtime/rea-tools rea-agents@6.8.0 node@26.12.1
```

프로젝트 루트에서 `bash scripts/rea-project.sh --help`로 확인한다.
`.codex/config.toml`은 프로젝트 MCP stdio 등록이다. 다음 프로젝트 Codex 세션에서 로드한다.
MCP stdio initialize/tools/list도 성공했다(v6.8.0, 229개 도구). 현재 세션에서는 CLI로 같은 REA 분석 기능을 실행했다. MCP 도구가 현재 세션에 자동 추가된 것은 아니다.
스킬 main과 npm 버전의 기능 차이가 있으므로 실제 CLI 도움말/도구 스키마를 우선한다.
네이티브 역공학 엔진은 웹 분석에 필요하지 않아 설치하지 않았다.

## 관찰 근거

대상은 실제 https://chatgpt.com/ 이다. Aside의 로컬 포트는 표준 CDP JSON 엔드포인트가 아니어서 REA 자체 임시 Chrome을 사용했다. 기존 로그인 프로필·쿠키를 복사하지 않았다.

- 빈 화면: `ev_d270a8f2e1655d4a4128029f06a2702a3e1e0d690bdba0d86d7dd1f1ef6fb7c3`.
- 대화 화면: `ev_acd1b9438901b55935e3fcd7e988da7bc89cccceb8c7b983aaaca935bc91e535`.
- REA `capture-browser-scenario`로 실제 DOM, 접근성 트리, 스크린샷을 저장했다. 합성 질문 입력 → Enter 전송 → 답변 표시까지 완료했다.
- 원본/화면은 `.runtime/rea-chatgpt/`에만 보관한다. 공개 플러그인에는 로그인 데이터나 웹페이지 원본을 넣지 않는다.

관찰: 1280×720 화면에서 약 260px 사이드바, 중앙 약 768px 대화 폭, 오른쪽 사용자 말풍선, 테두리 없는 답변 본문, 답변 아래 복사 동작, 하단 둥근 입력창. 접근성 트리는 대화 영역과 사용자/답변, textbox, 전송 버튼을 구분한다.

모아 적용 설계: 기존 탐색 사이드바를 유지하고 대화 폭을 제한한다. 빈 화면에는 기능 안내 한 줄만 두고 예시 카드·홍보 문구를 넣지 않는다. 입력창은 대화 영역 하단에 유지하고 모바일에서 별도 기록 패널을 접는다. 모델의 쓰기 요청은 확인/추적 제안으로 표시하며 사용자가 적용할 때 기존 버전 검사를 수행한다.

관찰 한계: 로그아웃 상태의 빈 화면과 한 대화 흐름이다. 로그인된 ChatGPT 기록 관리·모바일 실제 동작·내부 소스 구조까지 관찰했다고 주장하지 않는다. 모아의 반응형 구현과 일정 도구는 별도 자체 구현이다.
