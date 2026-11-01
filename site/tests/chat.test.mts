import {test} from 'node:test';
import assert from 'node:assert/strict';
import {runChat,codysseyProvider,chatInput,searchArgs,reviewArgs,type Message} from '../lib/chat-contract.ts';
test('tool results feed the next model request; proposals do not execute a write',async()=>{
 const messages:Message[]=[{role:'user',content:'일정 확인'}];let rounds=0,executed=0;
 const provider={complete:async()=>++rounds===1?{role:'assistant' as const,content:null,tool_calls:[{id:'one',type:'function' as const,function:{name:'schedule_search',arguments:'{"onlyMe":true}'}}]}:{role:'assistant' as const,content:'조회 완료'}};
 assert.equal(await runChat(provider,messages,async(name,args)=>{executed++;assert.equal(name,'schedule_search');assert.deepEqual(args,{onlyMe:true});return {events:[]}},new AbortController().signal),'조회 완료');
 assert.equal(executed,1);assert.equal(messages[2].role,'tool');assert.equal(messages[2].tool_call_id,'one');
});
test('malformed tool arguments are returned as errors, without execution',async()=>{
 let round=0,executed=0;const messages:Message[]=[];
 await runChat({complete:async()=>++round===1?{role:'assistant',content:null,tool_calls:[{id:'x',type:'function',function:{name:'schedule_search',arguments:'{'}}]}:{role:'assistant',content:'실패'}},messages,async()=>{executed++;},new AbortController().signal);
 assert.equal(executed,0);assert.match(messages[1].content!,/error/);
});
test('limits tool loops and honors cancellation before provider execution',async()=>{
 const provider={complete:async()=>({role:'assistant' as const,content:null,tool_calls:[{id:'x',type:'function' as const,function:{name:'schedule_attention',arguments:'{}'}}]})};
 await assert.rejects(runChat(provider,[],async()=>({}),new AbortController().signal),/조회가 길어/);
 const c=new AbortController();c.abort();await assert.rejects(runChat(provider,[],async()=>({}),c.signal));
});
test('contract rejects foreign owner and arbitrary review states; bounded query',()=>{
 assert.equal(searchArgs.safeParse({owner:'other'}).success,false);assert.equal(reviewArgs.safeParse({id:'x',state:'delete'}).success,false);assert.equal(searchArgs.safeParse({offset:90000}).success,false);assert.equal(chatInput.safeParse({thread:crypto.randomUUID(),requestId:crypto.randomUUID(),text:' '}).success,false);
});
test('Codyssey key stays in request header and provider errors are sanitized',async()=>{
 let sent=false;const provider=codysseyProvider('secret',async(url,init)=>{assert.equal(url,'https://copa.codyssey.kr/v1/chat/completions');assert.equal((init?.headers as Record<string,string>).Authorization,'Bearer secret');assert.ok(!String(init?.body).includes('secret'));sent=true;return new Response('secret internal error',{status:500})});
 await assert.rejects(provider.complete([],new AbortController().signal),/모델 연결/);assert.equal(sent,true);
});
