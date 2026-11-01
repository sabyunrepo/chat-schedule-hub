// Generated public/sw.js changes with every source revision. No private data caching.
const VERSION='__MOA_BUILD_ID__';
const acknowledgements=new Set();
self.addEventListener('install',event=>event.waitUntil(self.skipWaiting()));
self.addEventListener('message',event=>{
 if(event.data?.type==='MOA_UPDATE_ACK'&&event.data.version===VERSION&&event.source?.id)acknowledgements.add(event.source.id);
});
self.addEventListener('activate',event=>event.waitUntil((async()=>{
 const keys=await caches.keys();await Promise.all(keys.filter(k=>/^moa[-:]/.test(k)).map(k=>caches.delete(k)));
 await self.clients.claim();
 const windows=await self.clients.matchAll({type:'window',includeUncontrolled:true});
 for(const client of windows)client.postMessage({type:'MOA_UPDATE_READY',version:VERSION});
 // Legacy pages have no update listener. Migrate them once; modern pages own draft/busy handling.
 await new Promise(resolve=>setTimeout(resolve,2000));
 await Promise.all(windows.map(async client=>{
  if(acknowledgements.has(client.id))return;
  const url=new URL(client.url);if(url.origin!==self.location.origin||url.pathname!=='/'||url.searchParams.get('__moa_v')===VERSION)return;
  url.searchParams.set('__moa_v',VERSION);try{await client.navigate(url.href);}catch{}
 }));
 acknowledgements.clear();
})()));
self.addEventListener('fetch',event=>{
 if(event.request.mode!=='navigate')return;
 event.respondWith(fetch(event.request,{cache:'no-store'}).catch(()=>new Response('<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>모아 · 오프라인</title><body style="font-family:system-ui;padding:48px"><h1>연결을 확인해주세요</h1><p>인터넷 연결 후 최신 버전을 불러옵니다.</p><a href="/">다시 시도</a></body></html>',{headers:{'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store'}})));
});
self.addEventListener('notificationclick',event=>{event.notification.close();event.waitUntil(self.clients.matchAll({type:'window'}).then(windows=>windows.length?windows[0].focus():self.clients.openWindow('/')));});
self.addEventListener('push',event=>event.waitUntil(self.registration.showNotification('모아 · 일정 확인',{body:'일정 변경이나 다가오는 약속을 확인하세요.',tag:'moa-schedule-update'})));
