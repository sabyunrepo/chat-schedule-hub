import {instant} from './event-time.ts';
export function seoulDay(now:number){return new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit'}).format(now)}
export function scheduleWindow(now:number,view:'week'|'month',offset=0){
 const days=view==='week'?7:28;
 const start=instant(seoulDay(now))+offset*days*86400000;
 return {start:new Date(start),end:new Date(start+days*86400000),days};
}
