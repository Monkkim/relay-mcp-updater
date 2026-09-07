# 실행 프롬프트

## 다른 사용자가 복사해 사용할 요청

```text
$relay-mcp-updater를 사용해 내 Railway Relay MCP를 최신 정식 버전으로 업데이트해줘.

프로젝트: [프로젝트 이름 또는 ID]
환경: production
서비스: [서비스 이름 또는 ID]
실제 배포 소스: [relay-mcp-server 폴더 경로]

현재 증상은 PB auth-with-password failed (403), collection is not configured
 to allow password authentication 오류야.

내 Railway 로그인 상태와 대상부터 확인하고, 지원되는 코드면 백업·패치·테스트·배포까지 진행해.
환경변수와 볼륨은 유지하고, 커스텀 변경이 있으면 덮어쓰지 말고 충돌을 알려줘.
이미 최신이면 재배포하지 마.
마지막에는 실제 소셜 로그인과 MCP 볼트·폴더 조회로 확인해.
내가 직접 로그인해야 하면 그 단계만 안내해줘.
```

## 진단만 필요한 경우

```text
$relay-mcp-updater로 Railway 프로젝트 [이름], 서비스 [이름]의 인증 오류를 진단해줘.
배포하지 말고 원인, 적용 가능 여부, 변경 파일, 남은 확인 사항만 알려줘.
```

## 유지보수자가 새 릴리스를 만드는 요청

```text
이 저장소의 relay-mcp-updater 스킬을 새 버전으로 갱신해줘.
기존 지원 버전에서 마이그레이션되는지, 커스텀 코드를 거절하는지,
비밀값이 패키지에 들어가지 않는지, 재실행이 무변경인지 테스트해.
manifest.json의 버전·기존 허용 지문·새 파일 해시를 일치시키고
GitHub CI가 성공한 커밋에 새 vX.Y.Z 태그와 정식 Release를 발행해.
기존 정식 태그는 이동시키지 마.
```
