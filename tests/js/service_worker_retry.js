/* Execute the actual worker in an isolated worker-like context. No network. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('static/js/sw.js', 'utf8');

async function lifecycle() {
  const listeners = {}, removed = [], added = [];
  let skipped = false, claimed = false, cacheName;
  const context = vm.createContext({
    fetch: async url => {
      if (url.endsWith('/app.css')) return new Response('private', {headers: {'Cache-Control': 'private'}});
      if (url.endsWith('/app.js')) return new Response('no-store', {headers: {'Cache-Control': 'no-store'}});
      if (url.endsWith('/search.js')) return new Response('error', {status: 503});
      if (url.endsWith('/icon-192.png')) {
        const response = new Response('redirect');
        Object.defineProperty(response, 'redirected', {value: true});
        return response;
      }
      return new Response('public asset');
    }, Response,
    caches: {
      open: async (name) => {cacheName = name; return {put: async (url) => {added.push(url);}};},
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
  assert.deepEqual(added.sort(), ['/static/img/icons/icon-512.png', '/static/offline.html']);
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

async function cachePrivacy() {
  for (const path of ['/me', '/e/bearer-token/resume/person-token', '/r/survey-token', '/seq?tokens=secret', '/photo/12']) {
    for (const offline of [false, true]) {
      const listeners = {}, writes = [], lookups = [];
      const context = vm.createContext({
        URL, Response, setTimeout: fn => fn(),
        fetch: async () => {
          if (offline) throw new Error('offline');
          return new Response('personal data', {headers: {'Cache-Control': 'no-store'}});
        },
        caches: {
          open: async () => ({put: async key => writes.push(key), match: async key => {
            lookups.push(key); return new Response('stale personal data');
          }}),
          match: async key => {lookups.push(key); return new Response('generic offline shell');},
        },
        self: {location: {origin: 'https://office.test'},
          addEventListener: (name, fn) => {listeners[name] = fn;}},
      });
      vm.runInContext(source, context);
      // A small worker Request stand-in permits navigate mode in Node.
      const request = {url: 'https://office.test' + path, method: 'GET',
        mode: path.startsWith('/photo/') ? 'cors' : 'navigate', clone() {return this;}};
      let pending;
      listeners.fetch({request, respondWith: p => {pending = p;}});
      let response, failed = false;
      try { response = await pending; } catch (_) {failed = true;}
      assert.equal(writes.length, 0, path + ' must never be stored');
      assert.ok(lookups.every(key => key === '/static/offline.html'));
      if (!offline) assert.equal(await response.text(), 'personal data');
      else if (request.mode === 'navigate') assert.equal(await response.text(), 'generic offline shell');
      else assert.ok(failed, 'offline photos must not return cached personal data');
    }
  }
  for (const control of ['', 'public, max-age=300', 'no-store', 'private', 'max-age=30, PRIVATE', 'private="cookie"']) {
    const listeners = {}, writes = [], deleted = [];
    const context = vm.createContext({
      URL, Response, setTimeout: fn => fn(),
      fetch: async () => new Response('asset', {headers: {'Cache-Control': control}}),
      caches: {open: async () => ({match: async () => undefined,
        put: async key => writes.push(key), delete: async key => deleted.push(key)})},
      self: {location: {origin: 'https://office.test'},
        addEventListener: (name, fn) => {listeners[name] = fn;}},
    });
    vm.runInContext(source, context);
    const request = {url: 'https://office.test/static/js/app.js', method: 'GET',
      mode: 'cors', clone() {return this;}};
    let pending;
    listeners.fetch({request, respondWith: p => {pending = p;}});
    assert.equal(await (await pending).text(), 'asset');
    const privateResponse = /private|no-store/i.test(control);
    assert.equal(writes.length, privateResponse ? 0 : 1, control);
    assert.equal(deleted.length, privateResponse ? 1 : 0, control);
  }
}

async function companionAudioCache() {
  const listeners = {}, stored = new Map();
  let offline = false;
  const body = fs.readFileSync('static/audio/avatars/dog-1.mp3');
  const context = vm.createContext({
    URL, Response, setTimeout: fn => fn(),
    fetch: async () => {
      if (offline) throw new Error('offline');
      return new Response(body, {headers: {'Content-Type': 'audio/mpeg'}});
    },
    caches: {open: async () => ({
      match: async req => stored.has(req.url) ? stored.get(req.url).clone() : undefined,
      put: async (req, res) => stored.set(req.url, res.clone()),
      delete: async req => stored.delete(req.url),
    })},
    self: {location: {origin: 'https://office.test'},
      addEventListener: (name, fn) => {listeners[name] = fn;}},
  });
  vm.runInContext(source, context);
  for (const disconnected of [false, true]) {
    offline = disconnected;
    const request = {url: 'https://office.test/static/audio/avatars/dog-1.mp3',
      method: 'GET', mode: 'cors', clone() {return this;}};
    let pending;
    listeners.fetch({request, respondWith: p => {pending = p;}});
    const response = await pending;
    assert.equal(response.headers.get('Content-Type'), 'audio/mpeg');
    assert.deepEqual(Buffer.from(await response.arrayBuffer()), body);
  }
}

(async () => {
  await lifecycle();
  await cachePrivacy();
  await companionAudioCache();
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
  console.log('Passed: private pages/photos stay out of caches; private assets are rejected; writes are not replayed; GET recovery and queue code remain.');
})().catch((error) => { console.error(error); process.exitCode = 1; });
