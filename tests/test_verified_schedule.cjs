const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const records = name => JSON.parse(fs.readFileSync(path.join(root,name),'utf8'));
const originalAuto = records('events.json');
const originalManual = records('manual_events.json');
const verified = records('verified_schedule.json');
const policy = records('event-policy.json');
const ctx = {window:{FORUM_EVENT_POLICY:policy}, URL, console, linkInfo:()=>({url:'',label:''})};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(path.join(root,'manual-events.js'),'utf8'),ctx);
vm.runInContext(fs.readFileSync(path.join(root,'verified-schedule.js'),'utf8'),ctx);
const mergedManual = ctx.window.mergeForumEvents(originalAuto,originalManual);
const after = ctx.window.mergeVerifiedForumSchedule(mergedManual,verified);
assert.equal(verified.events.length,58);
assert.equal(verified.events.filter(x=>x.date.startsWith('2026-10')).length,28);
assert.equal(verified.events.filter(x=>x.date.startsWith('2026-11')).length,30);
assert.ok(verified.events.every(x=>!Object.hasOwn(x,'price')));
assert.equal(after.length,mergedManual.length + 58 - 10);
assert.equal(after.filter(x=>x.source_confirmed===true).length,58);
const lecture = after.find(x=>x.id==='schedule-11-14');
const ceremony = after.find(x=>x.id==='schedule-11-15');
assert.equal(lecture.hall,'小ホール');
assert.equal(lecture.time,'14:30-15:30');
assert.equal(lecture.detail_review.status,'要確認');
assert.equal(ceremony.hall,'中ホール');
assert.equal(ceremony.time,'16:00-17:30');
assert.equal(ceremony.detail_review,undefined);
assert.equal(after.some(x=>x.id==='manual-20261114-nagoya-bunri-70th-lecture'),false);
assert.equal(after.some(x=>x.id==='manual-20261031-meiji-zahatorte'),true);
assert.equal(after.some(x=>x.title==='セントラル愛知交響楽団 公開講座 Part3'),true);
assert.equal(after.filter(x=>x.date==='2026-11-19'&&x.hall==='小ホール').length,1);
assert.equal(after.find(x=>x.id==='schedule-11-16').detail_review,undefined);
// A newer verified official listing wins, while the pinned schedule supplies
// a missing end time and its raw source rows are never rewritten.
const officialGuideUrl = 'https://www.city.inazawa.aichi.jp/ica/0000002507.html';
const withOfficialGuide = rows => rows.map(e => {
  const replacements = {
    '2026-11-01': ['KAZUYOSHI SAITO LIVE TOUR2026"日常 Days"', '17:00〜'],
    '2026-11-05': ['モーニングクラシックVol.3', '10:00〜'],
    '2026-11-15': ['音楽家の集いVol.113「ラテンの魅力 峰岸桂子＆ルイス・サルトール」', '14:00〜'],
  };
  const replacement = replacements[e.date];
  if (!replacement) return e;
  return {...e, previous_titles:[...new Set([...(e.previous_titles||[]),e.title])], title:replacement[0], time:replacement[1],
    source_verified:true, source_type:'city_event_guide', source_url:officialGuideUrl,
    verified_fields:['date','title','hall','time']};
});
const improvedAuto=withOfficialGuide(originalAuto);
const improved = ctx.window.mergeVerifiedForumSchedule(
  ctx.window.mergeForumEvents(improvedAuto,originalManual), verified);
assert.equal(improved.length, after.length);
assert.equal(improved.filter(e=>e.source_confirmed===true).length,58);
assert.equal(improved.filter(e=>e.date==='2026-11-15'&&e.hall==='中ホール').length,1);
const improvedConcert = improved.find(e=>e.id==='schedule-11-16');
assert.equal(improvedConcert.title, '音楽家の集いVol.113「ラテンの魅力 峰岸桂子＆ルイス・サルトール」');
assert.equal(improvedConcert.time,'14:00-15:30');
assert.equal(improvedConcert.source_type,'city_event_guide');
assert.equal(improvedConcert.official_guide_evidence_url,officialGuideUrl);
assert.equal(improvedConcert.detail_review,undefined);
assert.equal(improved.find(e=>e.id==='schedule-11-04').title,'モーニングクラシックVol.3');
assert.equal(improved.find(e=>e.id==='schedule-11-04').time,'10:00-11:30');
assert.equal(improved.find(e=>e.id==='schedule-11-01').source_type,'city_event_guide');
const repeatedGuide=ctx.window.mergeVerifiedForumSchedule(
  ctx.window.mergeForumEvents(withOfficialGuide(improvedAuto),originalManual),verified);
assert.equal(repeatedGuide.length,improved.length,'Repeated guide fixtures retain reviewed old-title aliases');
assert.equal(repeatedGuide.reviewWarnings.length,0);
const adjustedStart = improvedAuto.map(e=>e.date==='2026-11-15' ? {...e,time:'13:00〜'} : e);
const officialTimeWins = ctx.window.mergeVerifiedForumSchedule(
  ctx.window.mergeForumEvents(adjustedStart,originalManual), verified);
assert.equal(officialTimeWins.find(e=>e.id==='schedule-11-16').time,'13:00〜');
assert.equal(officialTimeWins.find(e=>e.id==='schedule-11-16').detail_review.status,'要確認');
const differentEnd = improvedAuto.map(e=>e.date==='2026-11-15' ? {...e,time:'14:00〜16:00'} : e);
const officialEndWins = ctx.window.mergeVerifiedForumSchedule(
  ctx.window.mergeForumEvents(differentEnd,originalManual), verified);
assert.equal(officialEndWins.find(e=>e.id==='schedule-11-16').time,'14:00〜16:00');
assert.equal(officialEndWins.find(e=>e.id==='schedule-11-16').detail_review.status,'要確認');
assert.equal(records('verified_schedule.json').events.length,58);

// Item-level official organizer evidence wins even if the top-level label is older.
const organizerUrl='https://example.org/concert';
const organizerAuto=improvedAuto.map(e=>e.date==='2026-11-15'?{...e,time:'開場12:30／開演13:00',
  field_sources:{time:{source_type:'organizer',source_url:organizerUrl,verified:true,event_specific:true}}}:e);
const organizerResult=ctx.window.mergeVerifiedForumSchedule(
  ctx.window.mergeForumEvents(organizerAuto,originalManual),verified);
const organizerConcert=organizerResult.find(e=>e.id==='schedule-11-16');
assert.equal(organizerConcert.time,'開場12:30／開演13:00');
assert.equal(organizerConcert.field_sources.time.source_type,'organizer');
assert.equal(organizerConcert.source_url,organizerUrl);
assert.equal(organizerConcert.detail_review.status,'要確認');
assert.ok(organizerConcert.official_change_history.some(change=>change.field==='time'&&change.source_url===organizerUrl&&change.checked_at));

// Stronger titles must not certify a weak time, and a later X report cannot reverse the schedule.
for(const proof of [{source_type:'x',source_url:'https://x.com/example/status/1',verified:true},
                    {source_type:'city_event_guide',source_url:officialGuideUrl,verified:false}]){
  const mixed=improvedAuto.map(e=>e.date==='2026-11-15'?{...e,time:'13:00〜',field_sources:{time:proof}}:e);
  const result=ctx.window.mergeVerifiedForumSchedule(ctx.window.mergeForumEvents(mixed,originalManual),verified);
  assert.equal(result.find(e=>e.id==='schedule-11-16').time,'14:00-15:30');
  assert.equal(result.find(e=>e.id==='schedule-11-16').field_sources.time.source_type,'city_schedule');
}
// The guide may omit an end time: keep it as separately attributed schedule supplementation.
assert.equal(improvedConcert.time_supplement.end_time,'15:30');
assert.equal(improvedConcert.time_supplement.source_type,'city_schedule');
const withDoors=improvedAuto.map(e=>e.date==='2026-11-15'?{...e,time:'開場13:30／開演14:00'}:e);
const doorsResult=ctx.window.mergeVerifiedForumSchedule(ctx.window.mergeForumEvents(withDoors,originalManual),verified);
assert.equal(doorsResult.find(e=>e.id==='schedule-11-16').time,'開場13:30／開演14:00（終演15:30）');
assert.equal(doorsResult.find(e=>e.id==='schedule-11-16').detail_review,undefined);
const doorOnly=improvedAuto.map(e=>e.date==='2026-11-15'?{...e,time:'開場13:30'}:e);
const doorOnlyResult=ctx.window.mergeVerifiedForumSchedule(ctx.window.mergeForumEvents(doorOnly,originalManual),verified);
assert.equal(doorOnlyResult.find(e=>e.id==='schedule-11-16').time,'開場13:30／開演14:00（終演15:30）');
assert.equal(doorOnlyResult.find(e=>e.id==='schedule-11-16').time_supplement.start_time,'14:00');
// Only the missing start is supplemented: the official end must never be replaced.
const doorAndEnd=improvedAuto.map(e=>e.date==='2026-11-15'?{...e,time:'開場13:30／終演16:00'}:e);
const doorEndResult=ctx.window.mergeVerifiedForumSchedule(ctx.window.mergeForumEvents(doorAndEnd,originalManual),verified);
const doorEndConcert=doorEndResult.find(e=>e.id==='schedule-11-16');
assert.equal(doorEndConcert.time,'開場13:30／開演14:00（終演16:00）');
assert.equal(doorEndConcert.time_supplement.start_time,'14:00');
assert.equal(doorEndConcert.time_supplement.end_time,undefined);
assert.equal(doorEndConcert.detail_review.status,'要確認');
const namedEnd=improvedAuto.map(e=>e.date==='2026-11-15'?{...e,time:'開場13:30／開演14:00／終演16:00'}:e);
const namedEndResult=ctx.window.mergeVerifiedForumSchedule(ctx.window.mergeForumEvents(namedEnd,originalManual),verified);
assert.equal(namedEndResult.find(e=>e.id==='schedule-11-16').time,'開場13:30／開演14:00／終演16:00');
assert.equal(namedEndResult.find(e=>e.id==='schedule-11-16').detail_review.status,'要確認');

const changedHall=improvedAuto.map(e=>e.date==='2026-11-15'?{...e,hall:'大ホール',venues:['大ホール']}:e);
const hallResult=ctx.window.mergeVerifiedForumSchedule(ctx.window.mergeForumEvents(changedHall,originalManual),verified);
assert.equal(hallResult.find(e=>e.id==='schedule-11-16').hall,'大ホール');
assert.equal(hallResult.find(e=>e.id==='schedule-11-16').detail_review.status,'要確認');
assert.deepEqual(records('verified_schedule.json'),verified);

const officialMismatch = mergedManual.map(x=>x.date==='2026-11-15'&&x.hall==='中ホール'
  ? {...x,time:'16:00〜',field_sources:{},source_type:'city_official',source_verified:true,
     source_url:'https://www.city.inazawa.aichi.jp/ica/0000002507.html'} : x);
assert.equal(ctx.window.mergeVerifiedForumSchedule(officialMismatch,verified)
  .find(x=>x.id==='schedule-11-16').detail_review.status,'要確認');
assert.equal(after.some(x=>x.id==='manual-20261011-suyama-ballet-turandot'),false);
assert.deepEqual(records('events.json'),originalAuto);
assert.deepEqual(records('manual_events.json'),originalManual);
assert.throws(()=>ctx.window.mergeVerifiedForumSchedule(mergedManual,{...verified,source_pdf_sha256:'wrong'}));
assert.throws(()=>ctx.window.mergeVerifiedForumSchedule(mergedManual,{...verified,events:verified.events.slice(1)}));
const ambiguous=ctx.window.mergeVerifiedForumSchedule(
  mergedManual.concat([{date:'2026-11-14',hall:'小ホール',title:'未照合の同時刻の別名催事',time:'14:30-15:30'}]),verified);
assert.equal(ambiguous.filter(x=>x.source_confirmed===true).length,58);
assert.equal(ambiguous.find(x=>x.id==='schedule-11-14').detail_review.status,'要確認');
assert.ok(ambiguous.reviewWarnings.includes('schedule-11-14'));
const missingManual=ctx.window.mergeVerifiedForumSchedule(
  mergedManual.filter(x=>x.id!=='manual-20261011-suyama-ballet-turandot'),verified);
assert.equal(missingManual.filter(x=>x.source_confirmed===true).length,58);
assert.ok(missingManual.reviewWarnings.includes('schedule-10-07'));
assert.equal(missingManual.find(x=>x.id==='schedule-10-07').detail_review.status,'要確認');
assert.equal(missingManual.find(x=>x.id==='schedule-11-15').detail_review,undefined);
const html = fs.readFileSync(path.join(root,'index.html'),'utf8');
const renderCode = html.split('\n').find(line=>line.startsWith('function detailsHTML('));
assert.ok(renderCode);
const esc = v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const view = {esc,linkInfo:e=>({url:e.source_url,label:'催事予定表の原本'}),
  venuesOf:e=>e.venues,detailHallRank:e=>e.hall==='大ホール'?0:e.hall==='中ホール'?1:2,
  badges:e=>e.hall,safeHref:u=>u,googleUrl:()=> 'https://www.google.com/',console};
vm.createContext(view);
vm.runInContext(renderCode,view);
const lectureDetail=vm.runInContext('detailsHTML(events)',Object.assign(view,{events:[lecture]}));
assert.ok(lectureDetail.includes('要確認'));
assert.ok(lectureDetail.includes('小ホール'));
assert.ok(lectureDetail.includes('異なる記載の出典'));
assert.ok(!lectureDetail.includes('料金・入場'));
assert.ok(!vm.runInContext('detailsHTML(events)',Object.assign(view,{events:[ceremony]})).includes('要確認'));
const inject = {...lecture, detail_review:{status:'要確認',note:'<script>alert(1)</script>'}};
assert.ok(!vm.runInContext('detailsHTML(events)',Object.assign(view,{events:[inject]})).includes('<script>'));
assert.ok(vm.runInContext('detailsHTML(events)',view).includes('&lt;script&gt;'));
console.log('PASS: verified 58, mapped 10, row-local review, original inputs preserved, fail-closed data checks');
