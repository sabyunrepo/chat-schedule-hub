# 수집 경로 확장 계약 v1 (설계)

이 문서는 구현할 공통 계약이다. 아래 인터페이스·레지스트리·검증 도구는 아직 구현되지 않았다. 초기 구현은 카톡 Mac 앱과 Discord 웹이며, 이후 API·파일 가져오기 등을 같은 파이프라인으로 연결할 수 있다.

## 1. 연결 구조와 경계

```text
SourceRegistry → 설정/권한/대상 선택 → SourceAdapter
  → CollectionBatch → 검증·정규화 → 공통 저장·중복 제거
  → 분석 큐 → ExtractionProvider/DecisionProvider
  → 일정 엔진 → SyncAdapter → 세 탭
```

새 경로는 어댑터 모듈, 등록 정보, 설정 스키마, 수집 특성 문서, 합성 검증 자료를 추가한다. 공통 모델에 맞는 경로는 일정 엔진과 탭별 코드에 서비스명 분기를 추가하지 않는다. 새 의미가 필요한 경우 공통 계약을 버전업하고 기존 경로의 회귀를 확인한다.

SourceAdapter는 허용된 소스를 관찰하고 원문·출처·수집 범위를 반환한다. DB 체크포인트 갱신, AI 판단, 일정 생성, 클라우드 전송은 공통 계층이 담당한다. ComputerDriver는 UI 입력·관찰을 담당하고 서비스의 의미는 어댑터가 해석한다. API/파일 경로에는 ComputerDriver를 강제하지 않는다.

## 2. 등록 정보와 capability

각 등록 정보에 다음을 선언한다.

- adapterId, adapterVersion, contractVersion, displayName
- transport: native-ui | browser-ui | official-api | file-import
- 지원 플랫폼/앱 버전, 필요한 호스트 도구, 설정 스키마, 비밀 참조 키
- 안정적 메시지 ID 여부, 시간 정밀도, 순서 보장 범위
- resume 방식: native-cursor | observed-anchor | file-position | none
- 지원 작업: 과거 조회, 증분 조회, 최근 구간 재확인, 수정/삭제 감지
- 스레드·답글·첨부·원문 링크 지원 및 제한
- 접근 범위, 읽음 상태 변경 등 관찰 부작용, 호출 제한, 권장 수집 예산

지원하지 않는 기능은 unsupported로 명시한다. 예를 들어 삭제 감지 불가를 '삭제 없음'으로 변환하지 않는다. 설정에는 토큰 값 대신 비밀 저장소 참조를 둔다. 등록은 로컬의 검토된 모듈 목록을 사용하며 원격 URL의 코드를 자동 실행하지 않는다.

## 3. 공통 인터페이스 (언어 중립 계약)

| 작업 | 입력 | 반환/책임 |
| --- | --- | --- |
| describe | 없음 | 등록 정보·정적 capability |
| probe | 연결 설정·실행 환경 | 호환성·로그인·권한 상태와 실제 capability. 대상 본문 수집 없음 |
| listTargets | 연결·목록 커서 | 접근 가능한 방/채널/파일의 최소 메타데이터. 선택은 사용자 범위로 제한 |
| collect | CollectionRequest·취소 신호 | 제한된 크기의 CollectionBatch 스트림 |
| close | 실행 컨텍스트 | 자원 해제. 소스 데이터·권한 변경 없음 |

CollectionRequest: connectionId, targetId, mode(initial/incremental/reconcile), 기간, 선택된 스레드/첨부 정책, durableCheckpoint, 시간/페이지/항목 예산. 계정·워크스페이스·대상은 설정된 허용 범위와 다시 대조한다. 어댑터는 예산 초과·취소 요청에 응답해야 한다.

## 4. 공통 입력 형식

Connection은 한 서비스 계정/워크스페이스 연결이다. Target은 방·채널·스레드·문서 등 수집 단위이며 parentTargetId로 계층을 표현한다. 사람이 보는 이름과 안정적 내부 ID를 구분한다. 기존 rooms 모델은 이 Target의 채팅 특화 표현으로 확장한다.

MessageObservation 필수 의미:

- schemaVersion, connectionId, targetId, observedAt
- originId(없으면 null), identityQuality(stable/derived/ambiguous), identityScope
- authorRef(알 수 없으면 null), authorDisplayName
- sentAt(알 수 없으면 null), originalTimestampText, timezone, timestampPrecision
- text, contentKind, revisionFingerprint, editedAt(알 수 없으면 null)
- replyToRef/threadRef, attachment 메타데이터 및 수집 상태
- sourceLocator(허용된 딥링크 또는 방/시각/문맥), provenance(AX/DOM/화면/OCR/API/파일)
- observationKind: observed | edited | explicit-deletion

삭제 표시는 소스의 명시적 증거가 있을 때만 반환한다. editedAt을 모르면 관찰 시각을 수정 시각으로 대신 넣지 않는다. 작성자·날짜가 화면에서 생략된 묶음 메시지는 문맥으로 보완하되 추정 여부를 기록한다. OCR 결과는 원문과 동일한 신뢰도로 취급하지 않는다.

originId의 유일성 범위는 (connectionId, targetId, originId)를 기본으로 하며 실제 서비스 계약에 맞춘다. DB 내부 ID는 별도로 유지한다. ID 없는 메시지는 주변 순서·본문·작성자·시간의 후보 매칭으로 처리하고, 충돌은 병합을 보류한다. 본문 변경만으로 새로운 메시지가 되거나 같은 문구의 다른 메시지가 사라져서는 안 된다.

## 5. 배치·체크포인트 계약

CollectionBatch는 observations, candidateCheckpoint, coverage, gaps, stopReason, 진단 메타데이터를 포함한다. coverage에는 요청한 범위와 실제 관찰 범위, 연속성 확인 여부를 분리한다. 날짜의 최소/최대만으로 중간 구간의 완전성을 주장하지 않는다.

stopReason: known-boundary | requested-range-reached | explicit-source-end | budget-exhausted | cancelled | retryable-error | access-blocked | anchor-lost. 빈 페이지나 변경 없는 화면은 explicit-source-end의 증거가 아니다.

체크포인트에는 contract/adapter/cursor 버전, connectionId, targetId, 수집 모드·범위, 불투명 커서 또는 앵커, 경계 증거를 포함한다. 토큰·쿠키는 포함하지 않는다.

공통 저장기는 메시지/리비전, 실행 상태, 분석 작업과 체크포인트를 원자적으로 저장한다. 저장 실패 시 이전 체크포인트에서 재시도하며 전달은 at-least-once, 반영은 멱등 처리한다.

최신부터 과거로 수집하는 동안의 '이번 실행 재개 위치'와 '이전 실행과 연속성이 확인된 경계'를 분리한다. 중간에 종료된 실행의 최신 메시지만 보고 다음 실행이 즉시 멈춰 미수집 중간 구간을 건너뛰어서는 안 된다. 미완료 구간을 먼저 이어서 수집한다.

앵커가 삭제되거나 커서가 만료되면 제한된 겹침 구간을 재탐색한다. 찾지 못하면 anchor-lost와 공백을 기록하고, 지정 범위를 넘는 무한 전체 재수집을 하지 않는다. 버전 비호환은 마이그레이션 또는 명시적인 제한 재수집으로 처리한다.

## 6. 경로별 주의점

### UI/가상 스크롤

- 매 동작 뒤 최신 관찰에서 요소를 다시 찾는다. 과거 DOM/AX 인덱스와 좌표를 다음 화면에 재사용하지 않는다.
- 최상위 페이지 대신 메시지 컨테이너를 스크롤한다. 로딩 변화와 메시지 경계를 함께 확인한다.
- 실제 계정·방 이름/ID를 검증하고 포커스가 다른 창으로 이동하면 중단한다.
- 같은 데스크톱 입력 자원을 공유하는 수집은 잠금으로 직렬화한다. 사용자 조작과 충돌하면 양보·재개한다.
- 스크롤 간 겹침을 보존하고 날짜 구분선·묶인 작성자·같은 시각 메시지·고정 메시지·시스템 메시지를 구분한다.
- 스레드와 접힌 답글은 별도 대상/체크포인트를 사용한다. 루트 채널 수집 완료가 모든 스레드 완료를 의미하지 않는다.
- 로그인 만료·절전·잠금·권한 거부·화면 구조 변경은 정상적인 중단 원인으로 기록한다.

### 공식 API (향후 선택 시)

공식 권한 범위·페이지네이션·순서·수정/삭제 이벤트 보장을 확인한다. Retry-After와 호출 제한에 맞춰 재시도하고, 중복·역순 이벤트를 처리한다. 공식 API를 쓸 수 있다는 이유로 초기 UI 수집 선택을 바꾸지 않는다. 비공개 API·세션 토큰 추출을 기본 연결 방식으로 삼지 않는다.

### 파일 가져오기 (향후 선택 시)

사용자가 지정한 파일만 처리한다. 인코딩·시간대·줄바꿈·내보내기 형식 버전·파일 교체/추가 여부를 확인한다. 파일 해시와 위치를 커서에 연결한다. 재가져오기 중복, 잘린 파일, 표기 이름만 있는 작성자 식별 한계를 표시한다.

## 7. 연결 추가 절차

1. 대상·전송 방식·수집 범위·플랫폼을 정의하고 현재 공식 문서 및 허용된 UI를 조사한다.
2. docs/sources/<adapter-id>.md에 지원 범위, capability, ID/시간 규칙, 권한/부작용, 중단·재개, 한계와 근거를 작성한다.
3. 합성 또는 비식별 샘플로 MessageObservation 매핑과 체크포인트 설계를 검증한다.
4. 어댑터와 설정 스키마를 작성하고 SourceRegistry에 등록한다. 런타임 등록은 미래 구현이며 현재 문서 파일 추가만으로 작동하지 않는다.
5. 연결 온보딩에 probe·대상 선택·허용 범위·상태 표시를 연결한다. capability에 없는 설정은 제공하지 않는다.
6. 공통 저장/분석/동기화 파이프라인을 통과시킨다. 소스별 AI/DB/화면 파이프라인을 복제하지 않는다.
7. 계약 검증과 작은 실제 범위 검증을 구분해 수행한다. 기존 카톡·Discord 경로 회귀를 확인한다.
8. 문서·버전·플러그인 패키지 포함 목록을 갱신하고 검증 결과·남은 제한을 보고한다.

## 8. 어댑터 수용 기준

필수: 최초/증분 수집, 동일 배치 재전달, 저장 직전/직후 실패, 중간 수집 재개, 같은 본문/시각의 별개 메시지, 계정/대상 격리, 예산/취소, 인증 만료, 커서 손실, 부분 수집 표시.

지원 capability에 따라 추가: 수정·명시 삭제, 스레드/첨부, 역순 이벤트, 파일 재가져오기. unsupported 사례도 조용히 성공 처리하지 않는지 확인한다.

확장성 기준: 합성 테스트 어댑터 하나를 추가하여 기존 일정·대시보드 코드를 서비스별로 수정하지 않고 데이터가 흐르는지 확인한다. 이것을 실제 외부 서비스 지원 완료로 보고하지 않는다.

보고 지표: 읽은 구간/항목, 신규/중복/수정/모호 항목, 공백, 종료 이유, 소요 시간, 재시도. 실본문과 비밀값은 진단 로그에서 제외한다.

## 선택 수집 연결

어댑터는 화면에서 관찰한 최대 32개 메시지를 공통 select-ingest에 전달한다. AI를 서비스별 어댑터 안에 복제하지 않는다. 선택 저장에서도 전체 관찰 순서의 지문으로 경계를 계산한다. 관련 메시지와 맥락만 messages/revisions/jobs에 저장하고 제외 본문은 보관하지 않는다. 선택 결과·커서·경계는 같은 트랜잭션으로 커밋한다. API 실패는 커서 전진 없이 재관찰한다. 정확한 재개가 불가능한 UI는 anchor-lost로 보고한다.

선별 캐시는 계정 범위 target, 원본/발생 ID, 본문 지문, 전체 페이지와 context의 지문, 공급자·모델·규칙 버전을 포함한다. 페이지가 달라지면 짧은 답변의 의미가 달라질 수 있어 재판정한다. 어댑터는 페이지 경계에서 답글/일정 맥락을 연결하고 누락된 맥락을 명시해야 한다.


## 착오 검토 근거 확장

런타임 replyToRef는 {targetId,identity}이며 identity는 해당 대상의 originId 또는 검증된 occurrenceKey다. 원문 ID를 추측하지 않는다. sourceLocator, editedAt, provenance, timestampPrecision, threadRef를 가능한 경우 보존한다. 메시지 의미를 바꾸는 메타데이터도 revision 지문에 포함한다.

선택 규칙 v5는 일정과 사실·정정 근거를 보존한다. evidenceGaps에는 보관 메시지의 미확보 답글 참조가 포함된다. 이는 자동 원문 검색기가 구현됐다는 뜻이 아니다. 호스트가 UI로 보완해야 하며 공백이 남은 배치는 완료할 수 없다. 보존 규칙이 바뀌면 이전 완료 경계를 무효화하고 진행 중 실행은 명시적 restart로 재관찰한다.
