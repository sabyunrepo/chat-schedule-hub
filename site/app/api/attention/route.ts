import {env} from 'cloudflare:workers';
import {user,json,body,sameOrigin,hash} from '../../../lib/http';
import {attention,type Attention} from '../../../lib/attention';
import {readData} from '../../../lib/sync-records';
async function items(uid:string){
 const data=await readData(uid);const out=attention(data?.data.events||[],data?.data.people||[]);
 const changes=await env.DB!.prepare('SELECT id,revision,payload FROM event_history WHERE owner=? ORDER BY created DESC LIMIT 100').bind(uid).all<{id:string;revision:string;payload:string}>();
 for(const row of changes.results){const e=JSON.parse(row.payload);if(!e.excluded)out.push({id:'change:'+row.id+':'+row.revision,revision:row.revision,type:'change',title:e.title,reason:e.status==='cancelled'?'일정 취소':'일정 내용 변경',events:[e]});}
 return out;
}
export async function GET(){try{const uid=await user();const list=await items(uid);const rows=await env.DB!.prepare('SELECT id,revision,state,comment,version,updated FROM review_actions WHERE owner=?').bind(uid).all();return json({items:list,actions:rows.results});}catch{return json({error:'확인함 조회 실패'},401)}}
export async function POST(r:Request){try{
 if(!sameOrigin(r))return json({error:'origin'},403);const uid=await user(),b=await body(r);
 if(typeof b.id!=='string'||b.id.length>1500||typeof b.revision!=='string'||!['open','resolved','dismissed'].includes(b.state)||typeof b.comment!=='string'||b.comment.length>2000||!Number.isInteger(b.version)||b.version<0)return json({error:'invalid'},400);
 const item=(await items(uid)).find(x=>x.id===b.id);if(!item||item.revision!==b.revision)return json({error:'일정이 변경되었습니다. 새로고침해주세요.'},409);
 const stamp=new Date().toISOString(),audit=crypto.randomUUID(),db=env.DB!;
 const statement=b.version===0?db.prepare('INSERT OR IGNORE INTO review_actions VALUES(?,?,?,?,?,1,?)').bind(uid,b.id,b.revision,b.state,b.comment,stamp):db.prepare('UPDATE review_actions SET revision=?,state=?,comment=?,version=version+1,updated=? WHERE owner=? AND id=? AND version=?').bind(b.revision,b.state,b.comment,stamp,uid,b.id,b.version);
 // Atomic CAS update and audit. changes() is scoped to preceding update on this connection.
 const result=await db.batch([statement,db.prepare('INSERT INTO review_history SELECT ?,?,?,?,? WHERE changes()=1').bind(audit,uid,b.id,JSON.stringify({revision:b.revision,state:b.state,comment:b.comment,version:b.version+1}),stamp)]);
 if(!result[0].meta.changes)return json({error:'다른 기기에서 변경되었습니다.'},409);
 return json({ok:true,version:b.version+1});
 }catch{return json({error:'저장 실패'},400)}}
