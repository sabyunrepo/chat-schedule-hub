import type {Event} from './model';
import {instant} from './event-time';
export function layoutEvents(events:Event[],start:number,days:number,dayWidth=120){
 const width=days*dayWidth, lanes:{right:number,height:number}[]=[];
 const items=events.filter(e=>e.start).sort((a,b)=>instant(a.start!)-instant(b.start!)||a.id.localeCompare(b.id)).map(event=>{
  const left=Math.max(0,(instant(event.start!)-start)/86400000*dayWidth);
  const right=Math.min(width,(instant(event.end||event.start!)-start)/86400000*dayWidth);
  const barWidth=Math.max(4,right-left);
  const labelWidth=Math.min(width,Math.max(200,Math.min(320,event.title.length*12)));
  const labelLeft=Math.min(left,width-labelWidth);
  const height=Math.max(62,Math.ceil(event.title.length*12/labelWidth)*18+36);
  let lane=lanes.findIndex(l=>l.right+12<=labelLeft);
  if(lane<0){lane=lanes.length;lanes.push({right:0,height:0})}
  lanes[lane]={right:Math.max(left+barWidth,labelLeft+labelWidth),height:Math.max(lanes[lane].height,height)};
  return {event,left,barWidth,labelLeft,labelWidth,lane};
 });
 return {items:items.map(x=>({...x,top:12+lanes.slice(0,x.lane).reduce((a,l)=>a+l.height,0)})),height:24+lanes.reduce((a,l)=>a+l.height,0)};
}
