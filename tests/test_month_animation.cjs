const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const html=fs.readFileSync(path.resolve(__dirname,'../index.html'),'utf8');
const start=html.indexOf('async function moveMonth(delta){');
const end=html.indexOf('if(calendarEl&&window.PointerEvent){', start);
assert.ok(start!==-1&&end>start,'month navigation function must exist');
const source=html.slice(start,end);
async function caseRun(mode){
  let calls=0,canceled=0;
  const pane={animate(){
    calls++;
    return {finished:mode==='incoming-fail'&&calls===2
        ?Promise.reject(new Error('animation interrupted'))
        :mode==='outgoing-fail'&&calls===1
        ?Promise.reject(new Error('outgoing interrupted'))
        :Promise.resolve(),
      cancel(){canceled++;}};
  }};
  const ctx={pane,Date,window:{matchMedia:()=>({matches:false})},
    document:{querySelector:()=>pane}};
  vm.createContext(ctx);
  vm.runInContext('let view=new Date(2026,9,1),selected="2026-10-10",monthAnimating=false,rendered=0;function renderCalendar(){rendered++;}',ctx);
  vm.runInContext(source,ctx);
  await vm.runInContext('moveMonth(1)',ctx);
  assert.equal(vm.runInContext('view.getMonth()',ctx),10,'move exactly one month');
  assert.equal(vm.runInContext('rendered',ctx),1,'render once only');
  assert.equal(vm.runInContext('selected',ctx),null);
  assert.equal(vm.runInContext('monthAnimating',ctx),false);
  assert.ok(canceled>=1,'animation fills should be cleared');
}
(async()=>{
  await caseRun('normal');
  await caseRun('incoming-fail');
  await caseRun('outgoing-fail');
  console.log('PASS: normal and interrupted month transitions move exactly once');
})().catch(e=>{console.error(e);process.exitCode=1;});
