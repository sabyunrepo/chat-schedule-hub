import {env} from 'cloudflare:workers';
import {body,hash,json} from '../../../../lib/http';
import {attention} from '../../../../lib/attention';
import {readData} from '../../../../lib/sync-records';
export async function POST(r:Request){try{
 const token=r.headers.get('authorization')?.replace(/^Bearer /,'');if(!token)return json({error:'unauthorized'},401);
 const db=env.DB!,pair=await db.prepare('SELECT owner FROM pairings WHERE hash=?').bind(await hash(token)).first<{owner:string}>();if(!pair)return json({error:'unauthorized'},401);
 const uid=pair.owner,b=await body(r),now=Date.now();
 if(b.action==='configure'){
  if(typeof b.publicKey!=='string'||!/^B[A-Za-z0-9_-]{86}$/.test(b.publicKey))throw Error('invalid key');
  await db.prepare('INSERT OR IGNORE INTO push_settings VALUES(?,?)').bind(uid,b.publicKey).run();
  const key=await db.prepare('SELECT public_key FROM push_settings WHERE owner=?').bind(uid).first<{public_key:string}>();return json({ok:key?.public_key===b.publicKey});
 }
 if(b.action==='ack'){
  if(typeof b.subscription!=='string'||typeof b.item!=='string'||typeof b.lease!=='string'||!['sent','retry','gone'].includes(b.result))throw Error('invalid ack');
  const result=await db.prepare('UPDATE push_deliveries SET state=?,until=? WHERE owner=? AND subscription=? AND item=? AND lease=? AND state=?').bind(b.result==='retry'?'pending':'sent',now+900000,uid,b.subscription,b.item,b.lease,'leased').run();
  if(b.result==='gone'&&result.meta.changes)await db.prepare('DELETE FROM push_subscriptions WHERE owner=? AND id=?').bind(uid,b.subscription).run();return json({ok:true});
 }
 if(b.action!=='poll')throw Error('invalid action');
 const subs=await db.prepare('SELECT id,payload,created FROM push_subscriptions WHERE owner=? LIMIT 20').bind(uid).all<{id:string;payload:string;created:string}>();
 if(!subs.results.length)return json({jobs:[]});
 const stored=await readData(uid),candidates=attention(stored?.data.events??[],stored?.data.people??[],now).filter(x=>x.type==='reminder'||x.type==='overlap');
 const changes=await db.prepare('SELECT id,revision,payload,created FROM event_history WHERE owner=? ORDER BY created DESC LIMIT 100').bind(uid).all<{id:string;revision:string;payload:string;created:string}>();
 const actions=await db.prepare('SELECT id,revision,state FROM review_actions WHERE owner=?').bind(uid).all<{id:string;revision:string;state:string}>();
 const jobs=[];
 for(const sub of subs.results){
  const items=[...candidates.map(x=>({...x,created:sub.created})),...changes.results.filter(x=>x.created>=sub.created&&!JSON.parse(x.payload).excluded).map(x=>({id:'change:'+x.id+':'+x.revision,revision:x.revision,type:'change',reason:'일정 변경',created:x.created}))];
  for(const item of items){
   if(actions.results.some(a=>a.id===item.id&&a.revision===item.revision&&a.state!=='open'))continue;
   const id=await hash(JSON.stringify([item.id,item.revision,item.reason])),lease=crypto.randomUUID();
   const claimed=await db.prepare(`INSERT INTO push_deliveries VALUES(?,?,?,'leased',?,?,1) ON CONFLICT(owner,subscription,item) DO UPDATE SET state='leased',lease=excluded.lease,until=excluded.until,attempts=push_deliveries.attempts+1 WHERE push_deliveries.state!='sent' AND push_deliveries.until<? AND push_deliveries.attempts<3`).bind(uid,sub.id,id,lease,now+300000,now).run();
   if(claimed.meta.changes){jobs.push({subscription:sub.id,item:id,lease,info:JSON.parse(sub.payload)});break;}
  }
 }
 return json({jobs});
 }catch{return json({error:'push request failed'},400)}}
