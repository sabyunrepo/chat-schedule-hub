import {env} from 'cloudflare:workers';
import {user,json,body,sameOrigin,hash} from '../../../lib/http';
import {subscription} from '../../../lib/push';
export async function GET(){try{const uid=await user();const row=await env.DB!.prepare('SELECT public_key FROM push_settings WHERE owner=?').bind(uid).first<{public_key:string}>();return json({publicKey:row?.public_key??null});}catch{return json({error:'unauthorized'},401)}}
export async function POST(r:Request){try{
 if(!sameOrigin(r))return json({error:'origin'},403);const uid=await user(),b=await body(r),db=env.DB!;
 if(b.action==='remove'){
  const s=subscription.parse(b.subscription),id=await hash(s.endpoint);
  await db.batch([db.prepare('DELETE FROM push_subscriptions WHERE owner=? AND id=?').bind(uid,id),db.prepare('DELETE FROM push_deliveries WHERE owner=? AND subscription=?').bind(uid,id)]);return json({ok:true});
 }
 const s=subscription.parse(b.subscription),id=await hash(s.endpoint);
 const key=await db.prepare('SELECT public_key FROM push_settings WHERE owner=?').bind(uid).first<{public_key:string}>();
 if(!key||b.publicKey!==key.public_key)return json({error:'알림 연결을 새로고침해주세요.'},409);
 const count=await db.prepare('SELECT count(*) AS n FROM push_subscriptions WHERE owner=?').bind(uid).first<{n:number}>();if((count?.n??0)>=20&&!await db.prepare('SELECT id FROM push_subscriptions WHERE owner=? AND id=?').bind(uid,id).first())return json({error:'기기 한도 초과'},400);
 await db.prepare('INSERT INTO push_subscriptions VALUES(?,?,?,?) ON CONFLICT(owner,id) DO UPDATE SET payload=excluded.payload').bind(uid,id,JSON.stringify(s),new Date().toISOString()).run();return json({ok:true});
 }catch{return json({error:'알림 연결 실패'},400)}}
