const CACHE='forum-calendar-v9-3-6';
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
    try {
      const response=await fetch(req,{cache:'no-store'});
      if(!response.ok||response.status!==200)return response;
      // Read the body once before returning it; do not race two cloned streams.
      const body=await response.text();
      if(!Array.isArray(JSON.parse(body)))throw new Error('手動イベントJSONは配列である必要があります');
      const headers={'Content-Type':'application/json; charset=utf-8'};
      try {
        await (await caches.open(CACHE)).put(MANUAL_DATA,new Response(body,{status:200,headers}));
      } catch(cacheError) { console.warn('手動データのキャッシュ保存を省略',cacheError); }
      return new Response(body,{status:200,headers});
    } catch(error) {
      // Includes failures after fetch resolves but its response body is interrupted.
      try {
        const cached=await caches.match(MANUAL_DATA);
        if(cached&&cached.ok){
          const body=await cached.text();
          if(Array.isArray(JSON.parse(body)))return new Response(body,{status:200,headers:{
            'Content-Type':'application/json; charset=utf-8',
            'X-Forum-Manual-Cache':'stale'
          }});
        }
      } catch(cacheError) { console.warn('保存済み手動データも読み込めません',cacheError); }
      throw error;
    }
  })());
  return;
}
  const isData=DATA_PATHS.some(p=>url.pathname.endsWith(p));
  if(isData){e.respondWith(fetch(req,{cache:'no-store'}));return;}
  e.respondWith(fetch(req,{cache:'no-store'}).then(r=>{if(r&&r.ok){const c=r.clone();caches.open(CACHE).then(x=>x.put(req,c))}return r}).catch(()=>caches.match(req,{ignoreSearch:true}).then(r=>r||caches.match('./index.html'))));
});
