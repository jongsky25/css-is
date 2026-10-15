// Travel checklist: upload files for a row. Each file is shrunk on the device when it is a big photo, sent to
// the server, and the server puts it in the office Drive. The page only ever shows the folder link.
// A ticket or receipt also comes back with the amount the AI read off it. That reading is kept only in this
// browser's session (never on the server) and offered on the prepare page, where the person confirms it.
(function () {
  'use strict';
  var MAX = 6 * 1024 * 1024, EDGE = 2000;

  function shrink(file) {                       // a photo over ~1.5 MB becomes a JPEG about 2000 px wide
    if (!/^image\/(jpeg|png|webp)$/.test(file.type) || file.size < 1.5 * 1024 * 1024 || !window.createImageBitmap) {
      return Promise.resolve(file);
    }
    return createImageBitmap(file).then(function (bmp) {
      var k = Math.min(1, EDGE / Math.max(bmp.width, bmp.height));
      var c = document.createElement('canvas');
      c.width = Math.round(bmp.width * k); c.height = Math.round(bmp.height * k);
      c.getContext('2d').drawImage(bmp, 0, 0, c.width, c.height);
      return new Promise(function (resolve) {
        c.toBlob(function (b) { resolve(b && b.size < file.size ? new File([b], file.name.replace(/\.\w+$/, '') + '.jpg', { type: 'image/jpeg' }) : file); }, 'image/jpeg', 0.82);
      });
    }).catch(function () { return file; });
  }

  function send(box, file) {
    return shrink(file).then(function (f) {
      if (f.size > MAX) return { ok: false, error: file.name + ' is too large (over 6 MB). Paste a Google Drive link instead.' };
      return fetch(box.dataset.url + '?code=' + encodeURIComponent(box.dataset.code), {
        method: 'POST', credentials: 'same-origin', body: f,
        headers: { 'X-Filename': encodeURIComponent(file.name) }
      }).then(function (r) { return r.json(); }).catch(function () { return { ok: false, error: 'The upload did not go through. Check your connection and try again.' }; });
    });
  }

  function store(op, key, val) {                  // sessionStorage can be missing or full: the page works without it
    try {
      if (op === 'get') return window.sessionStorage.getItem(key);
      if (op === 'del') window.sessionStorage.removeItem(key); else window.sessionStorage.setItem(key, val);
    } catch (e) { /* ignore */ }
    return null;
  }

  function peso(n) { return '\u20b1' + Number(n).toLocaleString('en-PH', { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }

  function remember(box, j) {                     // keep a peso reading for the prepare page; returns a sentence or ''
    var r = j && j.reading;
    if (!r || !r.readable) return '';
    var what = [r.vendor, r.date].filter(Boolean).join(' \u00b7 ');
    if (r.currency !== 'PHP') return 'It shows ' + r.amount + ' ' + r.currency + ', not pesos, so it was not kept.';
    var key = 'tv-reads:' + box.dataset.ref, list = [];
    try { list = JSON.parse(store('get', key) || '[]'); } catch (e) { list = []; }
    var item = { code: box.dataset.code, label: box.dataset.label, amount: r.amount, date: r.date, origin: r.origin,
                 destination: r.destination, vendor: r.vendor, kind: r.kind };
    var same = list.some(function (x) { return x.code === item.code && x.amount === item.amount && x.date === item.date && x.vendor === item.vendor; });
    if (!same) list.push(item);
    store('set', key, JSON.stringify(list.slice(-30)));
    return 'Found ' + peso(r.amount) + (what ? ' (' + what + ')' : '') + '. Check it, then use it on the Prepare page.';
  }

  document.querySelectorAll('.tv-upload').forEach(function (box) {
    var pick = box.querySelector('input[type=file]'), out = box.querySelector('.tv-upload-out');
    var msgKey = 'tv-upload-msg:' + box.dataset.ref + ':' + box.dataset.code, kept = store('get', msgKey);
    if (kept) { out.textContent = kept; store('del', msgKey); }
    pick.addEventListener('change', function () {
      var files = Array.prototype.slice.call(pick.files || []);
      if (!files.length) return;
      pick.disabled = true;
      var done = 0, failed = '', notes = [];
      files.reduce(function (p, file, i) {
        return p.then(function () {
          out.textContent = 'Uploading ' + (i + 1) + ' of ' + files.length + '…';
          return send(box, file).then(function (j) {
            if (j.ok) { done++; var n = remember(box, j); if (n) notes.push(n); } else failed = failed || j.error || 'That file did not upload.';
          });
        });
      }, Promise.resolve()).then(function () {
        pick.disabled = false; pick.value = '';
        var saved = done + (done === 1 ? ' file' : ' files') + ' saved. ' + notes.join(' ');
        if (done && !failed) {
          store('set', msgKey, saved);
          if (store('get', msgKey)) { location.hash = '#item-' + box.dataset.code; location.reload(); return; }
          location.href = location.pathname + '?ok=' + encodeURIComponent(saved) + '#item-' + box.dataset.code; return;
        }
        out.textContent = (failed || 'Nothing was uploaded.') + (done ? ' (' + saved + ')' : '');
        if (done) { store('set', msgKey, out.textContent); setTimeout(function () { location.reload(); }, 3000); }
      });
    });
  });
})();
