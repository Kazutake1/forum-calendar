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
    const url = sourceUrl(event);
    if (!url || new URL(url).hostname !== 'www.city.inazawa.aichi.jp') return false;
    if (event.source_type === 'city_official') return event.source_verified === true;
    return ['event_guide', 'city_event_calendar', 'schedule_ocr'].includes(event.source);
  };
  const venues = event => Array.isArray(event.venues) && event.venues.length
    ? event.venues : [event.hall].filter(Boolean);
  const sameIdentity = (existing, match, requireTime) => existing.date === match.date &&
    normalizeTitle(existing.title) === normalizeTitle(match.title) &&
    (!match.hall || venues(existing).includes(match.hall)) &&
    (!requireTime || !match.time || !existing.time || existing.time === match.time);
  const validated = (raw, ids) => {
    if (!raw || typeof raw !== 'object' || Array.isArray(raw) ||
        !validDate(raw.date) || typeof raw.title !== 'string' ||
        raw.title.trim().length < 2 || typeof raw.hall !== 'string' ||
        !raw.hall.trim() || typeof raw.id !== 'string' || !raw.id.trim() ||
        ids.has(raw.id) || !['x', 'city_official', 'other'].includes(raw.source_type) ||
        (raw.distinct_performance !== undefined && typeof raw.distinct_performance !== 'boolean') ||
        !sourceUrl(raw)) throw new Error('手動イベントデータの形式が不正です');
    if (raw.source_type === 'x' && !['x.com', 'www.x.com', 'twitter.com', 'www.twitter.com'].includes(new URL(sourceUrl(raw)).hostname)) {
      throw new Error('X投稿の出典URLが不正です');
    }
    ids.add(raw.id);
    if (raw.match && (!validDate(raw.match.date) ||
        typeof raw.match.title !== 'string' || !raw.match.title.trim())) {
      throw new Error('重複照合情報の形式が不正です');
    }
    if (raw.source_type === 'city_official' && !verifiedCity(raw)) {
      throw new Error('市公式情報の出典が確認できません');
    }
    return { ...raw, venues: venues(raw),
      ...(verifiedCity(raw) ? { official_url: sourceUrl(raw) } : {}),
      _manualSourceUrl: sourceUrl(raw), _manualSourceType: raw.source_type };
  };
  function merge(auto, manual) {
    if (!Array.isArray(auto) || !Array.isArray(manual)) throw new Error('イベント配列が不正です');
    const result = auto.map(e => ({ ...e }));
    const ids = new Set();
    for (const raw of manual) {
      const incoming = validated(raw, ids);
      const find = (target, requireTime) => result.map((e, index) => sameIdentity(e, target, requireTime) ? index : -1)
        .filter(index => index >= 0);
      let matches = find(incoming, true);
      if (!matches.length && incoming.match) {
        matches = find(incoming.match, Boolean(incoming.match.time));
        if (!matches.length) throw new Error(`指定された既存イベントが見つかりません: ${incoming.title}`);
      }
      if (!matches.length && find(incoming, false).length && !incoming.distinct_performance) {
        throw new Error(`同名・同日・同会場の時間差を確認してください: ${incoming.title}`);
      }
      if (matches.length > 1) throw new Error(`重複候補が複数あります: ${incoming.title}`);
      if (!matches.length) { result.push(incoming); continue; }
      const i = matches[0], current = result[i];
      // Verified city pages outrank all other sources. When neither side is
      // city-verified, retain existing automatic data and fill blanks only.
      const incomingWins = verifiedCity(incoming) && !verifiedCity(current);
      const primary = incomingWins ? incoming : current;
      const secondary = incomingWins ? current : incoming;
      const combined = { ...primary };
      for (const field of ['time', 'price', 'hall', 'official_url']) {
        if (!combined[field] && secondary[field]) combined[field] = secondary[field];
      }
      if (!venues(combined).length && venues(secondary).length) {
        combined.venues = venues(secondary);
      }
      result[i] = combined;
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
