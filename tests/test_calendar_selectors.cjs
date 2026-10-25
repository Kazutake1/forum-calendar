const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const html=fs.readFileSync(path.resolve(__dirname,'../index.html'),'utf8');
const functionNames=['eventMatches','selectVisibleEvents','groupEventsByDate'];
const getFn=name=>{
  const line=html.split('\\n').find(l=>l.startsWith('function '+name+'('));
  assert.ok(line,'Missing pure selector: '+name);
  return line;
};
const venues=html.split('\\n').find(l=>l.startsWith('const venuesOf='));
assert.ok(venues);
const ctx={};
vm.createContext(ctx);
vm.runInContext(venues+'\\n'+functionNames.map(getFn).join('\\n'),ctx);
const records=[
  {date:'2026-11-01',title:'Morning Classic',hall:'小ホール',venues:['小ホール'],time:'10:00'},
  {date:'2026-11-01',title:'屋外イベント',hall:'文化の丘公園',venues:['文化の丘公園'],time:'13:00'},
  {date:'2026-11-02',title:'別会場コンサート',hall:'大ホール',venues:['大ホール'],time:'18:00'},
  {date:'2026-11-02',title:'複数会場',hall:'中ホール',venues:['中ホール','小ホール'],time:''}
];
const original=JSON.stringify(records);
const pick=(venue,query)=>ctx.selectVisibleEvents(records,venue,query);
assert.equal(pick('all','').length,4);
assert.equal(pick('小ホール','').length,2);
assert.equal(pick('小ホール','CLASSIC').length,1);
assert.equal(pick('文化の丘公園','').length,1);
assert.equal(pick('all','  18:00 ').length,1);
assert.equal(pick('大ホール','公園').length,0);
const grouped=ctx.groupEventsByDate(pick('all',''));
assert.equal(grouped.get('2026-11-01').length,2);
assert.equal(grouped.get('2026-11-02').length,2);
assert.equal(grouped.get('2026-11-03'),undefined);
assert.equal(JSON.stringify(records),original,'selectors may not alter saved events');
assert.ok(html.includes('es=grouped.get(k)||[]'));
assert.ok(html.includes('function renderList(){const es=selectVisibleEvents(EVENTS,filter,query)'));
console.log('PASS: calendar and list share pure event selectors without changing events');
