import {env} from 'cloudflare:workers';
import {user,json,body,sameOrigin} from '../../../lib/http';
import {actionKey} from '../../../lib/attention-state';
import {readAttention} from '../../../lib/attention-store';
export async function GET(){try{return json(await readAttention(await user()));}catch{return json({error:'확인함 조회 실패'},401)}}
export async function POST(r:Request){try{
 if(!sameOrigin(r))return json({error:'origin'},403);const uid=await user(),b=await body(r);
 if(typeof b.id!=='string'||b.id.length>1500||typeof b.revision!=='string'||!['acknowledged','tracking'].includes(b.state)||typeof b.comment!=='string'||b.comment.length>2000||!Number.isInteger(b.version)||b.version<0)return json({error:'invalid'},400);
 const current=await readAttention(uid);
 const item=current.items.find(x=>x.id===b.id);if(!item||item.revision!==b.revision)return json({error:'일정이 변경되었습니다. 새로고침해주세요.'},409);
 const existing=current.actions.find(a=>a.id===b.actionId);
 if(b.version>0&&(!existing||existing.version!==b.version||actionKey(existing)!==b.id))return json({error:'다른 기기에서 변경되었습니다.'},409);
 const actionId=existing?.id??b.id;
 const stamp=new Date().toISOString(),audit=crypto.randomUUID(),db=env.DB!;
 const statement=b.version===0?db.prepare('INSERT OR IGNORE INTO review_actions VALUES(?,?,?,?,?,1,?)').bind(uid,b.id,b.revision,b.state,b.comment,stamp):db.prepare('UPDATE review_actions SET id=?,revision=?,state=?,comment=?,version=version+1,updated=? WHERE owner=? AND id=? AND version=?').bind(b.id,b.revision,b.state,b.comment,stamp,uid,actionId,b.version);
 // Atomic CAS update and audit. changes() is scoped to preceding update on this connection.
 const result=await db.batch([statement,db.prepare('INSERT INTO review_history SELECT ?,?,?,?,? WHERE changes()=1').bind(audit,uid,b.id,JSON.stringify({revision:b.revision,state:b.state,comment:b.comment,version:b.version+1}),stamp)]);
 if(!result[0].meta.changes)return json({error:'다른 기기에서 변경되었습니다.'},409);
 return json({ok:true,version:b.version+1});
 }catch{return json({error:'저장 실패'},400)}}
