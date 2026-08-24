const CACHE='forum-calendar-v8';
const STATIC=['./','./index.html','./manifest.json','./icon-180.png','./icon-192.png','./icon-512.png'];
const DATA_PATHS=['/events.json','/update-meta.json'];
self.addEventListener('install',e=>{
  self.skipWaiting();
  e.waitUntil(caches.open(CACHE).then(c=>c.addAll(STATIC)));
});
self.addEventListener('activate',e=>{
  e.waitUntil(Promise.all([
    self.clients.claim(),
    caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k))))
  ]));
});
self.addEventListener('fetch',e=>{
  const req=e.request;
  if(req.method!=='GET') return;
  const url=new URL(req.url);
  if(url.origin!==self.location.origin) return;
  const isData=DATA_PATHS.some(p=>url.pathname.endsWith(p));
  if(isData){
    e.respondWith(fetch(req,{cache:'no-store'}).catch(()=>caches.match(url.pathname.endsWith('/events.json')?'./events.json':'./update-meta.json')));
    return;
  }
  if(url.search){
    e.respondWith(fetch(req));
    return;
  }
  e.respondWith(fetch(req).then(r=>{
    if(r && r.ok){
      const copy=r.clone();
      caches.open(CACHE).then(c=>c.put(req,copy));
    }
    return r;
  }).catch(()=>caches.match(req).then(r=>r||caches.match('./index.html'))));
});
