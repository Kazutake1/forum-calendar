#!/usr/bin/env python3
from pathlib import Path

path = Path("index.html")
text = path.read_text(encoding="utf-8")

old = r'''async function loadAutoData(){
  try{
    const [er,mr]=await Promise.all([
      fetch('./events.json?ts='+Date.now(),{cache:'no-store'}),
      fetch('./update-meta.json?ts='+Date.now(),{cache:'no-store'})
    ]);
    if(er.ok){
      const data=await er.json();
      if(Array.isArray(data)&&data.length){
        EVENTS=data;
      }
    }
    if(mr.ok){
      const meta=await mr.json();
      const el=document.querySelector('#autoUpdated');
      if(el){
        const when=meta.updated_at_jst||meta.updated_at||'';
        const count=meta.event_count||EVENTS.length;
        if(meta.resolved_urls){
          if(meta.resolved_urls.events)URLS.events=meta.resolved_urls.events;
          if(meta.resolved_urls.schedule)URLS.schedule=meta.resolved_urls.schedule;
          const oe=document.querySelector('#officialEventsLink');
          const os=document.querySelector('#officialScheduleLink');
          if(oe)oe.href=URLS.events;
          if(os)os.href=URLS.schedule;
        }
        const note=meta.status==='ok'?'自動更新':'前回データを使用';
        let stale=false;
        const successAt=meta.last_successful_forum_at||meta.last_successful_source_at||meta.updated_at||'';
        if(successAt){
          const t=Date.parse(successAt);
          stale=!Number.isNaN(t)&&(Date.now()-t)>48*60*60*1000;
        }
        el.classList.toggle('stale',stale);
        el.textContent=stale?`⚠ 文化フォーラム公式情報の正常取得が48時間以上ありません ・ ${when} ・ ${count}件`:`${note}：${when} ・ ${count}件`;
      }
    }
  }catch(err){
    const el=document.querySelector('#autoUpdated');
    if(el)el.textContent='自動更新データを取得できないため保存済みデータを表示';
  }
  renderCalendar();renderList();
  const now=new Date();
  view=new Date(now.getFullYear(),now.getMonth(),1);
  showDate(key(now.getFullYear(),now.getMonth(),now.getDate()));
}
'''

new = r'''async function loadAutoData(){
  const el=document.querySelector('#autoUpdated');
  const [eventsResult,metaResult]=await Promise.allSettled([
    fetch('./events.json?ts='+Date.now(),{cache:'no-store'}).then(async r=>{
      if(!r.ok)throw new Error(`events.json: HTTP ${r.status}`);
      return r.json();
    }),
    fetch('./update-meta.json?ts='+Date.now(),{cache:'no-store'}).then(async r=>{
      if(!r.ok)throw new Error(`update-meta.json: HTTP ${r.status}`);
      return r.json();
    })
  ]);

  let eventsLoaded=false;
  if(eventsResult.status==='fulfilled'&&Array.isArray(eventsResult.value)&&eventsResult.value.length){
    EVENTS=eventsResult.value;
    eventsLoaded=true;
  }

  let metaLoaded=false;
  if(metaResult.status==='fulfilled'&&metaResult.value&&typeof metaResult.value==='object'){
    const meta=metaResult.value;
    metaLoaded=true;
    if(el){
      const when=meta.updated_at_jst||meta.updated_at||'';
      const count=eventsLoaded?(meta.event_count||EVENTS.length):EVENTS.length;
      if(meta.resolved_urls){
        if(meta.resolved_urls.events)URLS.events=meta.resolved_urls.events;
        if(meta.resolved_urls.schedule)URLS.schedule=meta.resolved_urls.schedule;
        const oe=document.querySelector('#officialEventsLink');
        const os=document.querySelector('#officialScheduleLink');
        if(oe)oe.href=URLS.events;
        if(os)os.href=URLS.schedule;
      }
      const note=meta.status==='ok'?'自動更新':'前回データを使用';
      let stale=false;
      const successAt=meta.last_successful_forum_at||meta.last_successful_source_at||meta.updated_at||'';
      if(successAt){
        const t=Date.parse(successAt);
        stale=!Number.isNaN(t)&&(Date.now()-t)>48*60*60*1000;
      }
      const dataWarning=eventsLoaded?'':' ・ イベントデータ取得失敗（保存済みデータ）';
      el.classList.toggle('stale',stale||!eventsLoaded);
      el.textContent=(stale?`⚠ 文化フォーラム公式情報の正常取得が48時間以上ありません ・ ${when} ・ ${count}件`:`${note}：${when} ・ ${count}件`)+dataWarning;
    }
  }

  if(el&&!metaLoaded){
    el.classList.toggle('stale',!eventsLoaded);
    el.textContent=eventsLoaded
      ?`イベントデータを表示中（更新情報を取得できません） ・ ${EVENTS.length}件`
      :'自動更新データを取得できないため保存済みデータを表示';
  }

  renderCalendar();renderList();
  const now=new Date();
  view=new Date(now.getFullYear(),now.getMonth(),1);
  showDate(key(now.getFullYear(),now.getMonth(),now.getDate()));
}
'''

count = text.count(old)
if count != 1:
    raise SystemExit(f"Expected one loadAutoData block, found {count}")
text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")
print("Patched loadAutoData for independent events/meta failure handling.")
