const CACHE='forum-calendar-v9-3-7-r1';
const AUTO_DATA='./events.json';
const POLICY_DATA='./event-policy.json';
const MANUAL_DATA='./manual_events.json';
const VERIFIED_DATA='./verified_schedule.json';
const VERIFIED_SHA='c67f4dbc16e38becd24dfee2cd651b3d6ff871f577506b00b35075f9d46825d8';
const STATIC=['./','./index.html','./manifest.json','./icon-180.png','./icon-192.png','./icon-512.png','./manual-events.js','./verified-schedule.js'];
const PRECACHE_DATA=[AUTO_DATA,POLICY_DATA,MANUAL_DATA,VERIFIED_DATA];
const DATA_PATHS=['/update-meta.json'];

const validDate=value=>{
  if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(value))return false;
  const date=new Date(value+'T00:00:00Z');
  return !Number.isNaN(date.getTime())&&date.toISOString().slice(0,10)===value;
};
const validHttpsUrl=value=>{
  try{const url=new URL(String(value||''));return url.protocol==='https:'&&Boolean(url.hostname);}
  catch(_){return false;}
};
const validAutoData=data=>Array.isArray(data)&&data.length>0&&data.every(event=>
  event&&typeof event==='object'&&!Array.isArray(event)&&validDate(event.date)&&
  typeof event.title==='string'&&event.title.trim().length>=2&&
  typeof event.hall==='string'&&Boolean(event.hall.trim())&&
  (event.venues===undefined||(Array.isArray(event.venues)&&event.venues.every(v=>typeof v==='string'&&Boolean(v.trim()))))
);
const validPolicyData=data=>{
  if(!data||typeof data!=='object'||Array.isArray(data)||data.schema_version!==1||
     typeof data.city_host!=='string'||!data.city_host||
     !Array.isArray(data.x_hosts)||!data.x_hosts.length||
     !Array.isArray(data.merge_fields)||!data.merge_fields.length||
     !Array.isArray(data.manual_source_types)||!data.manual_source_types.length||
     !Array.isArray(data.source_groups)||!data.source_groups.length)return false;
  return data.source_groups.every(group=>group&&typeof group==='object'&&!Array.isArray(group)&&
    Number.isInteger(group.rank)&&Array.isArray(group.source_types)&&group.source_types.length>0);
};
const validManualData=data=>{
  if(!Array.isArray(data))return false;
  const ids=new Set();
  return data.every(event=>{
    if(!event||typeof event!=='object'||Array.isArray(event)||typeof event.id!=='string'||!event.id.trim()||
       ids.has(event.id)||!validDate(event.date)||typeof event.title!=='string'||event.title.trim().length<2||
       typeof event.hall!=='string'||!event.hall.trim()||typeof event.source_type!=='string'||!event.source_type.trim()||
       !validHttpsUrl(event.source_url))return false;
    ids.add(event.id);
    return true;
  });
};
const validVerifiedData=data=>{
  if(!data||typeof data!=='object'||Array.isArray(data)||data.schema_version!==1||
     data.source_pdf_sha256!==VERIFIED_SHA||!Array.isArray(data.events)||data.events.length!==58)return false;
  const ids=new Set();let october=0,november=0;
  for(const event of data.events){
    if(!event||typeof event!=='object'||Array.isArray(event)||typeof event.id!=='string'||ids.has(event.id)||
       !/^schedule-(10|11)-\d{2}$/.test(event.id)||!validDate(event.date)||!/^2026-(10|11)-\d{2}$/.test(event.date)||
       !['大ホール','中ホール','小ホール'].includes(event.hall)||typeof event.title!=='string'||!event.title.trim()||
       typeof event.time!=='string'||!Array.isArray(event.venues)||event.venues.length!==1||event.venues[0]!==event.hall||
       event.source_type!=='city_schedule'||event.source_confirmed!==true||
       event.source_pdf_sha256!==VERIFIED_SHA||!validHttpsUrl(event.source_url)||
       new URL(event.source_url).hostname!=='www.city.inazawa.aichi.jp'||
       typeof event.source_row!=='string'||!event.source_row.startsWith('PDF page 1, '))return false;
    ids.add(event.id);
    if(event.date.startsWith('2026-10'))october++;
    else if(event.date.startsWith('2026-11'))november++;
  }
  return october===28&&november===30;
};
const jsonHeaders=staleHeader=>({
  'Content-Type':'application/json; charset=utf-8',
  ...(staleHeader?{[staleHeader]:'stale'}:{})
});
const readValidatedBody=async(response,validator,label)=>{
  if(!response.ok||response.status!==200)throw new Error(label+'取得失敗: HTTP '+response.status);
  const body=await response.text();
  let data;
  try{data=JSON.parse(body);}catch(error){throw new Error(label+'のJSON解析に失敗しました');}
  if(!validator(data))throw new Error(label+'の内容検証に失敗しました');
  return body;
};
const putValidated=async(cacheKey,body)=>{
  await (await caches.open(CACHE)).put(cacheKey,new Response(body,{status:200,headers:jsonHeaders()}));
};
const fetchValidated=async(req,cacheKey,validator,staleHeader,label)=>{
  try{
    const body=await readValidatedBody(await fetch(req,{cache:'no-store'}),validator,label);
    try{await putValidated(cacheKey,body);}
    catch(cacheError){console.warn(label+'のキャッシュ保存を省略',cacheError);}
    return new Response(body,{status:200,headers:jsonHeaders()});
  }catch(error){
    try{
      const cached=await caches.match(cacheKey);
      if(cached&&cached.ok){
        const body=await cached.text();
        const data=JSON.parse(body);
        if(validator(data))return new Response(body,{status:200,headers:jsonHeaders(staleHeader)});
      }
    }catch(cacheError){console.warn('保存済み'+label+'も読み込めません',cacheError);}
    throw error;
  }
};
const precacheValidatedData=async cache=>{
  const targets=[
    [AUTO_DATA,validAutoData,'イベントデータ'],
    [POLICY_DATA,validPolicyData,'イベント出典ポリシー'],
    [MANUAL_DATA,validManualData,'手動イベントデータ'],
    [VERIFIED_DATA,validVerifiedData,'確認済み予定表']
  ];
  for(const [path,validator,label] of targets){
    const body=await readValidatedBody(await fetch(path,{cache:'no-store'}),validator,label);
    await cache.put(path,new Response(body,{status:200,headers:jsonHeaders()}));
  }
};

self.addEventListener('install',e=>{
  self.skipWaiting();
  e.waitUntil((async()=>{
    const cache=await caches.open(CACHE);
    await cache.addAll(STATIC);
    await precacheValidatedData(cache);
  })());
});
self.addEventListener('activate',e=>{e.waitUntil(Promise.all([self.clients.claim(),caches.keys().then(keys=>Promise.all(keys.filter(k=>k.startsWith('forum-calendar-')&&k!==CACHE).map(k=>caches.delete(k))))]))});
self.addEventListener('fetch',e=>{
  const req=e.request;if(req.method!=='GET')return;
  const url=new URL(req.url);if(url.origin!==self.location.origin)return;
  if(url.pathname.endsWith('/events.json')){
    e.respondWith(fetchValidated(req,AUTO_DATA,validAutoData,'X-Forum-Events-Cache','イベントデータ'));
    return;
  }
  if(url.pathname.endsWith('/event-policy.json')){
    e.respondWith(fetchValidated(req,POLICY_DATA,validPolicyData,'X-Forum-Policy-Cache','イベント出典ポリシー'));
    return;
  }
  if(url.pathname.endsWith('/verified_schedule.json')){
    e.respondWith(fetchValidated(req,VERIFIED_DATA,validVerifiedData,'X-Forum-Verified-Cache','確認済み予定表'));
    return;
  }
  if(url.pathname.endsWith('/manual_events.json')){
    e.respondWith(fetchValidated(req,MANUAL_DATA,validManualData,'X-Forum-Manual-Cache','手動イベントデータ'));
    return;
  }
  const isData=DATA_PATHS.some(p=>url.pathname.endsWith(p));
  if(isData){e.respondWith(fetch(req,{cache:'no-store'}));return;}
  e.respondWith(fetch(req,{cache:'no-store'}).then(r=>{if(r&&r.ok){const c=r.clone();caches.open(CACHE).then(x=>x.put(req,c))}return r}).catch(()=>caches.match(req,{ignoreSearch:true}).then(r=>r||caches.match('./index.html'))));
});
