'use client';
import {useState} from 'react';
import type {Event} from '../lib/model';
import {instant} from '../lib/event-time';
const dayKey=(n:number)=>new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit'}).format(n);
export function MonthCalendar({events,offset,onOffset,onOpen}:{events:Event[];offset:number;onOffset:(n:number)=>void;onOpen:(e:Event)=>void}){
 const now=dayKey(Date.now()),base=new Date(now+'T00:00:00+09:00');
 const month=new Date(Date.UTC(Number(now.slice(0,4)),Number(now.slice(5,7))-1+offset,1));
 const first=month.toISOString().slice(0,10),firstTime=instant(first),weekday=new Date(first+'T00:00:00Z').getUTCDay();
 const cells=Array.from({length:42},(_,i)=>dayKey(firstTime+(i-weekday)*86400000));
 const [selected,setSelected]=useState(now);
 const daily=(day:string)=>{const start=instant(day),end=start+86400000;return events.filter(e=>e.start&&e.status!=='cancelled'&&instant(e.start)<end&&(e.end?instant(e.end)>start:instant(e.start)>=start)).sort((a,b)=>instant(a.start!)-instant(b.start!));};
 return <section className="panel month-panel"><div className="section-title"><button onClick={()=>onOffset(offset-1)} aria-label="이전 달">‹</button><h2>{first.slice(0,7)}</h2><button onClick={()=>onOffset(0)}>이번 달</button><button onClick={()=>onOffset(offset+1)} aria-label="다음 달">›</button></div><div className="month-grid">{['일','월','화','수','목','금','토'].map(x=><b key={x}>{x}</b>)}{cells.map(day=>{const list=daily(day);return <div className={'month-day '+(day===now?'today ':'')+(day.slice(0,7)!==first.slice(0,7)?'outside':'')} key={day}><button className="day-number" aria-label={day+' 일정 '+list.length+'개'} onClick={()=>setSelected(day)}>{Number(day.slice(-2))}<small>{list.length>0?' · '+list.length:''}</small></button><div className="month-events">{list.slice(0,3).map(e=><button key={e.id} className={e.kind} onClick={()=>onOpen(e)}>{e.title}</button>)}{list.length>3&&<button onClick={()=>setSelected(day)}>+{list.length-3}개</button>}</div></div>})}</div><h3>{selected}</h3><div className="month-agenda">{daily(selected).map(e=><button key={e.id} onClick={()=>onOpen(e)}>{e.allDay||e.start?.length===10?'종일':new Date(e.start!).toLocaleTimeString('ko-KR',{hour:'2-digit',minute:'2-digit',timeZone:'Asia/Seoul'})} · {e.title}</button>)}{!daily(selected).length&&<p>일정 없음</p>}</div></section>
}
