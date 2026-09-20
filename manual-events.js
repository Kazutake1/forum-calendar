/* Manual events overlay. Never writes to or replaces events.json. */
(() => {
  'use strict';
  const normalizeTitle = value => String(value || '').normalize('NFKC').toLowerCase()
    .replace(/[\s\u3000「」『』【】（）()・.,。,:：!?！？"'“”‘’]/g, '');
  const validDate = value => {
    if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
    const d = new Date(`${value}T00:00:00Z`);
    return !Number.isNaN(d.getTime()) && d.toISOString().slice(0, 10) === value;
  };
  const sourceUrl = event => {
    try {
      const u = new URL(event.source_url || event.official_url || '');
      return u.protocol === 'https:' ? u.href : '';
    } catch (_) { return ''; }
  };
  const verifiedCity = event => {
    const url=sourceUrl(event);
    return event.source_type==='city_official' && event.source_verified===true &&
      Boolean(url) && new URL(url).hostname==='www.city.inazawa.aichi.jp';
  };
  const fieldEvidence = (e,field) => {
    const stored=e.field_sources && e.field_sources[field];
    if (stored && typeof stored==='object') return stored;
    const allowed=e.verified_fields;
    return {source_type:e[`${field}_source_type`]||e.source_type||e.source||'other',
      source_url:e[`${field}_source_url`]||e.source_url||e.official_url||'',
      verified:(e[`${field}_source_verified`]??e.source_verified)===true &&
        (!Array.isArray(allowed)||allowed.includes(field)),
      event_specific:(e[`${field}_event_specific`]??e.event_specific)===true};
  };
  const sourceRank = (e,field) => {
    const info=fieldEvidence(e,field);
    if(info.verified!==true)return 0;
    let url;
    try{url=new URL(info.source_url);if(url.protocol!=='https:')return 0;}catch(_){return 0;}
    const kind=info.source_type;
    if(['event_official','organizer','promoter'].includes(kind)&&info.event_specific===true&&
       !['x.com','www.x.com','twitter.com','www.twitter.com'].includes(url.hostname))return 3;
    if(url.hostname==='www.city.inazawa.aichi.jp'&&
       ['city_schedule','city_official','event_guide','city_event_calendar','schedule_ocr'].includes(kind))return 2;
    if(kind==='x'&&['x.com','www.x.com','twitter.com','www.twitter.com'].includes(url.hostname))return 1;
    return 0;
  };
  const venues = event => Array.isArray(event.venues) && event.venues.length
    ? event.venues : [event.hall].filter(Boolean);
  const timeParts = value => {
    const text=String(value||'').normalize('NFKC');
    const collect=pattern=>[...text.matchAll(pattern)].map(m=>[Number(m[1]),Number(m[2])])
      .filter(([h,m])=>h<24&&m<60)
      .map(([h,m])=>`${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}`);
    let starts=collect(/(?:開演|開始)\s*(\d{1,2}):(\d{2})/g);
    const doors=collect(/開場\s*(\d{1,2}):(\d{2})/g);
    if(!starts.length){const first=text.match(/^\s*(\d{1,2}):(\d{2})(?!\s*開場)/);
      if(first){starts=[`${first[1].padStart(2,'0')}:${first[2]}`];
        if(text.includes('/'))starts=collect(/(\d{1,2}):(\d{2})/g);}}
    return {starts:[...new Set(starts)],doors:[...new Set(doors)]};
  };
  const sameShowtime=(a,b)=>{
    if(a.performance_id&&b.performance_id)return a.performance_id===b.performance_id;
    const x=timeParts(a.time),y=timeParts(b.time);
    if(x.starts.length===1&&y.starts.length===1)return x.starts[0]===y.starts[0];
    if(x.starts.length>1||y.starts.length>1)return Boolean(a.time&&a.time===b.time);
    if(x.doors.length===1&&y.doors.length===1&&!x.starts.length&&!y.starts.length)
      return x.doors[0]===y.doors[0];
    return false;
  };
  const sameIdentity=(existing,match,requireTime)=> existing.date===match.date &&
    normalizeTitle(existing.title)===normalizeTitle(match.title) &&
    (!match.hall||venues(existing).includes(match.hall)) &&
    (!requireTime||sameShowtime(existing,match));
  const validated = (raw, ids) => {
    if (!raw || typeof raw !== 'object' || Array.isArray(raw) ||
        !validDate(raw.date) || typeof raw.title !== 'string' ||
        raw.title.trim().length < 2 || typeof raw.hall !== 'string' ||
        !raw.hall.trim() || typeof raw.id !== 'string' || !raw.id.trim() ||
        ids.has(raw.id) || !['x', 'city_official', 'city_schedule', 'event_official', 'organizer', 'promoter', 'other'].includes(raw.source_type) ||
        (raw.distinct_performance !== undefined && typeof raw.distinct_performance !== 'boolean') ||
        !sourceUrl(raw)) throw new Error('手動イベントデータの形式が不正です');
    if (raw.source_type === 'x' && !['x.com', 'www.x.com', 'twitter.com', 'www.twitter.com'].includes(new URL(sourceUrl(raw)).hostname)) {
      throw new Error('X投稿の出典URLが不正です');
    }
    ids.add(raw.id);
    if(raw.match){
        let good=false;
        try{good=new URL(raw.match.evidence_url).protocol==='https:';}catch(_){}
        if(!validDate(raw.match.date)||typeof raw.match.title!=='string'||
           !raw.match.title.trim()||raw.match.confirmed!==true||!good||
           (raw.match.correct_fields!==undefined&&(!Array.isArray(raw.match.correct_fields)||
             raw.match.correct_fields.some(field=>!['date','title','hall','time','price','official_url'].includes(field)))))
          throw new Error('重複照合には確認済みの公演と根拠URLが必要です');
      }
      if(raw.distinct_performance){
        let good=false;
        try{good=new URL(raw.distinct_performance_evidence_url).protocol==='https:';}catch(_){}
        if(raw.match||typeof raw.performance_id!=='string'||!raw.performance_id.trim()||!good)
          throw new Error('別公演には固有IDと根拠URLが必要です');
      }
    if (raw.source_type === 'city_official' && !verifiedCity(raw)) {
      throw new Error('市公式情報の出典が確認できません');
    }
    return { ...raw, venues: venues(raw),
      ...(verifiedCity(raw) ? { official_url: sourceUrl(raw) } : {}),
      _manualSourceUrl: sourceUrl(raw), _manualSourceType: raw.source_type };
  };
  function merge(auto,manual){
    if(!Array.isArray(auto)||!Array.isArray(manual))throw new Error('イベント配列が不正です');
    const result=auto.map(e=>({...e})); const ids=new Set();
    for(const raw of manual){
      const incoming=validated(raw,ids);
      const find=(target,withTime)=>result.map((e,i)=>sameIdentity(e,target,withTime)?i:-1).filter(i=>i>=0);
      let matches=incoming.distinct_performance?[]:find(incoming,true);
      if(incoming.match){matches=find(incoming.match,Boolean(incoming.match.time));
        if(matches.length!==1)throw new Error(`照合対象を一意に特定できません: ${incoming.title}`);}
      if(!matches.length&&find(incoming,false).length&&!incoming.distinct_performance)
        throw new Error(`同日同名の公演に食い違いがあります。確認してください: ${incoming.title}`);
      if(matches.length>1)throw new Error(`重複候補が複数あります: ${incoming.title}`);
      if(!matches.length){result.push(incoming);continue;}
      const current=result[matches[0]], combined={...current,field_sources:{...(current.field_sources||{})}};
      const corrected=Array.isArray(incoming.match?.correct_fields)?incoming.match.correct_fields:[];
      for(const field of ['date','title','hall','time','price','official_url']){
        const value=incoming[field];if(value===undefined||value===null||value==='')continue;
        const a=sourceRank(current,field),b=sourceRank(incoming,field);
        if(!current[field]||(b>a&&!(a===0&&b===1))||(incoming.match&&corrected.includes(field)&&b>=a&&!(a===0&&b===1))){
          combined[field]=value;combined.field_sources[field]=fieldEvidence(incoming,field);
          if(field==='hall')combined.venues=venues(incoming);
        }else if(current[field]===value&&b>a)combined.field_sources[field]=fieldEvidence(incoming,field);
        else if(current[field]!==value&&a===b&&a>0&&!corrected.includes(field))
          throw new Error(`同順位の出典が食い違います。確認してください: ${field}`);
      }
      const t1=timeParts(current.time),t2=timeParts(incoming.time);
      if(t1.starts.length===1&&t2.starts.length===1&&t1.starts[0]===t2.starts[0]&&
         (t1.doors.length||t2.doors.length)){
        const door=t1.doors[0]||t2.doors[0];
        if(t1.doors.length&&t2.doors.length&&t1.doors[0]!==t2.doors[0])
          throw new Error('開場時間が食い違います。確認してください');
        combined.time=`開場${door}／開演${t1.starts[0]}`;
        combined.opening_time_sources=[current,incoming].filter(e=>timeParts(e.time).doors.length).map(e=>fieldEvidence(e,'time'));
      }
      result[matches[0]]=combined;
    }
    return result;
  }
  window.mergeForumEvents = merge;
  const previousLinkInfo = linkInfo;
  linkInfo = function(event) {
    if (event._manualSourceUrl && event._manualSourceType !== 'city_official') {
      return { url: event._manualSourceUrl,
        label: event._manualSourceType === 'x' ? '出典のX投稿' : 'イベントの出典' };
    }
    return previousLinkInfo(event);
  };
  window.loadManualForumEvents = async () => {
    const status = document.querySelector('#autoUpdated');
    try {
      const response = await fetch('./manual_events.json?ts=' + Date.now(), { cache: 'no-store' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const manual = await response.json();
      EVENTS = merge(EVENTS, manual);
      refresh();
    } catch (error) {
      console.error('手動イベントの取得・統合に失敗しました', error);
      if (status) {
        status.classList.add('stale');
        status.textContent += ' ・ 手動登録データの取得・統合に失敗';
      }
    }
  };
})();
