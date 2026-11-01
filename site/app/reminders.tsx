'use client';
import {useEffect,useRef,useState} from 'react';
import type {Attention} from '../lib/attention';
export function Reminders(){
 const [enabled,setEnabled]=useState(false),[message,setMessage]=useState(''),seen=useRef(new Set<string>());
 useEffect(()=>{if(!enabled)return;let alive=true;
 async function check(){try{const response=await fetch('/api/attention',{cache:'no-store'});if(!response.ok)return;const data=await response.json() as {items:Attention[];actions:{id:string;state:string;revision:string}[]};
 const fresh=data.items.filter(i=>['change','reminder','overlap'].includes(i.type)&&!data.actions.some(a=>a.id===i.id&&a.revision===i.revision&&a.state!=='open')).filter(i=>!seen.current.has(i.id+':'+i.revision+':'+i.reason));
 if(!alive||!fresh.length)return;
 for(const item of fresh)seen.current.add(item.id+':'+item.revision+':'+item.reason);
 const registration=await navigator.serviceWorker.ready;
 await registration.showNotification('모아 · 확인할 일정 '+fresh.length+'개',{body:fresh.slice(0,2).map(i=>i.title+' · '+i.reason).join('\n'),tag:'moa-schedule-update'});
 }catch{if(alive)setMessage('알림 실패')}}
 check();const timer=setInterval(check,60000);return()=>{alive=false;clearInterval(timer)}},[enabled]);
 async function enable(){if(!('Notification'in window)||!('serviceWorker'in navigator)){setMessage('이 기기에서는 알림 미지원');return;}const permission=await Notification.requestPermission();if(permission==='granted'){setEnabled(true);setMessage('');}else setMessage('알림 권한 없음');}
 return <><button className="secondary" onClick={()=>enabled?setEnabled(false):enable()}>{enabled?'앱 열림 알림 끄기':'앱 열림 알림 켜기'}</button>{message&&<small role="status">{message}</small>}</>
}
