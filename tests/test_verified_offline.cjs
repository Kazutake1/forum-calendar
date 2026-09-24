const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.resolve(__dirname, '..');

async function main() {
  const json = fs.readFileSync(path.join(root,'verified_schedule.json'),'utf8');
  const handlers = {};
  const context = {
    URL, Response, console,
    self:{location:{origin:'https://calendar.example'},
      addEventListener:(name,callback)=>handlers[name]=callback},
    caches:{match:async key=>key==='./verified_schedule.json'
      ? new Response(json,{status:200,headers:{'Content-Type':'application/json'}}) : null},
    fetch:async ()=>{throw new Error('network offline');}
  };
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(root,'sw.js'),'utf8'),context);
  let answer;
  handlers.fetch({request:{method:'GET',url:'https://calendar.example/verified_schedule.json?ts=1'},
    respondWith:promise=>answer=promise});
  const response=await answer;
  assert.equal(response.status,200);
  assert.equal(response.headers.get('X-Forum-Verified-Cache'),'stale');
  const data=await response.json();
  assert.equal(data.events.length,58);
  console.log('PASS: offline verified schedule recovers 58 pinned rows with stale notice');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
