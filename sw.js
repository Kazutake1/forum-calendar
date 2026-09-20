const CACHE='forum-calendar-v9-3-5';
const MANUAL_DATA='./manual_events.json';
const STATIC=['./','./index.html','./manifest.json','./icon-180.png','./icon-192.png','./icon-512.png','./manual-events.js',MANUAL_DATA];
const DATA_PATHS=['/events.json','/update-meta.json','/manual_events.json'];
self.addEventListener('install',e=>{self.skipWaiting();e.waitUntil(caches.open(CACHE).then(c=>c.addAll(STATIC)))});
self.addEventListener('activate',e=>{e.waitUntil(Promise.all([self.clients.claim(),caches.keys().then(keys=>Promise.all(keys.filter(k=>k.startsWith('forum-calendar-')&&k!==CACHE).map(k=>caches.delete(k))))]))});
self.addEventListener('fetch',e=>{
  const req=e.request;if(req.method!=='GET')return;
  const url=new URL(req.url);if(url.origin!==self.location.origin)return;
  const isManual=url.pathname.endsWith('/manual_events.json');
  if(isManual){
    e.respondWith((async()=>{
      try{
        const response=await fetch(req,{cache:'no-store'});
        if(response.ok){
          // Use the canonical path as the cache key; the request has a timestamp query.
          await (await caches.open(CACHE)).put(MANUAL_DATA,response.clone());
        }
        return response;
      }catch(error){
        const cached=await (await caches.open(CACHE)).match(MANUAL_DATA);
        if(!cached)throw error;
        const headers=new Headers(cached.headers);
        headers.set('X-Forum-Manual-Cache','stale');
        return new Response(await cached.arrayBuffer(),{
          status:cached.status,statusText:cached.statusText,headers
        });
      }
    })());
    return;
  }
  const isData=DATA_PATHS.some(p=>url.pathname.endsWith(p));
  if(isData){e.respondWith(fetch(req,{cache:'no-store'}));return;}
  e.respondWith(fetch(req,{cache:'no-store'}).then(r=>{if(r&&r.ok){const c=r.clone();caches.open(CACHE).then(x=>x.put(req,c))}return r}).catch(()=>caches.match(req).then(r=>r||caches.match('./index.html'))));
});
