import type { Response } from "express";
import type {
  OAuthServerProvider,
  AuthorizationParams,
} from "@modelcontextprotocol/sdk/server/auth/provider.js";
import type { OAuthRegisteredClientsStore } from "@modelcontextprotocol/sdk/server/auth/clients.js";
import type {
  OAuthClientInformationFull,
  OAuthTokens,
  OAuthTokenRevocationRequest,
} from "@modelcontextprotocol/sdk/shared/auth.js";
import type { AuthInfo } from "@modelcontextprotocol/sdk/server/auth/types.js";
import {
  InvalidGrantError,
  InvalidTokenError,
} from "@modelcontextprotocol/sdk/server/auth/errors.js";

import { ALLOWED_EMAILS, STATIC_MCP_BEARER, PB_AUTH_URL, PB_COLLECTION, PUBLIC_URL } from "../config.js";
import { clientsStore } from "./clients.js";
import { createPending, consumePending, peekPending } from "./pending.js";
import { createCode, consumeCode, peekCode } from "./codes.js";
import { createSession, getSession } from "./sessions.js";
import { refreshPbToken } from "./pocketbase.js";
import {
  signAccessToken,
  verifyAccessJwt,
  issueRefreshToken,
  redeemRefreshToken,
  revokeRefreshToken,
  ACCESS_TOKEN_TTL_SEC,
} from "./tokens.js";

export const LOGIN_PATH = "/oauth/login";
export const RESET_PATH = "/oauth/reset-request";

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

export function loginCookieName(state: string): string {
  return `${PUBLIC_URL.startsWith("https:") ? "__Host-" : ""}relay-login-${state}`;
}

function renderLoginPage(params: { state: string; error?: string }): string {
  const config = JSON.stringify({ state: params.state, authUrl: PB_AUTH_URL, collection: PB_COLLECTION })
    .replace(/</g, "\\u003c");
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="referrer" content="same-origin">
<title>Sign in to Relay Vault MCP</title>
<style>
*{box-sizing:border-box}body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#0f172a;color:#e2e8f0;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;padding:1rem}
.card{background:#1e293b;padding:2rem;border-radius:12px;width:100%;max-width:460px;box-shadow:0 10px 40px #0004}h1{font-size:1.3rem;margin:0 0 .6rem}p{color:#94a3b8;line-height:1.5}button{width:100%;padding:.85rem;margin:.4rem 0;border:1px solid #334155;border-radius:8px;background:#38bdf8;color:#0f172a;font-size:1rem;font-weight:600;cursor:pointer}button:hover{background:#7dd3fc}button:disabled{opacity:.5;cursor:wait}.error{color:#fecaca}.hint{font-size:.85rem}a{color:#7dd3fc}
</style></head><body><main class="card">
<h1>Sign in to Relay Vault</h1>
<p>Choose the provider you use for your Relay.md account.</p>
<div id="providers"></div>
<p id="status" role="status" aria-live="polite" ${params.error ? 'class="error"' : ""}>${params.error ? escapeHtml(params.error) : "Loading sign-in options…"}</p>
<p class="hint">A sign-in window will open. Keep this page open until the connection finishes.</p>
<noscript>Enable JavaScript to sign in with your Relay account.</noscript>
<script id="login-config" type="application/json">${config}</script>
<script type="module" src="/assets/relay-login.js"></script>
</main></body></html>`;
}

function renderErrorPage(title: string, body: string): string {
  return `<!doctype html>
<html><head><meta charset="utf-8"><title>${escapeHtml(title)}</title>
<style>body{font-family:-apple-system,sans-serif;background:#0f172a;color:#e2e8f0;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}.card{background:#1e293b;padding:2rem;border-radius:12px;max-width:420px}h1{margin:0 0 .75rem;color:#fca5a5}p{color:#cbd5e1}</style>
</head><body><div class="card"><h1>${escapeHtml(title)}</h1><p>${escapeHtml(body)}</p><p>You can close this tab.</p></div></body></html>`;
}

export class RelayOAuthProvider implements OAuthServerProvider {
  get clientsStore(): OAuthRegisteredClientsStore {
    return clientsStore;
  }

  async authorize(
    client: OAuthClientInformationFull,
    params: AuthorizationParams,
    res: Response
  ): Promise<void> {
    const pending = createPending({
      claudeClientId: client.client_id,
      claudeRedirectUri: params.redirectUri,
      claudeState: params.state,
      claudeCodeChallenge: params.codeChallenge,
      claudeResource: params.resource?.toString(),
    });

    res.cookie(loginCookieName(pending.ourState), "1", {
      httpOnly: true, secure: PUBLIC_URL.startsWith("https:"), sameSite: "lax", path: "/", maxAge: 30 * 60_000,
    });
    res.set("Cache-Control", "no-store");
    res.status(200).type("text/html").send(renderLoginPage({ state: pending.ourState }));
  }

  async challengeForAuthorizationCode(
    _client: OAuthClientInformationFull,
    authorizationCode: string
  ): Promise<string> {
    const code = peekCode(authorizationCode);
    if (!code) throw new InvalidGrantError("invalid or expired authorization code");
    return code.codeChallenge;
  }

  async exchangeAuthorizationCode(
    client: OAuthClientInformationFull,
    authorizationCode: string,
    _codeVerifier?: string,
    _redirectUri?: string,
    _resource?: URL
  ): Promise<OAuthTokens> {
    const code = consumeCode(authorizationCode);
    if (!code) throw new InvalidGrantError("invalid or expired authorization code");
    if (code.clientId !== client.client_id) {
      throw new InvalidGrantError("code was issued to a different client");
    }

    const session = getSession(code.sid);
    if (!session) throw new InvalidGrantError("session no longer exists");

    const accessToken = await signAccessToken({
      sid: session.sid,
      email: session.email,
      clientId: client.client_id,
    });
    const refreshToken = issueRefreshToken(session.sid, client.client_id);

    return {
      access_token: accessToken,
      token_type: "Bearer",
      expires_in: ACCESS_TOKEN_TTL_SEC,
      refresh_token: refreshToken,
    };
  }

  async exchangeRefreshToken(
    client: OAuthClientInformationFull,
    refreshToken: string,
    _scopes?: string[],
    _resource?: URL
  ): Promise<OAuthTokens> {
    const redeemed = redeemRefreshToken(refreshToken);
    if (!redeemed) throw new InvalidGrantError("invalid or expired refresh token");
    if (redeemed.clientId !== client.client_id) {
      throw new InvalidGrantError("refresh token was issued to a different client");
    }
    const session = getSession(redeemed.sid);
    if (!session) {
      revokeRefreshToken(refreshToken);
      throw new InvalidGrantError("session no longer exists");
    }

    const accessToken = await signAccessToken({
      sid: session.sid,
      email: session.email,
      clientId: client.client_id,
    });

    return {
      access_token: accessToken,
      token_type: "Bearer",
      expires_in: ACCESS_TOKEN_TTL_SEC,
      refresh_token: refreshToken,
    };
  }

  async verifyAccessToken(token: string): Promise<AuthInfo> {
    if (STATIC_MCP_BEARER && token === STATIC_MCP_BEARER) {
      return {
        token,
        clientId: "static-bearer",
        scopes: [],
        expiresAt: Math.floor(Date.now() / 1000) + 60 * 60,
        extra: { mode: "static" },
      };
    }

    try {
      const verified = await verifyAccessJwt(token);
      const session = getSession(verified.sid);
      if (!session) throw new InvalidTokenError("session no longer exists");
      return {
        token,
        clientId: verified.clientId,
        scopes: [],
        expiresAt: verified.expSec,
        extra: {
          mode: "oauth",
          sid: verified.sid,
          email: verified.email,
        },
      };
    } catch (err: any) {
      if (err instanceof InvalidTokenError) throw err;
      throw new InvalidTokenError(err.message || "invalid access token");
    }
  }

  async revokeToken(
    _client: OAuthClientInformationFull,
    request: OAuthTokenRevocationRequest
  ): Promise<void> {
    const token = request.token;
    if (request.token_type_hint === "refresh_token" || !request.token_type_hint) {
      revokeRefreshToken(token);
    }
  }
}

/** Complete social login only after Relay validates the token. */
export async function handleLogin(params: {
  state: string;
  pbToken: string;
  browserBound: boolean;
}): Promise<{ redirectUrl: string } | { pageHtml: string; status: number }> {
  if (!params.browserBound) {
    return { pageHtml: renderErrorPage("Sign-in session mismatch", "Restart the connection from your MCP client in this browser."), status: 403 };
  }
  const pending = peekPending(params.state);
  if (!pending) {
    return { pageHtml: renderErrorPage("Session expired", "Please restart the connection from your MCP client."), status: 400 };
  }
  if (!params.pbToken || params.pbToken.length > 16_384) {
    return { pageHtml: renderLoginPage({state: params.state, error: "Please sign in with your Relay account."}), status: 400 };
  }
  let pb;
  try {
    pb = await refreshPbToken(params.pbToken);
    if (!pb.email || !pb.recordId || !pb.pbToken || pb.pbTokenExp <= Date.now() / 1000) throw new Error("Invalid session");
  } catch {
    return { pageHtml: renderLoginPage({state: params.state, error: "Relay could not verify your sign-in. Please try again."}), status: 401 };
  }
  if (ALLOWED_EMAILS.length && !ALLOWED_EMAILS.includes(pb.email)) {
    return { pageHtml: renderErrorPage("Not authorized", "This Relay account is not allowed to connect to this server."), status: 403 };
  }
  // Consume after async verification: concurrent/replayed submissions cannot issue two codes.
  if (!consumePending(params.state)) {
    return { pageHtml: renderErrorPage("Session expired", "Please restart the connection from your MCP client."), status: 400 };
  }
  const session = createSession(pb);
  const code = createCode({
    sid: session.sid, clientId: pending.claudeClientId, redirectUri: pending.claudeRedirectUri,
    codeChallenge: pending.claudeCodeChallenge, resource: pending.claudeResource,
  });
  const finalRedirect = new URL(pending.claudeRedirectUri);
  finalRedirect.searchParams.set("code", code.code);
  if (pending.claudeState) finalRedirect.searchParams.set("state", pending.claudeState);
  return { redirectUrl: finalRedirect.toString() };
}
