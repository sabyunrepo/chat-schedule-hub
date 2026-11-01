import type {Attention} from './attention';
import type {Event} from './model';
export type ReviewAction={id:string;revision:string;state:string;comment:string;version:number;updated?:string};
export const acknowledged=(a?:ReviewAction)=>!!a&&['acknowledged','resolved','dismissed'].includes(a.state);
export function actionKey(a:ReviewAction){return !['acknowledged','tracking'].includes(a.state)&&a.id.startsWith('change:')&&a.id.endsWith(':'+a.revision)?a.id.slice(0,-a.revision.length-1):a.id;}
export function actionFor(item:Attention,actions:ReviewAction[]){return actions.filter(a=>actionKey(a)===item.id).sort((a,b)=>(b.updated??'').localeCompare(a.updated??''))[0];}
export function eventIds(id:string):string[]{
 if(id.startsWith('overlap:')){try{const ids=JSON.parse(id.slice(8));return Array.isArray(ids)&&ids.every(x=>typeof x==='string')?ids:[]}catch{return []}}
 return ['review:','reminder:','change:'].some(p=>id.startsWith(p))?[id.slice(id.indexOf(':')+1)]:[];
}
// Keep watched subjects even after the original condition disappears; use current records only.
export function withTracking(items:Attention[],events:Event[],actions:ReviewAction[]):Attention[]{
 const out=new Map(items.map(i=>[i.id,i]));const current=new Map(events.filter(e=>!e.excluded).map(e=>[e.id,e]));
 for(const a of actions){if(a.state!=='tracking')continue;const id=actionKey(a);if(actionFor({id} as Attention,actions)!==a)continue;
 const related=eventIds(id).map(key=>current.get(key)).filter((e):e is Event=>!!e);if(!related.length)continue;
 const old=out.get(id);out.set(id,{id,revision:related.map(e=>e.version||1).join(':'),type:(id.split(':')[0] as Attention['type']),title:related.map(e=>e.title).join(' / '),reason:old?.reason??'추적 중 · 최신 일정',events:related});
 }
 return [...out.values()].filter(i=>!acknowledged(actionFor(i,actions)));
}
