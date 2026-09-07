# Relay MCP Updater

Railway의 Relay MCP에서 아래 오류가 발생했을 때 사용하는 SOP와 재사용 가능한 업데이트 스킬입니다.

```text
PB auth-with-password failed (403)
The collection is not configured to allow password authentication.
```

비밀번호 인증이 꺼진 Relay 서버에 맞춰 Google·GitHub·Microsoft 로그인을 지원합니다. 사용 가능한 제공자는 해당 인증 서버에서 조회합니다.

- [오류 대응 SOP](skills/relay-mcp-updater/references/SOP.ko.md)
- [스킬 지침](skills/relay-mcp-updater/SKILL.md)
- [복사해서 쓰는 프롬프트](skills/relay-mcp-updater/references/prompts.ko.md)

## 설치

Python 3.9+, Git, Node.js 22+, npm, Railway CLI가 필요합니다. Railway는 자신의 계정으로 로그인하세요.

```sh
git clone https://github.com/Monkkim/relay-mcp-updater.git
cd relay-mcp-updater
# Codex: 아래 폴더가 이미 있다면 먼저 기존 변경을 확인하세요
mkdir -p ~/.codex/skills
cp -R skills/relay-mcp-updater ~/.codex/skills/
# Claude Code는 같은 폴더를 ~/.claude/skills/ 아래에 설치할 수 있습니다
```

설치 후 새 대화에서 `$relay-mcp-updater`를 호출하거나 다음 명령을 실행합니다.

```sh
cd skills/relay-mcp-updater
python3 scripts/run.py --project YOUR_PROJECT --service YOUR_SERVICE \
  --source /path/to/your/deployed/relay-mcp-server --apply
```

`--apply`가 없으면 진단합니다. 서비스가 하나뿐이면 `--service`를 생략할 수 있습니다. 실제 소스가 Railway 로컬 연결 기록에서 하나로 식별되는 경우 자동으로 찾습니다. 연결 기록이 오래되었을 수 있으므로 실제 배포 소스인지 확인하세요.

## 자동 업데이트 방식

스킬을 **실행할 때마다** 이 저장소의 최신 정식 GitHub Release를 가져옵니다. 새 릴리스가 지원하는 코드이면 백업·테스트·배포·상태 확인까지 실행합니다. 이미 최신이면 재배포하지 않습니다. `main`에 커밋만 올리는 것으로는 배포되지 않으며 상시 스케줄도 생성하지 않습니다.

`--offline`은 설치된 버전을 의도적으로 사용할 때만 지정합니다. 최신 릴리스 조회 실패를 자동으로 무시하지 않습니다. 비공개 포크는 GitHub API 토큰(`GITHUB_TOKEN`)과 해당 저장소를 읽을 수 있는 Git 자격 증명이 필요합니다. 배포 토큰은 저장소에 넣지 않습니다.

## 지원 범위

- 번들 `os-mcp`의 Relay MCP v2 비밀번호 로그인 소스와 검증된 2.0.1 수정본
- 프로젝트·환경·서비스 이름은 사용자별로 지정 가능
- Railway 변수와 `/data` 볼륨 보존
- 소스 지문이 다른 커스텀 서버는 자동 덮어쓰기 거절
- 실제 사용자 로그인은 해당 사용자가 완료하고, MCP 볼트·폴더 조회로 최종 검증

자동화는 HTTP 검증까지 판정합니다. `deployed_health_verified`를 실제 계정 로그인 완료로 해석하지 마세요. 복구용 소스 백업과 이전 배포 ID를 남기며, 롤백 절차는 SOP에 설명합니다.

## 테스트

```sh
python3 -m unittest discover -s tests -v
cd skills/relay-mcp-updater/assets/server
npm ci --ignore-scripts --no-audit --no-fund
npm test
```

## 릴리스 유지보수

번들 수정 후 manifest의 새 해시와 버전을 갱신하고 이전 허용 지문을 보존하세요. 테스트한 커밋에 새 `vX.Y.Z` 태그와 정식 Release를 발행합니다. 기존 태그를 이동하지 않습니다. 개인 이메일·토큰·서비스 ID·세션 데이터는 포함하지 않습니다.

기반 코드: [Monkkim/secondbrain-suite의 os-mcp](https://github.com/Monkkim/secondbrain-suite/tree/master/skills/os-mcp). 이 저장소는 Relay.md 또는 Railway의 공식 제품이 아닙니다. 기반 코드와 의존성의 권리는 각 권리자에게 있습니다.

## 실제 배포 소스 대조 조건

최초 교체에는 Railway SSH 접근이 필요합니다. 스크립트는 실행 중인 `/app/src` 파일 해시와 로컬 소스를 대조합니다. SSH가 설정되지 않았거나 대조에 실패하면 배포하지 않습니다. 사용자가 자신의 SSH 키를 Railway에 등록한 뒤 다시 실행하거나 개별 병합을 진행합니다. 정상 배포본에 실행 파일 지문이 추가되면 다음 실행은 그 지문으로 최신 여부를 판단합니다. 버전 문자열만 같은 예전 수정본은 최신으로 단정하지 않습니다.
