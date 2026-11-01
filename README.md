# 모아 · Chat Schedule Hub

0.3.1 개발 미리보기: 레코드 증분 동기화와 Dot 실행 안내를 포함합니다. Gmail·네이버·Google Calendar 연결 파일럿과 연결 전용 스킬을 추가했습니다. [변경 이력](CHANGELOG.md)을 참고하세요. 기존 0.1.1에서는 카카오톡 UI 오류 복구 절차, 전체 AX 정규화와 `kakao-observe` 입력 경로를 추가했습니다. [복구 안내](docs/KAKAO_UI_RECOVERY.md)를 참고하세요. 실제 전체방·30일 수집과 독립 GUI 데몬은 아직 완료되지 않았습니다. Discord 상시 봇 상태는 [운영 기록](docs/CONTINUOUS_COLLECTION.md)을 따릅니다.

대화에서 일정을 정리하는 Codex 플러그인과 개인 일정 조회용 웹앱입니다. 현재 개발 미리보기입니다.

- 카카오톡 Mac UI·Discord 공식 봇 수집 및 메일·캘린더 연결 스킬
- SQLite 증분 저장, 중복 제거, 중간 실패 재개, 메시지 수정 이력
- 교체 가능한 OpenAI Decisions 판단 공급자
- 대시보드·사람별 간트·크라임씬 탭과 서버 저장 인물 필터
- 비공개 Sites 동기화와 PWA 기본 구성

## 실행

Python 3.9 이상에서 저장소 루트를 기준으로 실행합니다.

```sh
python3 -m hub.cli sources
python3 -m unittest discover -s tests -v
```

Codex 플러그인의 `skills/collect-schedules/SKILL.md`를 실행 지침으로 사용합니다. GUI 조작은 호스트의 컴퓨터 유즈 기능이 담당합니다. 이 패키지 자체에 독립적인 GUI 자동화 데몬은 포함되어 있지 않습니다. 자동 백그라운드 수집을 보장하지 않습니다.

환경변수 `HUB_DB`는 개인 SQLite 위치, `OPENAI_API_KEY`는 판단 API 인증, `HUB_DECISION_MODEL`은 모델 선택입니다. 키 파일은 `OPENAI_API_KEY_FILE`로 지정할 수 있고 기본값은 `~/Library/Application Support/ChatScheduleHub/openai.key`입니다. 파일 권한은 600이어야 합니다. 비밀값과 실제 대화는 저장소 밖에 보관합니다. `hub.cli`의 JSON 입력은 stdin으로 전달합니다. 수집 배치 형식은 [예제](examples/batch.json)를 참고하세요.

조회 앱 개발은 `site/`에서 진행합니다. Sites에 등록한 프로젝트 ID와 인증정보는 각 설치자가 설정합니다. 개인 Sites 설정은 공개 GitHub에 포함하지 않습니다. 세부 실행 절차는 [사이트 안내](site/README.md)를 참고하세요.

## 확장과 검증 범위

[최종 계획](PLAN.md), [프로젝트 지침](AGENTS.md), [수집 어댑터 계약](docs/SOURCE_ADAPTER_CONTRACT.md)을 기준으로 구현합니다. 새 수집 경로 추가 스킬은 `skills/add-collection-source/`에 있습니다.

현재 Python 테스트 83개를 통과했습니다. 웹앱은 이번 변경 대상이 아니며 이전 TypeScript 검사·빌드 결과와 구분합니다. Decisions API의 합성 일정 분류 실호출도 성공했습니다. 전체 방 최근 30일 수집, 실제 기기 PWA 설치, Codex 플러그인 설치 수용 검증 및 마켓 심사는 완료되지 않았습니다. 개인 Sites 배포는 성공했으며 개인 URL·프로젝트 ID는 공개 설정에 포함하지 않습니다. Decisions는 의도 분류를 담당하며 자유형 일정 추출은 호스트 Codex 단계에서 수행합니다.

공개 저장소와 개인 사이트의 공개 범위는 별개입니다. 샘플은 합성 데이터입니다. 배포 조건과 제3자 라이선스는 [LICENSE.md](LICENSE.md)를 확인하세요.

기본 수집 경로는 `select-ingest`이며 저장 전에 Decisions로 관련성과 의도를 함께 판단합니다. 전체 수집은 파일럿 검증 후 확대합니다. [파일럿 결과](docs/PILOT_REPORT.md)에 실측·한계·확대 조건을 기록했습니다.

## Gmail·네이버 메일·Google Calendar

세 경로의 읽기 인증과 제한 파일럿을 지원합니다. [실행 안내](docs/MAIL_CALENDAR_RUNBOOK.md)를 따르세요. 상시 증분 수집·메일 일정 추출·새 데이터의 Sites 동기화는 미완료입니다.

## 증분 동기화와 Dot

[증분 동기화](docs/INCREMENTAL_SYNC.md)는 변경된 레코드만 보내며 변경이 없으면 전송하지 않습니다. [Dot 원격 실행 안내](docs/DOT_REMOTE_COLLECTION.md)는 연결 조건과 실제 검증 절차를 설명합니다. Dot 계정 연결과 예약 실행은 미검증입니다.
