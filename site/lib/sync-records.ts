import {env} from 'cloudflare:workers';
import {z} from 'zod';
import {event,person,source} from './model';
export const delta=z.object({schemaVersion:z.literal(2),installationId:z.string().min(1).max(100),sequence:z.number().int().positive().max(Number.MAX_SAFE_INTEGER),records:z.array(z.discriminatedUnion('kind',[
 z.object({kind:z.literal('event'),value:event}),z.object({kind:z.literal('person'),value:person}),z.object({kind:z.literal('source'),value:source})
])).min(1).max(200)});
export async function applyDelta(owner:string,input:unknown,digest:string){
 const b=delta.parse(input), db=env.DB!;
 if(new Set(b.records.map(r=>r.kind+':'+r.value.id)).size!==b.records.length)throw Error('duplicate ids');
 const old=await db.prepare('SELECT sequence,digest FROM sync_heads WHERE owner=? AND installation=?').bind(owner,b.installationId).first<{sequence:number;digest:string}>();
 if(old&&old.sequence>=b.sequence){if(old.sequence===b.sequence&&old.digest!==digest)return {conflict:true};return {ok:true,duplicate:true,sequence:b.sequence};}
 const stamp=new Date().toISOString();
 // Every write checks the head inside the same atomic D1 batch, including races.
 const statements=b.records.map(r=>db.prepare(`INSERT INTO sync_records(owner,installation,kind,id,payload,sequence,updated)
 SELECT ?,?,?,?,?,?,? WHERE NOT EXISTS(SELECT 1 FROM sync_heads WHERE owner=? AND installation=? AND sequence>=?)
 ON CONFLICT(owner,installation,kind,id) DO UPDATE SET payload=excluded.payload,sequence=excluded.sequence,updated=excluded.updated WHERE sync_records.sequence<excluded.sequence`).bind(owner,b.installationId,r.kind,r.value.id,JSON.stringify(r.value),b.sequence,stamp,owner,b.installationId,b.sequence));
 for(const r of b.records){if(r.kind!=='event')continue;
 statements.unshift(db.prepare(`INSERT OR IGNORE INTO event_history(owner,id,revision,payload,created)
 SELECT ?,?,?,?,? WHERE EXISTS(SELECT 1 FROM sync_records WHERE owner=? AND installation=? AND kind='event' AND id=? AND sequence<? AND coalesce(json_extract(payload,'$.version'),1)<?)
 AND NOT EXISTS(SELECT 1 FROM sync_heads WHERE owner=? AND installation=? AND sequence>=?)`).bind(owner,r.value.id,String(r.value.version||1),JSON.stringify(r.value),stamp,owner,b.installationId,r.value.id,b.sequence,r.value.version||1,owner,b.installationId,b.sequence));
 }
 statements.push(db.prepare(`INSERT INTO sync_heads VALUES(?,?,?,?,?) ON CONFLICT(owner,installation) DO UPDATE SET sequence=excluded.sequence,digest=excluded.digest,updated=excluded.updated WHERE sync_heads.sequence<excluded.sequence`).bind(owner,b.installationId,b.sequence,digest,stamp));
 await db.batch(statements);
 const accepted=await db.prepare('SELECT sequence,digest FROM sync_heads WHERE owner=? AND installation=?').bind(owner,b.installationId).first<{sequence:number;digest:string}>();
 if(accepted?.sequence===b.sequence&&accepted.digest!==digest)return {conflict:true};
 return {ok:true,sequence:b.sequence,records:b.records.length};
}
export async function readData(owner:string){
 const rows=await env.DB!.prepare('SELECT kind,payload,updated FROM sync_records WHERE owner=? ORDER BY updated,id').bind(owner).all<{kind:string;payload:string;updated:string}>();
 if(!rows.results.length)return null;
 const events=new Map(),people=new Map(),sources=new Map();let updated='';
 for(const r of rows.results){const value=JSON.parse(r.payload);if(r.kind==='event'&&value.excluded===true)continue;(r.kind==='event'?events:r.kind==='person'?people:sources).set(value.id,value);if(r.updated>updated)updated=r.updated;}
 return {data:{schemaVersion:1,events:[...events.values()],people:[...people.values()],sources:[...sources.values()],generatedAt:updated},updated};
}
