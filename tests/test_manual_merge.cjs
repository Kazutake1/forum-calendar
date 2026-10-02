const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const policy = JSON.parse(fs.readFileSync('event-policy.json','utf8'));
const context = vm.createContext({
  window: {FORUM_EVENT_POLICY: policy}, URL,
  linkInfo: () => ({ url: '#', label: 'test' }),
  console,
});
vm.runInContext(fs.readFileSync('manual-events.js', 'utf8'), context);
const merge = context.window.mergeForumEvents;
assert.equal(typeof merge, 'function');

const base = (time, extras = {}) => ({
  date: '2026-10-31', title: '演奏会', hall: '中ホール',
  time, price: '500円', ...extras,
});
const manual = (id, time, extras = {}) => ({
  id, date: '2026-10-31', title: '演奏会', hall: '中ホール', time,
  source_type: 'x', source_url: 'https://x.com/example/status/123',
  ...extras,
});

// Doors and start are different attributes of the same performance.
let result = merge([base('開演18:00')], [manual('doors-and-start', '開場17:30／開演18:00')]);
assert.equal(result.length, 1);
assert.equal(result[0].time, '開場17:30／開演18:00');

// The first and second independent performances must remain separate.
result = merge([base('開演10:00')], [manual('second', '開演18:00', {
  distinct_performance: true, performance_id: 'show-2',
  distinct_performance_evidence_url: 'https://x.com/example/status/123',
})]);
assert.equal(result.length, 2);
assert.equal(result[0].time, '開演10:00');
assert.equal(result[1].time, '開演18:00');

// One unknown time does not prove that two notices describe the same show.
assert.throws(() => merge([base('')], [manual('unknown', '開演18:00')]), /確認|重複|時間/);
assert.throws(() => merge([base('開場17:30')], [manual('opening-only', '開演18:00')]), /確認|重複|時間/);

// A reviewed correction may target one named performance without merging other shows.
result = merge([base('開演10:00'), base('開演18:00')], [manual('correction', '開演18:30', {
  source_type: 'city_official', source_verified: true,
  source_url: 'https://www.city.inazawa.aichi.jp/0000123456.html',
  match: {
    date: '2026-10-31', title: '演奏会', hall: '中ホール', time: '開演18:00',
    confirmed: true, evidence_url: 'https://www.city.inazawa.aichi.jp/0000123456.html',
    correct_fields: ['time'],
  },
})]);
assert.equal(result.length, 2);
assert.equal(result[0].time, '開演10:00');
assert.equal(result[1].time, '開演18:30');

// A field sourced from X does not become city-verified due to another city field.
result = merge([base('開演18:00', { price: '500円' })], [manual('field-evidence', '開演18:00', {
  source_type: 'city_official', source_verified: true,
  source_url: 'https://www.city.inazawa.aichi.jp/0000123456.html',
  price: '2,000円', price_source_type: 'x',
  price_source_url: 'https://x.com/example/status/123',
})]);
assert.equal(result[0].price, '500円');
assert.throws(() => merge([base('開演18:00')], [manual('not-reviewed', '開演19:00', {
  match: {date:'2026-10-31', title:'演奏会', time:'開演18:00'},
})]), /根拠|確認|照合/);

// Verified field priority: event official > city schedule > X, regardless of insertion order.
const proof=(id,time,source_type,source_url,rank)=>manual(id,time,{source_type,source_url,source_verified:true,event_specific:rank===3,verified_fields:['time']});
const x=proof('x','開演18:00','x','https://x.com/example/status/123',1);
const city=proof('city','開演18:00','city_schedule','https://www.city.inazawa.aichi.jp/ica/0000002507.html',2);
const official=proof('official','開演18:00','event_official','https://example.org/event/123',3);
const withRank=(value,e)=>({...e,price:'',time_source_verified:true,time:value});
result=merge([withRank('開演18:00',x)], [withRank('開演18:00',city)]);
assert.equal(result[0].field_sources.time.source_type,'city_schedule');
result=merge([result[0]], [withRank('開演18:00',official)]);
assert.equal(result[0].field_sources.time.source_type,'event_official');

result=merge([base('開演18:00',{price:'500円'})], [manual('x-price','開演18:00',{price:'2000円',source_verified:true,verified_fields:['price']})]);
assert.equal(result[0].price,'500円');

// All manual city source types require verified Inazawa-city evidence.
const cityManualTypes=['city_official','city_schedule','city_event_guide','city_event_calendar'];
for(const sourceType of cityManualTypes){
  const cityUrl='https://www.city.inazawa.aichi.jp/ica/0000002507.html';
  result=merge([], [manual('valid-'+sourceType,'開演18:00',{
    source_type:sourceType,source_url:cityUrl,source_verified:true,
  })]);
  assert.equal(result.length,1,sourceType+' should accept verified city evidence');
  assert.equal(result[0].official_url,cityUrl);
  assert.throws(()=>merge([], [manual('wrong-host-'+sourceType,'開演18:00',{
    source_type:sourceType,source_url:'https://example.org/not-city',source_verified:true,
  })]), /市公式情報/);
  assert.throws(()=>merge([], [manual('unverified-'+sourceType,'開演18:00',{
    source_type:sourceType,source_url:cityUrl,source_verified:false,
  })]), /市公式情報/);
}
assert.throws(()=>merge([], [manual('legacy-event-guide','開演18:00',{
  source_type:'event_guide',source_url:'https://www.city.inazawa.aichi.jp/ica/0000002507.html',
  source_verified:true,
})]), /形式/);

// City event guide and the verified city schedule are distinct source types but the same rank.
assert.throws(() => merge([
  base('開演18:00',{price:'市公式イベント案内価格',source_type:'city_event_guide',
    source_url:'https://www.city.inazawa.aichi.jp/ica/0000002507.html',
    source_verified:true,verified_fields:['price']})
], [manual('schedule-price','開演18:00',{price:'催事予定表価格',source_type:'city_schedule',
  source_url:'https://www.city.inazawa.aichi.jp/ica/0000004875.html',
  source_verified:true,verified_fields:['price']})]), /同順位の出典/);

const indexHtml = fs.readFileSync('index.html','utf8');
assert.ok(indexHtml.includes("e.source_type==='city_event_guide'&&e.source_url"));
assert.ok(indexHtml.includes("label:'会館公式イベント案内'"));

// Equal-tier reports with the same start are compatible even when only one gives door time.
result=merge([base('開演18:00',{source_type:'city_schedule',source_url:'https://www.city.inazawa.aichi.jp/ica/0000002507.html',source_verified:true,verified_fields:['time']})],
 [manual('opening-city','開場17:30／開演18:00',{source_type:'city_schedule',source_url:'https://www.city.inazawa.aichi.jp/ica/0000002507.html',source_verified:true,verified_fields:['time']})]);
assert.equal(result.length,1);
assert.equal(result[0].time,'開場17:30／開演18:00');

// Shared contract fixtures are also executed by Python's dedupe implementation.
const contractCases = JSON.parse(fs.readFileSync('tests/event_merge_contract.json','utf8'));
for (const testCase of contractCases) {
  const contractResult = merge(testCase.base, testCase.manual);
  assert.equal(contractResult.length, testCase.expected.count, testCase.name);
  assert.deepEqual(Array.from(contractResult, e => e.time || ''), testCase.expected.times, testCase.name);
  if (Object.hasOwn(testCase.expected, 'price')) {
    assert.equal(contractResult[0].price, testCase.expected.price, testCase.name);
  }
}

// Production regression: validate every currently published manual record against
// the actual automatic dataset, not only synthetic events. Never write data files.
const publishedAuto = JSON.parse(fs.readFileSync('events.json', 'utf8'));
const publishedManual = JSON.parse(fs.readFileSync('manual_events.json', 'utf8'));
const publishedMerged = merge(publishedAuto, publishedManual);
assert.ok(Array.isArray(publishedMerged));
for (const event of publishedManual) {
  assert.ok(publishedMerged.some(e => e.date === event.date && e.title === event.title &&
    (e.venues || [e.hall]).includes(event.hall)), `Missing manual event: ${event.id}`);
}
console.log(`Manual overlay validated against ${publishedAuto.length} automatic and ${publishedManual.length} real manual records.`);
console.log('Manual identity/provenance regression tests passed.');

// Exercise the actual loader using the published data in a browser-like context.
async function testManualRecovery() {
  const response = { ok: true, headers: { get: () => null }, json: async () => publishedManual };
  const makePage = (fetcher, cached) => {
    const status = { textContent: '自動更新済み', classList: { add() {} } };
    let refreshed = 0;
    const page = { window: { FORUM_EVENT_POLICY: policy, caches: { match: async () => cached } }, URL, console,
      EVENTS: publishedAuto.slice(), refresh: () => { refreshed++; },
      linkInfo: () => ({ url: '#', label: 'test' }),
      document: { querySelector: () => status }, fetch: fetcher };
    vm.runInContext(fs.readFileSync('manual-events.js', 'utf8'), vm.createContext(page));
    return { page, status, getRefreshed: () => refreshed };
  };
  const good = makePage(async () => response, null);
  await good.page.window.loadManualForumEvents();
  assert.equal(good.page.EVENTS.length, publishedMerged.length);
  assert.equal(good.getRefreshed(), 1);
  assert.ok(!good.status.textContent.includes('失敗'));

  const offline = makePage(async () => { throw Error('offline'); }, response);
  await offline.page.window.loadManualForumEvents();
  assert.equal(offline.page.EVENTS.length, publishedMerged.length);
  assert.equal(offline.getRefreshed(), 1);
  assert.ok(offline.status.textContent.includes('保存済みデータを表示'));

  const failure = makePage(async () => { throw Error('network unavailable'); }, null);
  await failure.page.window.loadManualForumEvents();
  assert.equal(failure.page.EVENTS.length, publishedAuto.length);
  assert.equal(failure.getRefreshed(), 0);
  assert.ok(failure.status.textContent.includes('取得失敗'));
  assert.ok(failure.status.textContent.includes('network unavailable'));
  // iOS WebKit can report "Load failed" after fetch resolves, during response.json().
  let attempts = 0;
  const brokenBody = { ok: true, headers: { get: () => null },
    json: async () => { throw Error('Load failed'); } };
  const recovered = makePage(async () => (++attempts === 1 ? brokenBody : response), null);
  await recovered.page.window.loadManualForumEvents();
  assert.equal(attempts, 2);
  assert.equal(recovered.page.EVENTS.length, publishedMerged.length);
  assert.equal(recovered.getRefreshed(), 1);
  assert.ok(!recovered.status.textContent.includes('失敗'));

  const fromCache = makePage(async () => brokenBody, response);
  await fromCache.page.window.loadManualForumEvents();
  assert.equal(fromCache.page.EVENTS.length, publishedMerged.length);
  assert.equal(fromCache.getRefreshed(), 1);
  assert.ok(fromCache.status.textContent.includes('保存済みデータを表示'));

  const noBodyOrCache = makePage(async () => brokenBody, null);
  await noBodyOrCache.page.window.loadManualForumEvents();
  assert.equal(noBodyOrCache.page.EVENTS.length, publishedAuto.length);
  assert.ok(noBodyOrCache.status.textContent.includes('JSON解析失敗（Load failed）'));
  console.log('Manual recovery integration tests passed.');
}
testManualRecovery().catch(e => { console.error(e); process.exitCode = 1; });

// Test the service worker response-body path, not just the page's fetch() mock.
async function testManualServiceWorker() {
  const run = async (fetcher, cached, put) => {
    const listeners = {};
    const policyCached = new Response(JSON.stringify(policy), {status: 200, headers: {'Content-Type': 'application/json'}});
    const sw = vm.createContext({
      self: { location: { origin: 'https://calendar.example' },
        addEventListener: (name, fn) => { listeners[name] = fn; } },
      URL, Response, Headers, console, fetch: fetcher,
      caches: { match: async key => {
          if (String(key) === './event-policy.json') return policyCached.clone();
          return cached && typeof cached.clone === 'function' ? cached.clone() : cached;
        },
        open: async () => ({ put }) }
    });
    vm.runInContext(fs.readFileSync('sw.js', 'utf8'), sw);
    let pending;
    listeners.fetch({ request: { method: 'GET',
      url: 'https://calendar.example/forum-calendar/manual_events.json?ts=1' },
      respondWith: p => { pending = p; } });
    assert.ok(pending, 'Manual request was not intercepted');
    return pending;
  };
  const cached = new Response(JSON.stringify(publishedManual), { status: 200 });
  const interrupted = { ok: true, status: 200,
    text: async () => { throw Error('Load failed'); } };
  let result = await run(async () => interrupted, cached, async () => {});
  assert.equal(result.headers.get('X-Forum-Manual-Cache'), 'stale');
  assert.equal((await result.json()).length, publishedManual.length);

  result = await run(async () => new Response('[{}]', { status: 200 }), cached,
    async () => { throw Error('invalid manual payload must not be cached'); });
  assert.equal(result.headers.get('X-Forum-Manual-Cache'), 'stale');
  assert.equal((await result.json()).length, publishedManual.length);

  const invalidSource = [{...publishedManual[0], id: 'invalid-source-type', source_type: 'not_allowed'}];
  result = await run(async () => new Response(JSON.stringify(invalidSource), { status: 200 }), cached,
    async () => { throw Error('unknown source_type must not be cached'); });
  assert.equal(result.headers.get('X-Forum-Manual-Cache'), 'stale');
  assert.equal((await result.json()).length, publishedManual.length);

  const invalidX = [{...publishedManual[0], id: 'invalid-x-host', source_type: 'x',
    source_url: 'https://example.org/not-x'}];
  result = await run(async () => new Response(JSON.stringify(invalidX), { status: 200 }), cached,
    async () => { throw Error('invalid X host must not be cached'); });
  assert.equal(result.headers.get('X-Forum-Manual-Cache'), 'stale');
  assert.equal((await result.json()).length, publishedManual.length);

  const invalidCityHost = [{...publishedManual[0], id: 'invalid-city-host', source_type: 'city_schedule',
    source_url: 'https://example.org/not-city', source_verified: true}];
  result = await run(async () => new Response(JSON.stringify(invalidCityHost), { status: 200 }), cached,
    async () => { throw Error('invalid city host must not be cached'); });
  assert.equal(result.headers.get('X-Forum-Manual-Cache'), 'stale');
  assert.equal((await result.json()).length, publishedManual.length);

  const unverifiedCity = [{...publishedManual[0], id: 'unverified-city-guide', source_type: 'city_event_guide',
    source_url: 'https://www.city.inazawa.aichi.jp/ica/0000002507.html', source_verified: false}];
  result = await run(async () => new Response(JSON.stringify(unverifiedCity), { status: 200 }), cached,
    async () => { throw Error('unverified city source must not be cached'); });
  assert.equal(result.headers.get('X-Forum-Manual-Cache'), 'stale');
  assert.equal((await result.json()).length, publishedManual.length);

  let key = '';
  result = await run(async () => new Response(JSON.stringify(publishedManual), { status: 200 }), null,
    async (path, value) => { key = path; assert.equal((await value.json()).length, publishedManual.length); });
  assert.equal(key, './manual_events.json');
  assert.equal((await result.json()).length, publishedManual.length);
  result = await run(async () => new Response(JSON.stringify(publishedManual), { status: 200 }), null,
    async () => { throw Error('cache quota'); });
  assert.equal((await result.json()).length, publishedManual.length);
  console.log('Service Worker interrupted-body regression tests passed.');
}
testManualServiceWorker().catch(e => { console.error(e); process.exitCode = 1; });
