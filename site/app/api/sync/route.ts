import {env} from 'cloudflare:workers';
import {json,body,hash} from '../../../lib/http';
import {applyDelta} from '../../../lib/sync-records';
export async function POST(r:Request){
 try{
  const token=r.headers.get('authorization')?.replace(/^Bearer /,'');if(!token)return json({error:'unauthorized'},401);
  const pair=await env.DB!.prepare('SELECT owner FROM pairings WHERE hash=?').bind(await hash(token)).first<{owner:string}>();if(!pair)return json({error:'unauthorized'},401);
  const b=await body(r);if(b.schemaVersion!==2)return json({error:'delta protocol v2 required; update collector'},409);
  const result=await applyDelta(pair.owner,b,await hash(JSON.stringify(b)));
  return json(result,result.conflict?409:200);
 }catch{return json({error:'invalid delta'},400);}
}
