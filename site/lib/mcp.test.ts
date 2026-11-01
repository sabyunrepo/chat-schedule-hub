import {test} from 'node:test';
import assert from 'node:assert/strict';
import {dispatch} from './mcp.ts';
import {allowedPushEndpoint} from './push.ts';
test('unauthenticated tool calls cannot reach data',async()=>{
 let calls=0;const result=await dispatch({jsonrpc:'2.0',id:1,method:'tools/call',params:{name:'schedule_apply_delta',arguments:{}}},null,async()=>{calls++});
 assert.equal(calls,0);assert.equal((result as any).error.code,-32001);
});
test('owner comes only from authenticated identity',async()=>{
 let owner='';const result=await dispatch({jsonrpc:'2.0',id:2,method:'tools/call',params:{name:'schedule_list',arguments:{owner:'attacker'}}},'real-owner',async(_n,_a,uid)=>{owner=uid;return {ok:true}});
 assert.equal(owner,'real-owner');assert.equal((result as any).result.isError,undefined);
});
test('tool errors do not expose private exceptions',async()=>{
 const result=await dispatch({jsonrpc:'2.0',id:3,method:'tools/call',params:{name:'schedule_status'}},'u',async()=>{throw Error('secret-token')});
 assert.equal((result as any).result.isError,true);assert.ok(!JSON.stringify(result).includes('secret-token'));
});
test('push endpoints reject SSRF and suffix impersonation',()=>{
 for(const x of ['http://fcm.googleapis.com/x','https://localhost/x','https://jmt17.google.com.evil.test/fcm/send/x','https://jmt17.google.com/other','https://fcm.googleapis.com.attacker.test/x','https://user:pw@fcm.googleapis.com/x','https://fcm.googleapis.com:444/x'])assert.equal(allowedPushEndpoint(x),false);
 for(const x of ['https://fcm.googleapis.com/fcm/send/x','https://web.push.apple.com/x','https://jmt17.google.com/fcm/send/x','https://updates.push.services.mozilla.com/x'])assert.equal(allowedPushEndpoint(x),true);
});
