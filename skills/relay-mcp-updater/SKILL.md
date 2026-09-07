---
name: relay-mcp-updater
description: Use when a Railway-hosted Relay MCP v2 login fails with PocketBase password authentication disabled, or the user asks to update a compatible Relay MCP deployment to social sign-in.
---

# Relay MCP Updater

Preserve the user's existing service, Railway variables, and `/data` volume. Read [SOP](references/SOP.ko.md) for the incident and verification procedure. Copy-ready requests are in [prompts](references/prompts.ko.md).

## Execute

1. Resolve the user's project, environment, and service. A name is sufficient only when unique. Use the actual deployed source; a linked path may be stale. Ask for a source path when provenance is unknown. Never replace an unknown customized deployment with a fresh template.
2. Diagnose from this skill directory:
   ```sh
   python3 scripts/run.py --project PROJECT --environment production --service SERVICE
   ```
   Every invocation selects the latest stable release in `Monkkim/relay-mcp-updater`. `--offline` intentionally uses installed files. Network failures do not silently select old code.
3. First migration requires owner-configured Railway SSH access: the script hashes the running `/app/src` and compares it with the local checkout. If SSH or source correspondence cannot be verified, stop automatic deployment; do not register keys or bypass this check silently.

4. When the user requested an update, deploy the verified compatible source:
   ```sh
   python3 scripts/run.py --project PROJECT --environment production --service SERVICE --source /actual/relay-mcp-server --apply
   ```
   Substitute the user's target values. Do not hardcode the author's project, email, IDs, or credentials. Initial Railway login belongs to the user; never request tokens in chat.
5. `already_current` means no redeployment. Old compatible source is backed up and staged; checksums, build, and authentication tests must pass. Customized/unsupported files stop automatic changes. Preserve them for a separately reviewed merge; never bypass fingerprints to force an update.
6. Read the report. `deployed_health_verified` is **not authenticated completion**: restart the actual MCP connector, let the user finish provider login, verify OAuth code exchange, MCP initialization, `vault_relays`, and `vault_folders`. No note-body writes are needed. Report pending user login explicitly.

## Non-obvious boundaries

- `password.enabled: false` overrides misleading legacy `emailPassword: true`. Handle both `authProviders` and `oauth2.providers`.
- Use Relay's existing `/api/oauth2-redirect` through SDK popup/realtime; a new Railway callback may not be registered with Google.
- Keep browser binding, same-origin checks, server `auth-refresh`, allow-list checks, one-use authorization codes, and MCP PKCE.
- `no-referrer` can cause form POST `Origin: null`; use `same-origin`. Do not remove cookie/origin checks.
- Do not reset passwords, enable auth in a third party's database, rotate secrets, delete volumes, or replay uncertain deployments.
- Failed verification requires inspection of the report's previous deployment and SOP rollback procedure. Never claim unverified automatic rollback or successful login.

Automatic means **on invocation**, not a background monitor. Each operator authorizes and authenticates to their own account. Future releases must explicitly support previous source fingerprints.
