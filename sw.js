const CACHE='forum-calendar-v9-3-7-r3';
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
const uniqueNonEmptyStrings=values=>Array.isArray(values)&&values.length>0&&
  values.every(value=>typeof value==='string'&&Boolean(value.trim()))&&new Set(values).size===values.length;
const validHostName=value=>{
  if(typeof value!=='string'||!value||/[\\/:\s]/.test(value))return false;
  try{return new URL('https://'+value).hostname===value;}catch(_){return false;}
};
const validPolicyData=data=>{
  if(!data||typeof data!=='object'||Array.isArray(data)||data.schema_version!==1||
     !validHostName(data.city_host)||!uniqueNonEmptyStrings(data.x_hosts)||
     data.x_hosts.some(host=>!validHostName(host))||
     !uniqueNonEmptyStrings(data.merge_fields)||
     !uniqueNonEmptyStrings(data.manual_source_types)||
     !Array.isArray(data.source_groups)||data.source_groups.length!==3)return false;

  const expectedMergeFields=['date','title','hall','time','price','official_url'];
  if(data.merge_fields.length!==expectedMergeFields.length||
     data.merge_fields.some((field,index)=>field!==expectedMergeFields[index]))return false;

  const groups=new Map();
  const sourceTypes=new Set();
  for(const group of data.source_groups){
    if(!group||typeof group!=='object'||Array.isArray(group)||typeof group.name!=='string'||
       groups.has(group.name)||!Number.isInteger(group.rank)||!uniqueNonEmptyStrings(group.source_types)||
       (group.hosts!==undefined&&(!uniqueNonEmptyStrings(group.hosts)||group.hosts.some(host=>!validHostName(host))))||
       (group.forbidden_hosts!==undefined&&(!uniqueNonEmptyStrings(group.forbidden_hosts)||
         group.forbidden_hosts.some(host=>!validHostName(host)))))return false;
    for(const sourceType of group.source_types){
      if(sourceTypes.has(sourceType))return false;
      sourceTypes.add(sourceType);
    }
    groups.set(group.name,group);
  }

  const official=groups.get('event_specific_official');
  const city=groups.get('city_official');
  const x=groups.get('x');
  if(!official||official.rank!==3||official.require_event_specific!==true||
     !Array.isArray(official.forbidden_hosts)||!data.x_hosts.every(host=>official.forbidden_hosts.includes(host))||
     !['event_official','organizer','promoter'].every(type=>official.source_types.includes(type)))return false;
  if(!city||city.rank!==2||!Array.isArray(city.hosts)||!city.hosts.includes(data.city_host)||
     !['city_official','city_schedule','city_event_guide','event_guide','city_event_calendar']
       .every(type=>city.source_types.includes(type)))return false;
  if(!x||x.rank!==1||!Array.isArray(x.hosts)||!data.x_hosts.every(host=>x.hosts.includes(host))||
     !x.source_types.includes('x'))return false;

  const requiredManual=['x','city_official','city_schedule','city_event_guide','city_event_calendar',
    'event_official','organizer','promoter','other'];
  if(!requiredManual.every(type=>data.manual_source_types.includes(type)))return false;
  return data.manual_source_types.every(type=>type==='other'||sourceTypes.has(type));
};
const validManualData=(data,policy)=>{
  if(!validPolicyData(policy)||!Array.isArray(data))return false;
  const ids=new Set(),allowedTypes=new Set(policy.manual_source_types),xHosts=new Set(policy.x_hosts);
  const mergeFields=new Set(policy.merge_fields);
  const cityGroup=policy.source_groups.find(group=>group.name==='city_official');
  const cityTypes=new Set(cityGroup.source_types);
  return data.every(event=>{
    if(!event||typeof event!=='object'||Array.isArray(event)||typeof event.id!=='string'||!event.id.trim()||
       ids.has(event.id)||!validDate(event.date)||typeof event.title!=='string'||event.title.trim().length<2||
       typeof event.hall!=='string'||!event.hall.trim()||typeof event.source_type!=='string'||
       !allowedTypes.has(event.source_type)||!validHttpsUrl(event.source_url)||
       (event.source_verified!==undefined&&typeof event.source_verified!=='boolean')||
       (event.event_specific!==undefined&&typeof event.event_specific!=='boolean')||
       (event.distinct_performance!==undefined&&typeof event.distinct_performance!=='boolean')||
       (event.verified_fields!==undefined&&(!Array.isArray(event.verified_fields)||
         event.verified_fields.some(field=>!mergeFields.has(field)))))return false;
    const sourceHost=new URL(event.source_url).hostname;
    if(event.source_type==='x'&&!xHosts.has(sourceHost))return false;
    if(cityTypes.has(event.source_type)&&
       (event.source_verified!==true||sourceHost!==policy.city_host))return false;
    if(event.match){
      if(typeof event.match!=='object'||Array.isArray(event.match)||!validDate(event.match.date)||
         typeof event.match.title!=='string'||!event.match.title.trim()||event.match.confirmed!==true||
         !validHttpsUrl(event.match.evidence_url)||
         (event.match.correct_fields!==undefined&&(!Array.isArray(event.match.correct_fields)||
           event.match.correct_fields.some(field=>!mergeFields.has(field)))))return false;
    }
    if(event.distinct_performance&&
       (event.match||typeof event.performance_id!=='string'||!event.performance_id.trim()||
        !validHttpsUrl(event.distinct_performance_evidence_url)))return false;
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
  if(!(await validator(data)))throw new Error(label+'の内容検証に失敗しました');
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
        if(await validator(data))return new Response(body,{status:200,headers:jsonHeaders(staleHeader)});
      }
    }catch(cacheError){console.warn('保存済み'+label+'も読み込めません',cacheError);}
    throw error;
  }
};
const cachedValidatedPolicy=async()=>{
  try{
    const cached=await caches.match(POLICY_DATA);
    if(!cached||!cached.ok)return null;
    const policy=JSON.parse(await cached.text());
    return validPolicyData(policy)?policy:null;
  }catch(_){return null;}
};
const precacheValidatedData=async cache=>{
  const policyBody=await readValidatedBody(
    await fetch(POLICY_DATA,{cache:'no-store'}),validPolicyData,'イベント出典ポリシー');
  const policy=JSON.parse(policyBody);
  await cache.put(POLICY_DATA,new Response(policyBody,{status:200,headers:jsonHeaders()}));
  const targets=[
    [AUTO_DATA,validAutoData,'イベントデータ'],
    [MANUAL_DATA,data=>validManualData(data,policy),'手動イベントデータ'],
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
    e.respondWith((async()=>{
      const policy=await cachedValidatedPolicy();
      if(!policy)throw new Error('検証済みイベント出典ポリシーがありません');
      return fetchValidated(req,MANUAL_DATA,data=>validManualData(data,policy),
        'X-Forum-Manual-Cache','手動イベントデータ');
    })());
    return;
  }
  const isData=DATA_PATHS.some(p=>url.pathname.endsWith(p));
  if(isData){e.respondWith(fetch(req,{cache:'no-store'}));return;}
  e.respondWith(fetch(req,{cache:'no-store'}).then(r=>{if(r&&r.ok){const c=r.clone();caches.open(CACHE).then(x=>x.put(req,c))}return r}).catch(()=>caches.match(req,{ignoreSearch:true}).then(r=>r||caches.match('./index.html'))));
});
