const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const eventsText = fs.readFileSync(path.join(root, 'events.json'), 'utf8');
const sourceEvents = JSON.parse(eventsText);
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
    fetch: async () => {
      if (mode === 'offline') throw new Error('network offline');
      if (mode === 'empty') return new Response('[]', {status: 200, headers: {'Content-Type': 'application/json'}});
      return new Response(eventsText, {status: 200, headers: {'Content-Type': 'application/json'}});
    },
  };

  vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(root, 'sw.js'), 'utf8'), context);

  const dispatch = async suffix => {
    let answer;
    handlers.fetch({
      request: {method: 'GET', url: 'https://calendar.example/events.json?ts=' + suffix},
      respondWith: promise => { answer = promise; },
    });
    assert.ok(answer, 'events.json request must be handled by the service worker');
    return answer;
  };

  const online = await dispatch('online');
  assert.equal(online.status, 200);
  assert.equal(online.headers.get('X-Forum-Events-Cache'), null);
  assert.deepEqual(await online.json(), sourceEvents);
  assert.ok(stored.has('./events.json'), 'successful automatic data must be cached');

  mode = 'offline';
  const offline = await dispatch('offline');
  assert.equal(offline.status, 200);
  assert.equal(offline.headers.get('X-Forum-Events-Cache'), 'stale');
  assert.deepEqual(await offline.json(), sourceEvents);

  mode = 'empty';
  const invalid = await dispatch('invalid');
  assert.equal(invalid.headers.get('X-Forum-Events-Cache'), 'stale');
  assert.deepEqual(await invalid.json(), sourceEvents, 'invalid network data must not replace the saved dataset');

  stored.clear();
  mode = 'offline';
  await assert.rejects(dispatch('no-cache'), /network offline/);

  const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
  assert.ok(!html.includes('FALLBACK_EVENTS'), 'hard-coded automatic fallback must not return');
  assert.ok(html.includes('let EVENTS=[];'), 'automatic events should start empty and come from events.json');
  assert.ok(html.includes('X-Forum-Events-Cache'), 'UI must detect saved automatic event data');

  console.log('PASS: events.json is the single source and saved automatic data is used offline');
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
