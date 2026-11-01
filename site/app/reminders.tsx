'use client';
import {useEffect,useState} from 'react';
export function Reminders(){
 const [enabled,setEnabled]=useState(false),[busy,setBusy]=useState(false),[message,setMessage]=useState('');
 useEffect(()=>{let alive=true;if('serviceWorker'in navigator)navigator.serviceWorker.ready.then(r=>r.pushManager?.getSubscription()).then(async s=>{if(!s)return;const r=await fetch('/api/push',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'status',endpoint:s.endpoint})});if(!r.ok)return;const data=await r.json() as {registered:boolean};if(alive)setEnabled(data.registered===true);}).catch(()=>{});return()=>{alive=false};},[]);
 async function toggle(){
  if(!('Notification'in window)||!('serviceWorker'in navigator)||!('PushManager'in window)){setMessage('홈 화면에 설치한 앱 또는 푸시 지원 브라우저에서 켜주세요.');return;}
  setBusy(true);setMessage('');
  try{
   // Request permission from this explicit click, before other async operations (Safari).
   if(!enabled&&await Notification.requestPermission()!=='granted')throw Error('알림 권한이 필요합니다.');
   const registration=await navigator.serviceWorker.ready;let sub=await registration.pushManager.getSubscription();
   if(enabled&&sub){
    const r=await fetch('/api/push',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'remove',subscription:sub.toJSON()})});
    if(!r.ok)throw Error('알림 해제 실패');await sub.unsubscribe();setEnabled(false);return;
   }
   const r=await fetch('/api/push',{cache:'no-store'});if(!r.ok)throw Error('로그인을 확인해주세요.');const {publicKey}=await r.json() as {publicKey:string|null};
   if(!publicKey)throw Error('수집기 알림 연결이 필요합니다.');
   const bytes=Uint8Array.from(atob(publicKey.replace(/-/g,'+').replace(/_/g,'/')),c=>c.charCodeAt(0));
   sub=sub??await registration.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:bytes});
   const saved=await fetch('/api/push',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({subscription:sub.toJSON(),publicKey})});
   if(!saved.ok){const error=await saved.json().catch(()=>({})) as {error?:string};throw Error(error.error||'알림 연결 저장 실패');}setEnabled(true);setMessage('수집기가 실행 중일 때 최대 15분 간격으로 전달됩니다.');
  }catch(e){setMessage(e instanceof Error?e.message:'알림 연결 실패');}finally{setBusy(false)}
 }
 return <><button className="secondary" disabled={busy} onClick={toggle}>{busy?'연결 중':enabled?'푸시 알림 끄기':'푸시 알림 켜기'}</button>{message&&<small role="status">{message}</small>}</>
}
