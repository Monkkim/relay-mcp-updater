import test from 'node:test';
import assert from 'node:assert/strict';
import { normalizeAuthMethods } from '../src/public/auth-methods.js';
test('legacy Relay provider list is usable by current PocketBase SDK',()=>{
 const method=normalizeAuthMethods({authProviders:[{name:'google',authUrl:'https://accounts.google.com/?redirect_uri=',codeVerifier:'pkce'}],emailPassword:true,password:{enabled:false}});
 assert.equal(method.oauth2.enabled,true);
 assert.equal(method.oauth2.providers[0].authURL,'https://accounts.google.com/?redirect_uri=');
 assert.equal(method.oauth2.providers[0].codeVerifier,'pkce');
 assert.equal(method.password.enabled,false);
});
test('modern disabled OAuth cannot be re-enabled by legacy fields',()=>{
 const method=normalizeAuthMethods({oauth2:{enabled:false,providers:[]},authProviders:[{name:'google'}]});
 assert.equal(method.oauth2.enabled,false);assert.deepEqual(method.oauth2.providers,[]);
});
