import {env} from 'cloudflare:workers';
import {z} from 'zod';
import {searchArgs,undatedArgs,resolveReviewItem,detailArgs,reviewArgs,type ChatReply} from './chat-contract';
import {readAttention} from './attention-store';
import {actionFor} from './attention-state';
import {phase} from './event-time';
import type {Event,Person} from './model';
// Rank before filtering so an old version cannot reappear after a correction/exclusion.
const latest=`WITH latest AS (SELECT payload,id,row_number() OVER(PARTITION BY id ORDER BY updated DESC,installation DESC) AS rank FROM sync_records WHERE owner=? AND kind='event') SELECT payload FROM latest WHERE rank=1 AND coalesce(json_extract(payload,'$.excluded'),0)=0`;
export function scheduleTools(owner:string){
 const reply:ChatReply={text:'',references:[],proposals:[]};
 let people:Person[]|undefined;
 async function persons(){if(!people){const r=await env.DB!.prepare("SELECT payload FROM sync_records WHERE owner=? AND kind='person' ORDER BY updated").bind(owner).all<{payload:string}>();people=[...new Map(r.results.map(x=>{const p=JSON.parse(x.payload) as Person;return [p.id,p] as const})).values()];}return people;}
 async function brief(e:Event){if(!reply.references.some(x=>x.id===e.id))reply.references.push({id:e.id,title:e.title});const ps=await persons();return {id:e.id,title:e.title,kind:e.kind,status:e.status,timePhase:phase(e,Date.now()),endExclusive:e.endExclusive??false,start:e.start,end:e.end,allDay:e.allDay??false,location:e.location,participants:e.participants.map(id=>({id,name:ps.find(p=>p.id===id)?.name??'미확인',isMe:ps.some(p=>p.id===id&&p.isMe)})),needsReview:e.needsReview,source:e.source,version:e.version};}
 async function execute(name:string,input:unknown):Promise<unknown>{
  if(name==='schedule_search'||name==='schedule_undated'){
   const isUndated=name==='schedule_undated';
   const a=isUndated?searchArgs.parse({...undatedArgs.parse(input),query:'',from:null,to:null}):searchArgs.parse(input),ps=await persons(),me=ps.filter(p=>p.isMe).map(p=>p.id);
   if(a.onlyMe&&!me.length)return {events:[],warning:'내 인물이 연결되지 않아 내 일정을 판별할 수 없습니다.'};
   let sql=latest;const values:unknown[]=[owner];
   if(isUndated)sql+=" AND json_extract(payload,'$.start') IS NULL";
   if(a.query){sql+=" AND instr(lower(json_extract(payload,'$.title') || ' ' || coalesce(json_extract(payload,'$.description'),'')),lower(?))>0";values.push(a.query);}
   if(a.kind!=='all'){sql+=" AND json_extract(payload,'$.kind')=?";values.push(a.kind);}
   // ISO timestamps and all-day dates normalized to local calendar dates for overlap search.
   const start="date(json_extract(payload,'$.start'),CASE WHEN length(json_extract(payload,'$.start'))=10 THEN '+0 hours' ELSE '+9 hours' END)";
   const finish="date(coalesce(json_extract(payload,'$.end'),json_extract(payload,'$.start')),CASE WHEN length(coalesce(json_extract(payload,'$.end'),json_extract(payload,'$.start')))=10 THEN '+0 hours' ELSE '+9 hours' END)";
   if(a.from){sql+=` AND (${finish}>=?)`;values.push(a.from);}
   if(a.to){sql+=` AND (${start}<?)`;values.push(a.to);}
   if(a.onlyMe){sql+=` AND EXISTS(SELECT 1 FROM json_each(json_extract(payload,'$.participants')) WHERE value IN (${me.map(()=>'?').join(',')}))`;values.push(...me);}
   sql+=" ORDER BY json_extract(payload,'$.start'),id LIMIT 21 OFFSET ?";values.push(a.offset);
   const r=await env.DB!.prepare(sql).bind(...values).all<{payload:string}>();return {events:await Promise.all(r.results.slice(0,20).map(x=>brief(JSON.parse(x.payload)))),hasMore:r.results.length>20,nextOffset:r.results.length>20?a.offset+20:null,scope:'저장된 일정만 조회. 취소·완료 상태를 구별하세요.'};
  }
  if(name==='schedule_get'){const a=detailArgs.parse(input),r=await env.DB!.prepare(latest+' AND id=? LIMIT 1').bind(owner,a.id).first<{payload:string}>();if(!r)return {error:'일정 없음'};const e=JSON.parse(r.payload) as Event;return {...await brief(e),description:e.description,evidence:e.evidenceDetails?.slice(0,3).map(x=>({source:x.source,summary:x.summary,excerpt:x.excerpt.slice(0,600),sentAt:x.sentAt}))??[],version:e.version};}
  if(name==='schedule_attention'){z.object({}).strict().parse(input);const data=await readAttention(owner);return {items:data.items.slice(0,30).map(i=>({id:i.id,title:i.title,reason:i.reason,state:actionFor(i,data.actions)?.state??'unread',events:i.events.map(e=>({id:e.id,title:e.title,start:e.start}))})),hasMore:data.items.length>30};}
  if(name==='propose_review'){const a=reviewArgs.parse(input),d=await readAttention(owner),i=resolveReviewItem(d.items,a.id);if(!i)return {error:'항목 식별자를 확인할 수 없습니다. schedule_attention에서 현재 항목 id를 조회해 다시 요청하세요.'};const action=actionFor(i,d.actions);const p={...a,id:i.id,title:i.title,revision:i.revision,version:action?.version??0,actionId:action?.id};reply.proposals=reply.proposals.filter(x=>x.id!==p.id);reply.proposals.push(p);return {proposal:p,saved:false,next:'사용자가 적용 버튼을 눌러야 저장됩니다.'};}
  throw Error('unknown tool');
 }
 return {reply,execute};
}
