/* Execute the actual worker in an isolated worker-like context. No network. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('static/js/sw.js', 'utf8');

async function lifecycle() {
  const listeners = {}, removed = [], added = [];
  let skipped = false, claimed = false, cacheName;
  const context = vm.createContext({
    caches: {
      open: async (name) => {cacheName = name; return {add: async (url) => {added.push(url);}};},
      keys: async () => ['css-is-v6.91-a', cacheName, 'unrelated-cache'],
      delete: async (name) => {removed.push(name);},
    },
    self: {
      addEventListener: (name, fn) => {listeners[name] = fn;},
      skipWaiting: async () => {skipped = true;},
      clients: {claim: async () => {claimed = true;}},
    },
  });
  vm.runInContext(source, context);
  let pending;
  listeners.install({waitUntil: (p) => {pending = p;}});
  await pending;
  listeners.activate({waitUntil: (p) => {pending = p;}});
  await pending;
  assert.notEqual(cacheName, 'css-is-v6.91-a');
  assert.deepEqual(removed, ['css-is-v6.91-a']);
  assert.ok(skipped && claimed);
  assert.ok(added.includes('/static/offline.html'));
}

async function run(method, first, path = '/work/12') {
  let sends = 0, effects = 0, intercepted;
  const listeners = {};
  const fetch = async () => {
    sends++;
    if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) effects++;
    if (sends === 1) {
      if (first instanceof Error) throw first;
      return first;
    }
    return new Response('OK', {status: 200});
  };
  const context = vm.createContext({
    URL, Request, Response, fetch, setTimeout: (fn) => fn(),
    self: {location: {origin: 'https://office.test'},
      addEventListener: (name, handler) => {listeners[name] = handler;}},
  });
  vm.runInContext(source, context);
  const request = new Request('https://office.test' + path, {method,
    ...(!['GET', 'HEAD'].includes(method) ? {body: 'payload=one'} : {})});
  listeners.fetch({request, respondWith: (promise) => {intercepted = promise;}});
  // A worker that does not intercept leaves one native browser fetch.
  let response, error;
  try { response = await (intercepted || fetch(request)); }
  catch (e) { error = e; }
  return {sends, effects, response, error};
}

(async () => {
  await lifecycle();
  for (const method of ['POST', 'PUT', 'PATCH', 'DELETE']) {
    for (const status of [500, 502, 503, 504]) {
      // The server commits; a proxy replaces its response. Missing header
      // does not tell the browser whether that commit happened.
      const r = await run(method, new Response('Unknown outcome', {status}));
      assert.equal(r.sends, 1, `${method} ${status} must not replay`);
      assert.equal(r.effects, 1);
      assert.equal(r.response.status, status);
    }
    const lost = await run(method, new Error('Response lost after commit'));
    assert.equal(lost.effects, 1);
    assert.ok(lost.error);
  }
  const get = await run('GET', new Response('Proxy failure', {status: 503}));
  assert.equal(get.sends, 2);
  assert.equal(get.response.status, 200);
  const network = await run('GET', new Error('Connection lost'));
  assert.equal(network.sends, 2);
  const appError = await run('GET', new Response('App failure', {
    status: 500, headers: {'X-CSS-App': '1'},
  }));
  assert.equal(appError.sends, 1);
  assert.equal(appError.response.status, 500);
  const intake = await run('POST', new Response('Unknown', {status: 503}), '/documents/intake/read');
  assert.equal(intake.effects, 1);
  console.log('Passed: write failures are not replayed; GET recovery and intake pass-through remain.');
})().catch((error) => { console.error(error); process.exitCode = 1; });
