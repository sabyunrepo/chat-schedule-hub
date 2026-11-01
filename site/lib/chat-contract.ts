import {z} from 'zod';
export const searchArgs=z.object({query:z.string().max(100).default(''),from:z.string().date().nullable().default(null),to:z.string().date().nullable().default(null),kind:z.enum(['all','work','crime','personal']).default('all'),onlyMe:z.boolean().default(true),offset:z.number().int().min(0).max(2000).default(0)}).strict();
export const undatedArgs=z.object({kind:z.enum(['all','work','crime','personal']).default('all'),onlyMe:z.boolean().default(true)}).strict();
export const detailArgs=z.object({id:z.string().min(1).max(200)}).strict();
export const reviewArgs=z.object({id:z.string().min(1).max(1500),state:z.enum(['acknowledged','tracking']),comment:z.string().max(2000).default('')}).strict();
export const chatInput=z.object({thread:z.string().uuid(),requestId:z.string().uuid(),text:z.string().trim().min(1).max(4000)}).strict();
export type Proposal={id:string;revision:string;title:string;state:'acknowledged'|'tracking';comment:string;version:number;actionId?:string};
export type ChatReply={text:string;references:{id:string;title:string}[];proposals:Proposal[];lookups?:{name:string;input:unknown;count?:number;error?:boolean}[]};
export type ChatTurn={id:string;question:string;reply:ChatReply|null;status:string;created:string};
export type Message={role:'system'|'user'|'assistant'|'tool';content:string|null;tool_call_id?:string;tool_calls?:ToolCall[]};
export type ToolCall={id:string;type:'function';function:{name:string;arguments:string}};
const fn=(name:string,description:string,properties:Record<string,unknown>,required:string[])=>({type:'function',function:{name,description,parameters:{type:'object',properties,required,additionalProperties:false}}});
export const chatTools=[
 fn('schedule_search','현재 저장된 일정을 조회합니다. query는 제목/설명의 고유명사 검색어이며 크라임씬/미정/다가오는 같은 필터 단어는 넣지 말고 빈 문자열로 두세요. 날짜 미정은 schedule_undated를 사용하세요. 기간은 한국 날짜, to는 미포함. 기본은 내 일정만. 다음 페이지는 offset을 20 늘립니다.',{query:{type:'string'},from:{type:['string','null']},to:{type:['string','null']},kind:{type:'string',enum:['all','work','crime','personal']},onlyMe:{type:'boolean'},offset:{type:'integer'}},['query','from','to','kind','onlyMe','offset']),
 fn('schedule_undated','날짜 미정 일정을 조회합니다. 날짜 미정 질문에는 이 도구를 사용합니다. 제목에 미정이 없어도 찾습니다.',{kind:{type:'string',enum:['all','work','crime','personal']},onlyMe:{type:'boolean'}},['kind','onlyMe']),
 fn('schedule_get','일정 하나의 최신 상세·판단 근거를 읽습니다.',{id:{type:'string'}},['id']),
 fn('schedule_attention','확인함의 미확인·추적 항목을 읽습니다.',{},[]),
 fn('propose_review','사용자가 요청한 확인 또는 추적 변경안을 만듭니다. 먼저 schedule_attention으로 항목 id를 조회하세요. 일정 id와 확인함 항목 id는 다릅니다. 아직 저장하지 않으며 사용자가 적용 버튼을 눌러야 합니다.',{id:{type:'string'},state:{type:'string',enum:['acknowledged','tracking']},comment:{type:'string'}},['id','state','comment'])
];
export interface ChatProvider {complete(messages:Message[],signal:AbortSignal):Promise<Message>}
export function codysseyProvider(key:string,request:typeof fetch=fetch):ChatProvider{return {async complete(messages,signal){
 const response=await request('https://copa.codyssey.kr/v1/chat/completions',{method:'POST',headers:{Authorization:'Bearer '+key,'Content-Type':'application/json'},body:JSON.stringify({model:'gpt-5.4-mini',messages,tools:chatTools,tool_choice:'auto',max_completion_tokens:1800}),signal});
 if(!response.ok)throw Error(response.status===429?'모델 사용 한도에 도달했습니다. 잠시 후 다시 시도해주세요.':'모델 연결에 실패했습니다.');
 const b=await response.json() as {choices?:{message?:Message}[]};const m=b.choices?.[0]?.message;
 if(!m||m.role!=='assistant'||(m.content!==null&&typeof m.content!=='string')||(m.tool_calls&&(!Array.isArray(m.tool_calls)||m.tool_calls.length>6)))throw Error('모델 응답을 확인하지 못했습니다.');
 return m;
}}}
export async function runChat(provider:ChatProvider,messages:Message[],execute:(name:string,input:unknown)=>Promise<unknown>,signal:AbortSignal){
 let count=0;
 for(let round=0;round<5;round++){
  signal.throwIfAborted();const next=await provider.complete(messages,signal);messages.push(next);
  if(!next.tool_calls?.length){if(!next.content?.trim())throw Error('답변이 비어 있습니다.');return next.content;}
  for(const call of next.tool_calls){if(++count>8)throw Error('조회 범위가 큽니다. 기간이나 대상을 좁혀주세요.');
   let result:unknown;try{if(call.type!=='function'||typeof call.id!=='string')throw Error();result=await execute(call.function.name,JSON.parse(call.function.arguments));}catch{result={error:'도구 인수가 잘못되었거나 현재 항목이 없습니다. 값을 추측해 변경하지 마세요.'};}
   messages.push({role:'tool',tool_call_id:call.id,content:JSON.stringify(result)});
  }
 }
 throw Error('조회가 길어졌습니다. 기간이나 대상을 좁혀주세요.');
}

export function resolveReviewItem<T extends {id:string;events:{id:string}[]}>(items:T[],id:string):T|undefined{const exact=items.find(i=>i.id===id);if(exact)return exact;const matches=items.filter(i=>i.events.some(e=>e.id===id));return matches.length===1?matches[0]:undefined;}
