import {test} from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
import {clearAppCaches,updateTarget} from '../lib/app-update.ts';
const version='0123456789abcdefabcd';
test('version reload preserves path/query/hash and prevents same-version loops',()=>{
 const url=updateTarget('old',version,'https://moa.test/?view=chat#message')!;
 assert.equal(new URL(url).searchParams.get('view'),'chat');assert.equal(new URL(url).hash,'#message');
 assert.equal(updateTarget('old',version,url),null);assert.equal(updateTarget(version,version,url),null);
 assert.equal(updateTarget('old','<script>',url),null);
});
test('cache cleanup touches only Moa app caches',async()=>{
 const removed:string[]=[];await clearAppCaches({keys:async()=>['moa-static-v1','moa:old','other-site','authentication'],delete:async k=>{removed.push(k);return true}});
 assert.deepEqual(removed,['moa-static-v1','moa:old']);
});
function worker(ack:boolean){
 const handlers:Record<string,(e:any)=>void>={},removed:string[]=[],navigated:string[]=[],messages:unknown[]=[],requests:unknown[]=[];
 const self:any={location:{origin:'https://moa.test'},skipWaiting:async()=>{},addEventListener:(name:string,fn:any)=>handlers[name]=fn,registration:{showNotification:async()=>{}},clients:{claim:async()=>{},matchAll:async()=>[{id:'one',url:'https://moa.test/?view=chat',postMessage:(message:any)=>{messages.push(message);if(ack)handlers.message({data:{type:'MOA_UPDATE_ACK',version:message.version},source:{id:'one'}})},navigate:async(url:string)=>navigated.push(url)}]}};
 vm.runInNewContext(readFileSync(new URL('../scripts/service-worker.js',import.meta.url),'utf8').replaceAll('__MOA_BUILD_ID__',version),{self,caches:{keys:async()=>['moa-old','unrelated'],delete:async(k:string)=>removed.push(k)},URL,Response,fetch:async(_req:unknown,options:unknown)=>{requests.push(options);return new Response('network')},setTimeout:(f:()=>void)=>f()});
 return {handlers,removed,navigated,messages,requests};
}
test('new worker cleans app caches, leaves draft-aware clients in control and migrates legacy clients',async()=>{
 for(const ack of [true,false]){const w=worker(ack);let promise:Promise<void>|undefined;w.handlers.activate({waitUntil:(p:Promise<void>)=>promise=p});await promise;assert.deepEqual(w.removed,['moa-old']);assert.equal(w.messages.length,1);assert.equal(w.navigated.length,ack?0:1);if(!ack)assert.equal(new URL(w.navigated[0]).searchParams.get('__moa_v'),version);}
});
test('navigation uses fresh network, API responses are never intercepted/cached',async()=>{
 const w=worker(true);let response:Promise<Response>|undefined;
 w.handlers.fetch({request:{mode:'navigate'},respondWith:(p:Promise<Response>)=>response=p});assert.equal(await (await response!).text(),'network');assert.equal((w.requests[0] as {cache:string}).cache,'no-store');
 let intercepted=false;w.handlers.fetch({request:{mode:'cors'},respondWith:()=>intercepted=true});assert.equal(intercepted,false);
 assert.ok(w.handlers.push);assert.ok(w.handlers.notificationclick);
});
