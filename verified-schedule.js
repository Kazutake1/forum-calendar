/* Visually checked schedule overlay. Keeps automated and manual JSON untouched. */
(() => {
  'use strict';
  const pdf = 'https://www.city.inazawa.aichi.jp/ica/cmsfiles/contents/0000004/4875/2026.10-11.pdf';
  const sha = 'c67f4dbc16e38becd24dfee2cd651b3d6ff871f577506b00b35075f9d46825d8';
  // Each mapping is an individually reviewed identity, not a fuzzy title match.
  const auto = {
    'schedule-10-02': 'セントラル愛知交響楽団 第16回名曲コンサート “The Musical”',
    'schedule-10-22': 'ピアノ体験会 ～スタインウェイがつなぐ街の劇場～',
    'schedule-10-26': 'M&Oplaysプロデュース 舞台「ブランク」',
    'schedule-11-01': 'KAZUYOSHI SAITO LIVE TOUR 2026 “日常 Days”',
    'schedule-11-04': 'Morning Classic Vol.3',
    'schedule-11-05': 'セントラル愛知交響楽団 公開リハーサル Part3',
    'schedule-11-16': '音楽家の集い Vol.113 峰岸桂子＆ルイス・サルトール「ラテンの魅力」'
  };
  const manual = {
    'schedule-10-07': 'manual-20261011-suyama-ballet-turandot',
    'schedule-11-14': 'manual-20261114-nagoya-bunri-70th-lecture',
    'schedule-11-20': 'manual-20261119-inazawa-women-charity'
  };
  const hasOwn = (obj, key) => Object.prototype.hasOwnProperty.call(obj, key);
  const normalizedTime = s => [...String(s || '').matchAll(/\d{1,2}:\d{2}/g)]
    .map(m => m[0].padStart(5, '0')).sort().join(',');

  function mergeVerifiedSchedule(existing, data) {
    if (!Array.isArray(existing) || !data || data.schema_version !== 1 ||
        data.source_pdf_sha256 !== sha || !Array.isArray(data.events) || data.events.length !== 58) {
      throw new Error('予定表の原本・件数を確認できません');
    }
    const ids = new Set(), keys = new Set();
    for (const e of data.events) {
      if (!e || typeof e.id !== 'string' || ids.has(e.id) ||
          !/^schedule-(10|11)-\d{2}$/.test(e.id) ||
          typeof e.date !== 'string' || !/^2026-(10|11)-\d{2}$/.test(e.date) ||
          !['大ホール','中ホール','小ホール'].includes(e.hall) ||
          typeof e.title !== 'string' || !e.title.trim() ||
          typeof e.time !== 'string' || !Array.isArray(e.venues) ||
          e.venues.length !== 1 || e.venues[0] !== e.hall ||
          e.source_type !== 'city_schedule' || e.source_confirmed !== true ||
          e.source_pdf_sha256 !== sha || e.source_url !== pdf ||
          typeof e.source_row !== 'string' || !e.source_row.startsWith('PDF page 1, ')) {
        throw new Error('予定表の行が検証済み形式と一致しません');
      }
      ids.add(e.id);
      const key = [e.date, e.hall, e.title].join('|');
      if (keys.has(key)) throw new Error('予定表に同一行が重複しています');
      keys.add(key);
    }
    const counts = data.events.reduce((n,e) => (n[e.date.slice(5,7)]++, n), {'10':0,'11':0});
    if (counts['10'] !== 28 || counts['11'] !== 30) throw new Error('予定表の月別件数が異なります');
    const withoutMapped = existing.slice();
    const schedule = data.events.map(raw => ({...raw}));
    for (const e of schedule) {
      const expected = hasOwn(manual, e.id) ? {id:manual[e.id]} :
        hasOwn(auto, e.id) ? {date:e.date, title:auto[e.id]} : null;
      if (!expected) continue;
      const matching = withoutMapped.map((x,i) => (expected.id
        ? x.id === expected.id : x.date === expected.date && x.title === expected.title && !x.id)
        ? i : -1).filter(i => i !== -1);
      if (matching.length !== 1) throw new Error(`既存催事の照合に失敗: ${e.id}`);
      const previous = withoutMapped[matching[0]];
      if (hasOwn(manual,e.id) && (previous.date !== e.date ||
          (e.id !== 'schedule-11-14' && previous.hall !== e.hall) ||
          (e.id === 'schedule-10-07' && !String(previous.time||'').includes('16:30')))) {
        throw new Error(`手動登録と別公演の可能性: ${e.id}`);
      }
      if (hasOwn(auto,e.id)) {
        if (previous.hall !== e.hall) throw new Error(`会場の照合に失敗: ${e.id}`);
        const a = normalizedTime(previous.time), b = normalizedTime(e.time);
        let cityProof = false;
        try { const url = new URL(previous.source_url || previous.official_url);
          cityProof = previous.source_verified === true && url.protocol === 'https:' &&
            url.hostname === 'www.city.inazawa.aichi.jp'; }
        catch (_) { /* Historical entries without a source cannot establish an official discrepancy. */ }
        if (cityProof && a && b && a !== b) {
          e.detail_review = {status:'要確認', note:`催事予定表の時間は${e.time}。市公式イベント案内は${previous.time}。`,
            conflicting_source_url:previous.official_url || previous.source_url || ''};
        }
      }
      withoutMapped.splice(matching[0], 1);
    }
    // The 10/11 ballet identity was checked against the organizer and Chacott;
    // its program, hall, date and showtime match the schedule. Never infer this
    // correspondence from a matching date/time for any other event.
    for (const other of withoutMapped) for (const e of schedule) {
      if (other.date !== e.date || other.hall !== e.hall) continue;
      const titleMatch = String(other.title||'').normalize('NFKC').replace(/\s/g,'') ===
        e.title.normalize('NFKC').replace(/\s/g,'');
      const starts = normalizedTime(other.time).split(',').filter(Boolean);
      const matchingTime = starts.some(t=>normalizedTime(e.time).split(',').includes(t));
      if (titleMatch || matchingTime) {
        throw new Error(`未照合の同一公演候補: ${e.id}`);
      }
    }
    return withoutMapped.concat(schedule);
  }
  window.mergeVerifiedForumSchedule = mergeVerifiedSchedule;
  window.loadVerifiedForumSchedule = async () => {
    const status = document.querySelector('#autoUpdated');
    try {
      const response = await fetch('./verified_schedule.json?ts=' + Date.now(), {cache:'no-store'});
      if (!response.ok) throw new Error('HTTP ' + response.status);
      const usingCache = response.headers && response.headers.get &&
        response.headers.get('X-Forum-Verified-Cache') === 'stale';
      const merged = mergeVerifiedSchedule(EVENTS, await response.json());
      const before = EVENTS;
      EVENTS = merged;
      try { refresh(); } catch (error) { EVENTS = before; throw error; }
      if (usingCache && status) {
        status.classList.add('stale');
        status.textContent += ' ・ 確認済み予定表：通信できないため保存済みデータを表示';
      }
    } catch (error) {
      console.error('原画像照合済み予定表の取り込みに失敗しました', error);
      if (status) {
        status.classList.add('stale');
        status.textContent += ' ・ 確認済み予定表の読込失敗';
      }
    }
  };
})();
