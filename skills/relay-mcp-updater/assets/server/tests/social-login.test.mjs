import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
process.env.DATA_DIR = mkdtempSync(join(tmpdir(), 'relay-auth-test-'));
process.env.JWT_SECRET = 'test-only-secret-with-at-least-32-characters';
process.env.PB_AUTH_URL = 'https://auth.example.test';
process.env.PUBLIC_URL = 'https://mcp.example.test';
process.env.ALLOWED_EMAILS = 'allowed@example.test';
const { RelayOAuthProvider, handleLogin } = await import('../dist/auth/provider.js');
const { createPending, peekPending } = await import('../dist/auth/pending.js');
const { peekCode } = await import('../dist/auth/codes.js');
const { getSession } = await import('../dist/auth/sessions.js');
const originalFetch = globalThis.fetch;
test.after(() => { globalThis.fetch = originalFetch; rmSync(process.env.DATA_DIR, {recursive:true, force:true}); });
const pending = () => createPending({claudeClientId:'client', claudeRedirectUri:'https://client.example/callback', claudeState:'client-state', claudeCodeChallenge:'challenge'});
const token = 'header.' + Buffer.from(JSON.stringify({exp: Math.floor(Date.now()/1000)+3600})).toString('base64url') + '.signature';
const sessionResponse = (email='allowed@example.test') => new Response(JSON.stringify({token,record:{id:'record-1',email}}),{status:200});

test('authorization offers social sign-in without disabled password/reset forms', async () => {
  let html = ''; let cookie;
  const res = {status(){return this},type(){return this},send(s){html=s;return this},cookie(...args){cookie=args;return this},set(){return this}};
  await new RelayOAuthProvider().authorize({client_id:'client'}, {redirectUri:'https://client.example/callback',codeChallenge:'challenge'}, res);
  assert.match(html, /relay-login.js/);
  assert.match(html, /name="referrer" content="same-origin"/);
  assert.doesNotMatch(html, /type="password"|Send reset email/);
  assert.ok(cookie);
});

test('unbound browser cannot complete another authorization', async () => {
 const p=pending();
 globalThis.fetch=()=>{throw new Error('must not contact upstream')};
 const result=await handleLogin({state:p.ourState,pbToken:token,browserBound:false});
 assert.equal(result.status,403);
 assert.ok(peekPending(p.ourState));
});

test('verified Relay token creates session and original client redirect, then rejects replay',async()=>{
 const p=pending();
 globalThis.fetch=async (url,options)=>{
  assert.equal(url,'https://auth.example.test/api/collections/users/auth-refresh');
  assert.equal(options.headers.Authorization,token);
  return sessionResponse();
 };
 const result=await handleLogin({state:p.ourState,pbToken:token,browserBound:true});
 assert.ok(result.redirectUrl);
 const u=new URL(result.redirectUrl); assert.equal(u.origin,'https://client.example');assert.equal(u.searchParams.get('state'),'client-state');
 const code=peekCode(u.searchParams.get('code')); assert.equal(code.codeChallenge,'challenge');
 assert.equal(getSession(code.sid).email,'allowed@example.test');
 assert.equal((await handleLogin({state:p.ourState,pbToken:token,browserBound:true})).status,400);
});

test('invalid upstream token fails without consuming retry state or exposing upstream details',async()=>{
 const p=pending();globalThis.fetch=async()=>new Response('sensitive upstream error',{status:401});
 const result=await handleLogin({state:p.ourState,pbToken:'invalid',browserBound:true});
 assert.equal(result.status,401);assert.ok(peekPending(p.ourState));assert.doesNotMatch(result.pageHtml,/sensitive upstream/);
});

test('server enforces email allow-list using refreshed identity',async()=>{
 const p=pending();globalThis.fetch=async()=>sessionResponse('other@example.test');
 assert.equal((await handleLogin({state:p.ourState,pbToken:token,browserBound:true})).status,403);
});
