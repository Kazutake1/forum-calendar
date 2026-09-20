const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const context = vm.createContext({
  window: {}, URL,
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

console.log('Manual identity/provenance regression tests passed.');

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

// Equal-tier reports with the same start are compatible even when only one gives door time.
result=merge([base('開演18:00',{source_type:'city_schedule',source_url:'https://www.city.inazawa.aichi.jp/ica/0000002507.html',source_verified:true,verified_fields:['time']})],
 [manual('opening-city','開場17:30／開演18:00',{source_type:'city_schedule',source_url:'https://www.city.inazawa.aichi.jp/ica/0000002507.html',source_verified:true,verified_fields:['time']})]);
assert.equal(result.length,1);
assert.equal(result[0].time,'開場17:30／開演18:00');
