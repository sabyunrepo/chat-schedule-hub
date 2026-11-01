export const validBuild=(value:unknown):value is string=>typeof value==='string'&&/^[a-f0-9]{20}$/.test(value);
export function updateTarget(current:string,next:unknown,href:string):string|null{
 if(!validBuild(next)||next===current)return null;
 const url=new URL(href);if(url.searchParams.get('__moa_v')===next)return null;
 url.searchParams.set('__moa_v',next);return url.href;
}
export async function clearAppCaches(storage:Pick<CacheStorage,'keys'|'delete'>){const keys=await storage.keys();await Promise.all(keys.filter(k=>/^moa[-:]/.test(k)).map(k=>storage.delete(k)));}
