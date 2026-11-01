# 웹·PWA 자동 업데이트

2026-11-01. 앱 원본으로 만든 빌드 식별자를 클라이언트, `/api/version`, 서비스 워커에 함께 넣는다. `scripts/run-framework.mjs`가 dev/build 전에 자동 생성하므로 배포 때 수동 버전 증가를 잊어도 소스 변경이 반영된다. 생성 파일은 `lib/build-info.ts`, `public/sw.js`; 워커 원본은 `scripts/service-worker.js`다.

- 시작·앱 복귀·온라인 복구와 사용 중 30초 간격으로 서버 버전을 확인한다. 숨겨진 앱은 복귀 시 확인한다.
- 버전 API는 no-store 응답이며 매번 네트워크로 조회한다. 서비스 워커도 updateViaCache:none으로 검사한다.
- 새 워커는 skipWaiting/claim 후 클라이언트에 알린다. 새 클라이언트가 ACK하면 입력/저장 중인지 판단해 새로고침을 관리한다. ACK가 없는 구형 페이지는 최초 전환 시 한 번 새 URL로 이동한다.
- 새 버전이 확인되면 `moa-`, `moa:` 이름의 앱 캐시만 정리한다. 페이지를 버전 query가 포함된 새 URL로 요청하며 내비게이션은 no-store다. JS/CSS는 빌드별 자산 URL을 사용한다.
- 로그인 쿠키·푸시 구독·DB·필터·다른 이름의 CacheStorage는 삭제하지 않는다. 개인정보 페이지/API는 오프라인 캐시에 넣지 않는다.
- 입력이 남아 있거나 저장/응답 대기 중이면 자동 적용을 잠시 보류하고 ‘지금 업데이트’를 표시한다. 입력을 마치면 자동 적용한다. 버튼을 직접 누르면 입력 중이어도 새로 불러온다.
- 동일 버전 query로 반복 이동하지 않아 캐시/CDN 지연이 생겨도 무한 새로고침을 피한다.

OS가 PWA를 종료/중지했거나 오프라인이면 백그라운드 즉시 실행을 보장할 수 없다. 다시 열고 연결되면 갱신한다. 이 로직이 없는 오래된 앱은 최초 한 번 다시 열어 새 업데이트 관리 코드를 받아야 할 수 있다.

## 검증

타입 검사 및 기존 회귀 테스트 통과. 버전 비교·URL 보존·반복 방지·앱 캐시만 삭제·ACK/구형 클라이언트 전환·내비게이션 no-store·개인 API 비캐싱·푸시 핸들러 보존 테스트 통과. 실제 배포 A→B 전환에서 입력 문구를 남긴 상태로 기다려 새 버전 알림과 입력 보존을 확인했다. 서버 버전 API의 no-store 헤더도 확인했다. iOS/Android 설치 PWA 실기기 검증과 브라우저 검증은 구분한다.

설계 참고: [MDN register/updateViaCache](https://developer.mozilla.org/en-US/docs/Web/API/ServiceWorkerContainer/register), [skipWaiting](https://developer.mozilla.org/en-US/docs/Web/API/ServiceWorkerGlobalScope/skipWaiting).

실제 배포 전환 결과: `745c8c2cf9b03595a450` → `36fd5660aa20ada419d1`. 입력을 비우자 수동 새로고침 없이 자동 전환했고, 설정에 새 버전 `36fd5660`이 표시되었다. 로그인 유지와 기존 푸시 알림 ‘켜짐’도 확인했다. 최종 Sites 소스 `f6b44a62e8b4a566eee238983b45086c25511241`. 설치된 모바일 PWA 실기기는 미검증이다.
