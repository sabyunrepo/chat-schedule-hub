import {env} from 'cloudflare:workers';
import {z} from 'zod';
import {body,hash,json} from '../../lib/http';
import {getChatGPTUser} from '../chatgpt-auth';
import {applyDelta,readData} from '../../lib/sync-records';
import {readAttention} from '../../lib/attention-store';
import {dispatch} from '../../lib/mcp';
const range=z.object({from:z.string().date().optional(),to:z.string().date().optional(),kind:z.enum(['all','work','crime','personal']).default('all'),limit:z.number().int().min(1).max(100).default(50),offset:z.number().int().min(0).max(100000).default(0)}).strict();
const date=(value:string|null)=>!value?'unknown':value.length===10?value:new Date(value).toLocaleDateString('en-CA',{timeZone:'Asia/Seoul'});
export async function POST(request:Request){
 try{
  const input=await body(request),caller=await getChatGPTUser();
  const result=await dispatch(input,caller?.userId??null,async(name,args,uid)=>{
   if(name==='schedule_apply_delta')return applyDelta(uid,args,await hash(JSON.stringify(args)));
   const stored=await readData(uid),data=stored?.data;
   if(name==='schedule_status')return {events:data?.events.length??0,sources:data?.sources.length??0,updated:stored?.updated??null,remoteCollectorExecution:false};
   if(name==='schedule_attention'){
    return readAttention(uid);
   }
   const q=range.parse(args);if(q.from&&q.to&&q.from>q.to)throw Error('invalid range');
   const events=(data?.events??[]).filter(e=>{const day=date(e.start);return (q.kind==='all'||e.kind===q.kind)&&(!q.from||(day!=='unknown'&&day>=q.from))&&(!q.to||(day!=='unknown'&&day<=q.to))}).sort((a,b)=>(a.start??'z').localeCompare(b.start??'z')||a.id.localeCompare(b.id));
   return {events:events.slice(q.offset,q.offset+q.limit),total:events.length,nextOffset:q.offset+q.limit<events.length?q.offset+q.limit:null,people:data?.people??[],updated:stored?.updated??null};
  });
  return result===null?new Response(null,{status:202}):json(result);
 }catch{return json({jsonrpc:'2.0',id:null,error:{code:-32700,message:'Invalid request'}},400)}
}
