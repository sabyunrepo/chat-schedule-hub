import {env} from 'cloudflare:workers';
import {attention,type Attention} from './attention';
import {readData} from './sync-records';
import {withTracking,type ReviewAction} from './attention-state';
export async function readAttention(uid:string){
 const [stored,actions,history]=await Promise.all([readData(uid),env.DB!.prepare('SELECT id,revision,state,comment,version,updated FROM review_actions WHERE owner=?').bind(uid).all<ReviewAction>(),env.DB!.prepare('SELECT id,revision,payload FROM event_history WHERE owner=? ORDER BY created DESC LIMIT 100').bind(uid).all<{id:string;revision:string;payload:string}>()]);
 const events=stored?.data.events??[],list:Attention[]=attention(events,stored?.data.people??[]),seen=new Set<string>(),current=new Map(events.map(e=>[e.id,e]));
 for(const row of history.results){if(seen.has(row.id))continue;seen.add(row.id);const e=current.get(row.id);if(e&&!e.excluded)list.push({id:'change:'+e.id,revision:String(e.version||1),type:'change',title:e.title,reason:e.status==='cancelled'?'일정 취소':'일정 내용 변경',events:[e]});}
 return {items:withTracking(list,events,actions.results),actions:actions.results};
}
