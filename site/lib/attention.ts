import type {Event,Person} from './model';
import {instant,phase} from './event-time.ts';
export type Attention={id:string;revision:string;type:'review'|'overlap'|'reminder'|'change';title:string;reason:string;events:Event[]};
export function attention(events:Event[],people:Person[],now=Date.now()):Attention[]{
 const me=new Set(people.filter(p=>p.isMe).map(p=>p.id)),out:Attention[]=[];
 const active=events.filter(e=>!e.excluded&&!['past','inactive'].includes(phase(e,now)));
 for(const e of active){
  if(e.needsReview)out.push({id:'review:'+e.id,revision:String(e.version||1),type:'review',title:e.title,reason:'날짜·참석·내용 확인 필요',events:[e]});
  const time=e.start?instant(e.start):NaN;
  if(e.status==='confirmed'&&e.participants.some(p=>me.has(p))&&!e.allDay&&time>now&&time-now<=86400000)out.push({id:'reminder:'+e.id,revision:String(e.version||1),type:'reminder',title:e.title,reason:time-now<=3600000?'1시간 이내 시작':'24시간 이내 시작',events:[e]});
 }
 const timed=active.filter(e=>e.status==='confirmed'&&!e.allDay&&e.start&&e.end&&e.participants.some(p=>me.has(p))).sort((a,b)=>instant(a.start!)-instant(b.start!));
 for(let i=0;i<timed.length;i++)for(let j=i+1;j<timed.length;j++){
  const a=timed[i],b=timed[j];if(instant(b.start!)>=instant(a.end!))break;
  if(!a.participants.some(p=>me.has(p)&&b.participants.includes(p)))continue;
  const pair=[a,b].sort((x,y)=>x.id.localeCompare(y.id));
  out.push({id:'overlap:'+JSON.stringify(pair.map(e=>e.id)),revision:pair.map(e=>e.version||1).join(':'),type:'overlap',title:a.title+' / '+b.title,reason:'내 확정 일정의 시간이 겹칩니다. 같은 모임인지 확인하세요.',events:pair});
 }
 return out;
}
