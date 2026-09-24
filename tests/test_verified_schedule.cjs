const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const records = name => JSON.parse(fs.readFileSync(path.join(root,name),'utf8'));
const originalAuto = records('events.json');
const originalManual = records('manual_events.json');
const verified = records('verified_schedule.json');
const ctx = {window:{}, URL, console, linkInfo:()=>({url:'',label:''})};
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
const officialMismatch = mergedManual.map(x=>x.title==='音楽家の集い Vol.113 峰岸桂子＆ルイス・サルトール「ラテンの魅力」'
  ? {...x,source_verified:true,source_url:'https://www.city.inazawa.aichi.jp/ica/0000002507.html'} : x);
assert.equal(ctx.window.mergeVerifiedForumSchedule(officialMismatch,verified)
  .find(x=>x.id==='schedule-11-16').detail_review.status,'要確認');
assert.equal(after.some(x=>x.id==='manual-20261011-suyama-ballet-turandot'),false);
assert.deepEqual(records('events.json'),originalAuto);
assert.deepEqual(records('manual_events.json'),originalManual);
assert.throws(()=>ctx.window.mergeVerifiedForumSchedule(mergedManual,{...verified,source_pdf_sha256:'wrong'}));
assert.throws(()=>ctx.window.mergeVerifiedForumSchedule(mergedManual,{...verified,events:verified.events.slice(1)}));
assert.throws(()=>ctx.window.mergeVerifiedForumSchedule(
  mergedManual.concat([{date:'2026-11-14',hall:'小ホール',title:'未照合の同時刻の別名催事',time:'14:30-15:30'}]),verified),
  /未照合の同一公演候補/);
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
console.log('PASS: verified 58, mapped 10, lecture detail only, original inputs preserved, fail-closed data checks');
