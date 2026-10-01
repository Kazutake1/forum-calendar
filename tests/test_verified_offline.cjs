const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.resolve(__dirname, '..');

async function main() {
  const json = fs.readFileSync(path.join(root,'verified_schedule.json'),'utf8');
  const handlers = {};
  let mode='offline';
  const context = {
    URL, Response, console,
    self:{location:{origin:'https://calendar.example'},
      addEventListener:(name,callback)=>handlers[name]=callback},
    caches:{match:async key=>key==='./verified_schedule.json'
      ? new Response(json,{status:200,headers:{'Content-Type':'application/json'}}) : null},
    fetch:async ()=>{
      if(mode==='offline')throw new Error('network offline');
      const bad={...JSON.parse(json),source_pdf_sha256:'wrong'};
      return new Response(JSON.stringify(bad),{status:200,headers:{'Content-Type':'application/json'}});
    }
  };
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(root,'sw.js'),'utf8'),context);
  const dispatch=async suffix=>{
    let answer;
    handlers.fetch({request:{method:'GET',url:'https://calendar.example/verified_schedule.json?ts='+suffix},
      respondWith:promise=>answer=promise});
    return answer;
  };
  let response=await dispatch('offline');
  assert.equal(response.status,200);
  assert.equal(response.headers.get('X-Forum-Verified-Cache'),'stale');
  let data=await response.json();
  assert.equal(data.events.length,58);

  mode='invalid';
  response=await dispatch('invalid');
  assert.equal(response.headers.get('X-Forum-Verified-Cache'),'stale');
  data=await response.json();
  assert.equal(data.source_pdf_sha256,JSON.parse(json).source_pdf_sha256);
  assert.equal(data.events.length,58);
  console.log('PASS: offline/invalid verified schedule recovers 58 pinned rows without poisoning cache');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
