// Do not persist private pages, conversations, credentials or API responses.
self.addEventListener('install',()=>self.skipWaiting());
self.addEventListener('activate',event=>event.waitUntil(self.clients.claim()));
self.addEventListener('fetch',event=>{if(event.request.mode==='navigate')event.respondWith(fetch(event.request).catch(()=>new Response('<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>모아 · 오프라인</title><body style="font-family:system-ui;padding:48px;background:#f8f9f5;color:#326653"><h1>잠시 연결이 끊겼어요.</h1><p>개인 일정은 기기에 저장하지 않습니다. 연결 후 다시 열어주세요.</p><a href="/">다시 시도</a></body></html>',{headers:{'Content-Type':'text/html; charset=utf-8'}})))});

self.addEventListener('notificationclick',event=>{event.notification.close();event.waitUntil(clients.matchAll({type:'window'}).then(windows=>windows.length?windows[0].focus():clients.openWindow('/')));});

// No personal titles or source contents on the lock screen.
self.addEventListener('push',event=>event.waitUntil(self.registration.showNotification('모아 · 일정 확인',{body:'일정 변경이나 다가오는 약속을 확인하세요.',tag:'moa-schedule-update'})));
