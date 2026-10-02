const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const eventsText = fs.readFileSync(path.join(root, 'events.json'), 'utf8');
const policyText = fs.readFileSync(path.join(root, 'event-policy.json'), 'utf8');
const sourceEvents = JSON.parse(eventsText);
const sourcePolicy = JSON.parse(policyText);
assert.ok(Array.isArray(sourceEvents) && sourceEvents.length > 0);

async function main() {
  const handlers = {};
  const stored = new Map();
  let mode = 'online';

  const cache = {
    put: async (key, response) => {
      stored.set(String(key), await response.text());
    },
    addAll: async () => {},
  };
  const context = {
    URL, Response, console,
    self: {
      location: {origin: 'https://calendar.example'},
      addEventListener: (name, callback) => { handlers[name] = callback; },
      skipWaiting: () => {},
      clients: {claim: async () => {}},
    },
    caches: {
      open: async () => cache,
      match: async key => stored.has(String(key))
        ? new Response(stored.get(String(key)), {status: 200, headers: {'Content-Type': 'application/json'}})
        : undefined,
      keys: async () => [],
      delete: async () => true,
    },
    fetch: async request => {
      const requestUrl = String(request && request.url || request || '');
      if (requestUrl.includes('event-policy.json')) {
        if (mode === 'policy-malformed') return new Response('{"schema_version":1}', {status: 200, headers: {'Content-Type': 'application/json'}});
        if (mode === 'policy-rank-invalid') {
          const invalid = JSON.parse(JSON.stringify(sourcePolicy));
          invalid.source_groups.find(group => group.name === 'city_official').rank = 3;
          return new Response(JSON.stringify(invalid), {status: 200, headers: {'Content-Type': 'application/json'}});
        }
        return new Response(policyText, {status: 200, headers: {'Content-Type': 'application/json'}});
      }
      if (mode === 'offline') throw new Error('network offline');
      if (mode === 'empty') return new Response('[]', {status: 200, headers: {'Content-Type': 'application/json'}});
      if (mode === 'malformed') return new Response('[{}]', {status: 200, headers: {'Content-Type': 'application/json'}});
      return new Response(eventsText, {status: 200, headers: {'Content-Type': 'application/json'}});
    },
  };

  vm.createContext(context);
  const swSource = fs.readFileSync(path.join(root, 'sw.js'), 'utf8');
  vm.runInContext(swSource, context);

  const dispatch = async (filename, suffix) => {
    let answer;
    handlers.fetch({
      request: {method: 'GET', url: 'https://calendar.example/' + filename + '?ts=' + suffix},
      respondWith: promise => { answer = promise; },
    });
    assert.ok(answer, filename + ' request must be handled by the service worker');
    return answer;
  };
  const dispatchEvents = suffix => dispatch('events.json', suffix);

  const online = await dispatchEvents('online');
  assert.equal(online.status, 200);
  assert.equal(online.headers.get('X-Forum-Events-Cache'), null);
  assert.deepEqual(await online.json(), sourceEvents);
  assert.ok(stored.has('./events.json'), 'successful automatic data must be cached');

  mode = 'offline';
  const offline = await dispatchEvents('offline');
  assert.equal(offline.status, 200);
  assert.equal(offline.headers.get('X-Forum-Events-Cache'), 'stale');
  assert.deepEqual(await offline.json(), sourceEvents);

  mode = 'empty';
  const invalid = await dispatchEvents('invalid');
  assert.equal(invalid.headers.get('X-Forum-Events-Cache'), 'stale');
  assert.deepEqual(await invalid.json(), sourceEvents, 'empty network data must not replace the saved dataset');

  mode = 'malformed';
  const malformed = await dispatchEvents('malformed');
  assert.equal(malformed.headers.get('X-Forum-Events-Cache'), 'stale');
  assert.deepEqual(await malformed.json(), sourceEvents, 'structurally invalid network data must not replace the saved dataset');
  assert.deepEqual(JSON.parse(stored.get('./events.json')), sourceEvents);

  mode = 'online';
  const policyOnline = await dispatch('event-policy.json', 'policy-online');
  assert.deepEqual(await policyOnline.json(), sourcePolicy);
  mode = 'policy-malformed';
  const policyFallback = await dispatch('event-policy.json', 'policy-malformed');
  assert.equal(policyFallback.headers.get('X-Forum-Policy-Cache'), 'stale');
  assert.deepEqual(await policyFallback.json(), sourcePolicy, 'invalid policy must not replace the saved policy');

  mode = 'policy-rank-invalid';
  const rankFallback = await dispatch('event-policy.json', 'policy-rank-invalid');
  assert.equal(rankFallback.headers.get('X-Forum-Policy-Cache'), 'stale');
  assert.deepEqual(await rankFallback.json(), sourcePolicy, 'wrong source ranks must not replace the saved policy');
  assert.deepEqual(JSON.parse(stored.get('./event-policy.json')), sourcePolicy);

  stored.clear();
  mode = 'offline';
  await assert.rejects(dispatchEvents('no-cache'), /network offline/);

  const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
  assert.ok(!html.includes('FALLBACK_EVENTS'), 'hard-coded automatic fallback must not return');
  assert.ok(html.includes('let EVENTS=[];'), 'automatic events should start empty and come from events.json');
  assert.ok(html.includes('X-Forum-Events-Cache'), 'UI must detect saved automatic event data');
  assert.ok(swSource.includes("POLICY_DATA='./event-policy.json'"), 'shared event policy must be cached for offline use');
  assert.ok(swSource.includes("const CACHE='forum-calendar-v9-3-7-r3'"), 'semantic validation changes must use a fresh cache generation');
  const staticLine = swSource.split('\n').find(line => line.startsWith('const STATIC='));
  assert.ok(staticLine && !/AUTO_DATA|POLICY_DATA|MANUAL_DATA|VERIFIED_DATA/.test(staticLine),
    'semantic JSON data must not be blindly precached by cache.addAll');
  assert.ok(swSource.includes('precacheValidatedData'), 'install must validate semantic JSON before replacing the old cache');
  const policy = JSON.parse(fs.readFileSync(path.join(root, 'event-policy.json'), 'utf8'));
  assert.equal(policy.schema_version, 1);
  const policyLoad = html.indexOf('await loadEventPolicy()');
  const manualLoad = html.indexOf("script.src = './manual-events.js");
  assert.ok(policyLoad >= 0 && manualLoad > policyLoad, 'event policy must load before manual merge code');

  console.log('PASS: events.json is the single source and shared event policy is available before offline overlays');
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
