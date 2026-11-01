'use client';
import {useEffect,useRef,useState} from 'react';
import {BUILD_ID} from '../lib/build-info';
import {clearAppCaches,updateTarget,validBuild} from '../lib/app-update';
function editing(){return !!document.querySelector('[aria-busy="true"]')||[...document.querySelectorAll<HTMLInputElement|HTMLTextAreaElement>('input:not([type=checkbox]):not([type=radio]),textarea')].some(e=>!e.readOnly&&!e.disabled&&!!e.value.trim());}
export function AppUpdater(){
 const [next,setNext]=useState(''),[problem,setProblem]=useState(false),pending=useRef(''),reloading=useRef(false);
 const apply=useRef<(force?:boolean)=>Promise<void>>(async()=>{});
 useEffect(()=>{
  let disposed=false,checking=false,registration:ServiceWorkerRegistration|undefined;
  apply.current=async(force=false)=>{
   if(disposed||reloading.current||!pending.current||document.hidden||!navigator.onLine||(!force&&editing()))return;
   const target=updateTarget(BUILD_ID,pending.current,location.href);
   if(!target){setProblem(true);return;} // Never loop if an intermediary still serves an old document.
   reloading.current=true;
   try{if('caches'in window)await clearAppCaches(caches);}catch{/* Network reload still works when storage is unavailable. */}
   location.replace(target);
  };
  function found(version:unknown){if(!validBuild(version))return;if(version===BUILD_ID){pending.current='';setNext('');setProblem(false);return;}pending.current=version;setNext(version);void apply.current();}
  async function check(){
   if(disposed||checking||document.hidden||!navigator.onLine)return;checking=true;
   try{const r=await fetch('/api/version?_='+Date.now(),{cache:'no-store',signal:AbortSignal.timeout(8000)});if(r.ok){const b=await r.json() as {version?:unknown};if(!disposed)found(b.version);}}catch{/* Offline and auth errors are not version changes. */}
   finally{checking=false;}
   void registration?.update().catch(()=>{});
  }
  function message(e:MessageEvent){if(e.data?.type!=='MOA_UPDATE_READY'||!validBuild(e.data.version))return;
   (e.source as ServiceWorker|null)?.postMessage({type:'MOA_UPDATE_ACK',version:e.data.version});void check();
  }
  const resume=()=>{void check();void apply.current()};
  if('serviceWorker'in navigator){navigator.serviceWorker.addEventListener('message',message);navigator.serviceWorker.addEventListener('controllerchange',resume);
   void navigator.serviceWorker.register('/sw.js',{updateViaCache:'none'}).then(r=>{registration=r;return r.update()}).catch(()=>{});
  }
  const url=new URL(location.href);if(url.searchParams.get('__moa_v')===BUILD_ID){url.searchParams.delete('__moa_v');history.replaceState(history.state,'',url.href);}
  void check();const poll=setInterval(check,30000),idle=setInterval(()=>{void apply.current()},1500);
  window.addEventListener('focus',resume);window.addEventListener('online',resume);window.addEventListener('pageshow',resume);document.addEventListener('visibilitychange',resume);
  return()=>{disposed=true;clearInterval(poll);clearInterval(idle);window.removeEventListener('focus',resume);window.removeEventListener('online',resume);window.removeEventListener('pageshow',resume);document.removeEventListener('visibilitychange',resume);navigator.serviceWorker?.removeEventListener('message',message);navigator.serviceWorker?.removeEventListener('controllerchange',resume)};
 },[]);
 return next?<div className="app-update-notice" role="status"><span>{problem?'새 버전을 불러오지 못했습니다. 앱을 다시 열어주세요.':'새 버전 준비됨 · 입력을 마치면 자동 업데이트'}</span>{!problem&&<button onClick={()=>void apply.current(true)}>지금 업데이트</button>}</div>:null;
}
