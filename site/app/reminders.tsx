'use client';
import {useEffect,useState} from 'react';
export function Reminders(){
 const [enabled,setEnabled]=useState<boolean|null>(null),[busy,setBusy]=useState(false),[message,setMessage]=useState(''),[supported,setSupported]=useState(true);
 async function check(){
  if(!('Notification'in window)||!('serviceWorker'in navigator)||!('PushManager'in window)){setSupported(false);setEnabled(false);return;}
  setBusy(true);setMessage('');
  try{const registration=await navigator.serviceWorker.getRegistration();const sub=await registration?.pushManager?.getSubscription();if(!sub){setEnabled(false);return;}
   const r=await fetch('/api/push',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'status',endpoint:sub.endpoint})});if(!r.ok)throw Error('알림 상태를 확인하지 못했습니다.');const data=await r.json() as {registered:boolean};setEnabled(data.registered===true);
  }catch(e){setEnabled(null);setMessage(e instanceof Error?e.message:'알림 상태 확인 실패');}finally{setBusy(false)}
 }
 useEffect(()=>{check()},[]);
 async function toggle(){
  if(!('Notification'in window)||!('serviceWorker'in navigator)||!('PushManager'in window)){setMessage('홈 화면에 설치한 앱 또는 푸시 지원 브라우저에서 켜주세요.');return;}
  setBusy(true);setMessage('');
  try{
   // Request permission from this explicit click, before other async operations (Safari).
   if(!enabled&&await Notification.requestPermission()!=='granted')throw Error('알림 권한이 필요합니다.');
   const registration=await Promise.race([navigator.serviceWorker.ready,new Promise<never>((_,reject)=>setTimeout(()=>reject(Error('알림 준비가 지연됩니다. 다시 시도해주세요.')),10000))]);let sub=await registration.pushManager.getSubscription();
   if(enabled&&!sub){setEnabled(false);return;}
   if(enabled&&sub){
    const r=await fetch('/api/push',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'remove',subscription:sub.toJSON()})});
    if(!r.ok)throw Error('알림 해제 실패');await sub.unsubscribe();setEnabled(false);return;
   }
   const r=await fetch('/api/push',{cache:'no-store'});if(!r.ok)throw Error('로그인을 확인해주세요.');const {publicKey}=await r.json() as {publicKey:string|null};
   if(!publicKey)throw Error('수집기 알림 연결이 필요합니다.');
   const bytes=Uint8Array.from(atob(publicKey.replace(/-/g,'+').replace(/_/g,'/')),c=>c.charCodeAt(0));
   sub=sub??await registration.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:bytes});
   const saved=await fetch('/api/push',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({subscription:sub.toJSON(),publicKey})});
   if(!saved.ok){const error=await saved.json().catch(()=>({})) as {error?:string};throw Error(error.error||'알림 연결 저장 실패');}setEnabled(true);setMessage('알림이 켜졌습니다.');
  }catch(e){setMessage(e instanceof Error?e.message:'알림 연결 실패');}finally{setBusy(false)}
 }
 return <div className="push-setting"><div className="setting-row"><div><strong id="push-label">푸시 알림</strong><p id="push-description">일정 변경과 다가오는 약속</p></div><div className="switch-control"><span>{busy?'확인 중':enabled===null?'확인 필요':enabled?'켜짐':'꺼짐'}</span><button type="button" role="switch" aria-labelledby="push-label" aria-describedby="push-description" aria-checked={enabled===true} className="switch" disabled={busy||enabled===null||!supported} onClick={toggle}><span/></button></div></div><p className="setting-description">이 기기에 적용됩니다. 수집기가 실행 중일 때 최대 15분 간격으로 전달됩니다.</p>{!supported&&<p className="setting-description">푸시 지원 브라우저 또는 홈 화면에 설치한 앱에서 설정해주세요.</p>}{message&&<p className="setting-message" role="status">{message}</p>}{enabled===null&&!busy&&<button className="secondary" onClick={check}>다시 확인</button>}</div>
}
