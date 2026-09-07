# SOP: Relay MCP 비밀번호 인증 403 복구와 업데이트

문서 버전 1.0.0 · 기준일 2026-09-07

**목표:** Railway의 기존 서비스·계정·볼트·설정을 보존하면서 소셜 로그인과 인증된 MCP 조회를 복구한다.

## 1. 적용 조건

```text
PB auth-with-password failed (403)
The collection is not configured to allow password authentication.
```

PocketBase 인증 컬렉션이 비밀번호 인증을 허용하지 않는데 MCP가 비밀번호 인증을 요청하는 상황이다. 비밀번호 오타, 서버 배포 실패, 토큰 만료, 계정 접근 권한 문제와 구분한다. 모든 403에 이 절차를 적용하지 않는다.

## 2. 실제 사례의 원인과 근거

| 확인 항목 | 관찰 | 판단 |
|---|---|---|
| Railway | 배포 성공, 서비스 실행 중 | 배포 성공만으로 로그인 정상 여부는 알 수 없음 |
| `/health` | HTTP 200 | 애플리케이션 실행은 정상 |
| 인증 방법 | `password.enabled: false` | 비밀번호 로그인 불가 |
| 소셜 제공자 | Google, GitHub, Microsoft | 지원되는 소셜 인증으로 전환 |
| 기존 코드 | `/auth-with-password` 요청 | 로그인 UI와 인증 코드 수정 필요 |
| 레거시 응답 | `emailPassword: true`도 반환 | 레거시 플래그만으로 비밀번호 활성 상태를 판단하면 안 됨 |

공개 기록에는 사용자 이메일, 인증 토큰, 비밀번호, 서비스 식별자를 넣지 않는다.

## 3. 준비 사항

- Python 3.9+, Git, Node.js 22+, npm, Railway CLI
- 사용자 자신의 Railway 로그인과 대상 서비스 배포 권한
- 실제 배포 소스 체크아웃
- 로그인 후 검증할 MCP 클라이언트

`railway login`은 사용자가 자신의 환경에서 완료한다. 비밀값을 채팅이나 GitHub에 붙여 넣지 않는다.

## 4. 대상과 원인 확인

1. `railway list --json`에서 프로젝트·환경·서비스를 찾는다. 중복된 이름과 여러 서비스는 ID 또는 명시적인 서비스명으로 구분한다.
2. 현재 배포 ID, 서비스 도메인, 빌드 설정, 연결 소스, 볼륨 마운트를 확인한다.
3. 변수의 값은 메모리에서 확인하고 비밀값을 출력하지 않는다. `PUBLIC_URL`, `PB_AUTH_URL`, `PB_COLLECTION`이 의도한 대상을 가리키는지 대조한다.
4. 읽기 전용 인증 방법 API를 조회한다.

```text
GET {PB_AUTH_URL}/api/collections/{PB_COLLECTION}/auth-methods
```

`password.enabled`와 `oauth2.providers` 또는 `authProviders`를 확인한다. 비밀번호가 비활성이고 소셜 제공자가 있다면 적용 대상이다. `/health` 성공만으로 진단을 종료하지 않는다.

## 5. 자동 실행

스킬 폴더에서 대문자 값을 사용자의 실제 값으로 바꿔 실행한다.

```sh
# 진단 및 호환성 확인
python3 scripts/run.py --project PROJECT --environment production --service SERVICE

# 실제 배포 소스가 확인되었을 때 빌드·배포
python3 scripts/run.py --project PROJECT --environment production --service SERVICE \
  --source /path/to/relay-mcp-server --apply
```

최신 수정본이면 `already_current`로 종료하고 재배포하지 않는다. 최신 릴리스 조회에 실패하면 자동 배포하지 않는다. 설치된 버전을 의도적으로 사용하려면 `--offline`을 지정한다.

### 자동 처리 범위

- 매 실행 최신 정식 GitHub 릴리스 선택
- 대상 식별, 인증 방식과 공개 URL 대조
- 지원하는 소스 버전의 파일 지문 확인
- 기존 소스 백업과 별도 배포 폴더 준비
- 설치 스크립트를 실행하지 않는 `npm ci`, 컴파일, 인증 테스트
- 한 번의 배포 요청과 해당 배포 상태 추적
- 배포 버전·로그인 JavaScript 해시 확인과 보고서 저장

Railway 환경변수, `/data` 볼륨, 원래 소스 폴더를 수정하지 않는다. `.env`, 로컬 메모, 세션 파일은 업로드하지 않는다.

### 자동 처리에서 제외되는 경우

커스텀 코드나 미지원 버전, 확인되지 않은 소스, 사용자 비밀번호·2FA·새 권한 동의, 상시 감시, 불명확한 업로드의 재시도, 무조건 자동 롤백은 포함하지 않는다. 지원되지 않는 파일은 목록을 보여주고 개별 병합 대상으로 남긴다.

## 6. 수정 후 인증 흐름

```text
MCP 연결 시작
 → 서버가 대기 상태와 HttpOnly 브라우저 쿠키 생성
 → Relay 소셜 제공자 표시
 → 사용자가 해당 제공자에서 로그인
 → Relay 기존 콜백과 실시간 구독으로 인증 코드 수신
 → PocketBase SDK가 PKCE로 코드 교환
 → 브라우저가 Relay 토큰을 MCP 서버에 POST
 → 서버가 쿠키·Origin·auth-refresh·허용 이메일 검증
 → 원래 MCP 클라이언트에 일회용 코드 반환
 → 클라이언트가 PKCE로 MCP 토큰 교환
```

기존 `/api/oauth2-redirect`를 사용해 Google에 새 Railway 콜백을 등록해야 하는 문제를 피한다. 브라우저 토큰은 메모리에서만 사용하고 localStorage에 저장하지 않는다.

### 추가로 발견한 복귀 오류

`Referrer-Policy: no-referrer` 페이지의 네이티브 폼 POST는 `Origin: null`을 보낼 수 있다. 정상 로그인도 출처 검사에서 거절된다. `same-origin`으로 설정한다. 출처·쿠키 검사를 제거하지 않는다.

## 7. 완료 판정

| 단계 | 확인 | 증명하는 범위 |
|---|---|---|
| 테스트 | 호환·커스텀·중복 이름·비밀파일 제외·인증 실패·재사용 | 코드와 처리 규칙 |
| Railway | 해당 배포 ID가 SUCCESS | 배포 완료 |
| HTTP | `/health`와 로그인 자산 해시 일치 | 수정본 제공 |
| 브라우저 | 버튼 표시, 실제 로그인과 복귀 | 로그인 흐름 |
| OAuth | 인증 코드 교환 성공 | MCP 인증 연결 |
| MCP | initialize, `vault_relays`, `vault_folders` | 인증된 도구 접근 |
| 재실행 | `already_current`, 새 배포 없음 | 멱등성 |

볼트·폴더가 비어 있으면 로그인 성공과 데이터 접근 문제를 나누어 보고한다. 노트 본문 수정은 필요하지 않다.

원본 서비스에서는 실제 Google 로그인, 코드 교환, MCP 초기화, 볼트·폴더 목록 조회가 성공했다. 이 결과가 다른 계정의 성공을 보증하지는 않는다. 다른 운영자도 자신의 계정에서 마지막 인증 검증을 수행한다.

## 8. 실패 처리와 롤백

1. `report.json`의 `previous_deployment`, `deployment`, `deployment_status`, `result`를 읽는다.
2. 업로드 결과가 불명확하면 Railway에서 해당 배포를 조회한다. 업로드를 곧바로 반복하지 않는다.
3. 커스텀 충돌은 기존 서비스를 유지하고 별도 병합한다. 해시 검사를 삭제하거나 허용 지문을 임의 추가하지 않는다.
4. 새 배포가 실패하거나 문제가 생기면 Railway의 Deployments 화면에서 기록한 이전 정상 배포를 선택하고 제공되는 Rollback/복원 기능으로 되돌린다. 최신 배포 재실행을 과거 배포 롤백으로 착각하지 않는다.
5. 이전 배포 복원이 불가능하면 백업 소스와 기존 설정으로 복구 배포를 준비한다. 대상과 소스를 확인한 상태에서만 수행한다.
6. 복원 후 실제 배포 ID와 `/health`를 확인한다. 이전 버전은 원래의 비밀번호 오류가 다시 나타날 수 있음을 기록한다.

롤백은 이 스크립트의 자동 완료 동작이 아니다. 실제 복원 결과가 확인되어야 완료로 기록한다.

## 9. 정식 릴리스와 자동 업데이트

- `main` 변경만으로 사용자 서버는 변경되지 않는다.
- 유지보수자가 테스트한 `vX.Y.Z` 태그와 정식 GitHub Release를 발행한다.
- 다음 스킬 실행에서 그 릴리스를 선택한다. 백그라운드 스케줄은 생성하지 않는다.
- 신규 릴리스는 이전 지원 버전의 지문과 마이그레이션 테스트를 유지한다.
- 기존 정식 태그를 이동시키지 않고 새 버전을 발행한다.
- 새로운 권한이나 외부 서비스를 기존 권한으로 조용히 추가하지 않는다.

## 10. 결과 기록 템플릿

```text
일시:
프로젝트 / 환경 / 서비스:
증상과 인증 방법 조회 결과(비밀값 제외):
적용 릴리스 / 커밋:
이전 배포 ID / 새 배포 ID:
호환성·테스트:
HTTP·브라우저 검증:
OAuth·MCP 검증:
남은 사용자 행동:
롤백 여부와 실제 결과:
```

참고: [PocketBase 인증 문서](https://pocketbase.io/docs/authentication/), [Railway 배포 문서](https://docs.railway.com/guides/deployments)

## 실제 배포 소스 대조 조건

최초 교체에는 Railway SSH 접근이 필요합니다. 스크립트는 실행 중인 `/app/src` 파일 해시와 로컬 소스를 대조합니다. SSH가 설정되지 않았거나 대조에 실패하면 배포하지 않습니다. 사용자가 자신의 SSH 키를 Railway에 등록한 뒤 다시 실행하거나 개별 병합을 진행합니다. 정상 배포본에 실행 파일 지문이 추가되면 다음 실행은 그 지문으로 최신 여부를 판단합니다. 버전 문자열만 같은 예전 수정본은 최신으로 단정하지 않습니다.
