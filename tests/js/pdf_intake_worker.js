// Verify transient reads bypass worker body forwarding without changing other POSTs.
const assert = require('assert');
const vm = require('vm');
const fs = require('fs');
const handlers = {};
const origin = 'https://example.test';
let forwarded = 0;
vm.runInNewContext(fs.readFileSync('static/js/sw.js', 'utf8'), {
 self: {location: {origin}, addEventListener: (name, fn) => handlers[name] = fn},
 URL, setTimeout,
 fetch: async () => { forwarded++; return {status: 200, headers: {get: () => '1'}}; },
});
(async () => {
 for (const path of ['/documents/intake/read', '/documents/intake/page', '/documents/intake/pages-result']) {
  handlers.fetch({request: {url: origin + path, method: 'POST', clone() {throw Error('Body was cloned');}},
   respondWith() {throw Error('Transient read was intercepted');}});
 }
 let response;
 handlers.fetch({request: {url: origin + '/documents/new', method: 'POST', clone() {return this;}},
  respondWith(value) {response = value;}});
 assert(response);
 await response;
 assert.equal(forwarded, 1);
 console.log('Temporary reads bypass worker; normal submissions retain existing handling.');
})().catch(error => {console.error(error); process.exitCode = 1;});
