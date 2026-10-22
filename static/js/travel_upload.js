// Travel checklist: upload files for a row. Each file is shrunk on the device when it is a big photo, sent to
// the server, and the server puts it in the office Drive. The page only ever shows the folder link.
// A ticket or receipt also comes back with the amount the AI read off it. The server keeps that small reading (never
// the file) and drafts the Appendix A entries from it on the prepare page, where the person checks each one.
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

  // One write per selected file. A lost response may follow a saved Drive upload;
  // ask the person to check the checklist rather than automatically replaying it.
  function why(status) {
    if (status === 403) return 'The server could not verify the request. Reload the page, sign in again if asked, and retry.';
    if (status === 401) return 'You were signed out. Sign in again, then retry.';
    if (status === 413) return 'That file is too large. Use one under 6 MB.';
    if (status === 429) return 'Too many tries. Wait a minute and retry.';
    if (status >= 500) return 'The server had a problem (code ' + status + '). Try again shortly, or paste a Google Drive link instead.';
    return 'The upload was refused (code ' + status + ').';
  }

  function post(url, f, name) {
    return fetch(url, { method: 'POST', credentials: 'same-origin', body: f, headers: { 'X-Filename': encodeURIComponent(name) } })
      .then(function (r) {
        return r.text().then(function (t) {
          var j = null; try { j = JSON.parse(t); } catch (e) { /* not JSON: a proxy or error page */ }
          if (r.status >= 500 || (r.ok && (!j || typeof j.ok !== 'boolean'))) return {ok:false, uncertain:true, error:'The upload result was not confirmed. Open the checklist and check the saved files before selecting them again.'};
          if (j && typeof j === 'object') return j;
          return { ok: false, error: why(r.status) };
        });
      }).catch(function () {
        return { ok: false, uncertain:true, error: 'The upload result was not confirmed. Check the saved files on the checklist before selecting them again.' };
      });
  }

  function send(box, file) {
    return shrink(file).then(function (f) {
      if (f.size > MAX) return { ok: false, error: file.name + ' is too large (over 6 MB). Paste a Google Drive link instead.' };
      return post(box.dataset.url + '?code=' + encodeURIComponent(box.dataset.code), f, file.name);
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

  // The DPO and the Certificate of Appearance come back already checked against the filing: show what does not
  // match, and offer to copy a DPO number / date the filing lacks into "Change my answers" (the person saves it).
  function checked(box, j) {
    if (j.fill) store('set', 'tv-upload-fill:' + box.dataset.ref, JSON.stringify(j.fill));
    return (j.checks || []).join(' ') || (j.reading && j.reading.readable ? 'Checked against this filing: nothing to flag.' : '');
  }

  function offerFill(box, out) {
    var raw = store('get', 'tv-upload-fill:' + box.dataset.ref), fill = null;
    try { fill = raw ? JSON.parse(raw) : null; } catch (e) { fill = null; }
    var no = document.getElementById('dpo_no'), dt = document.getElementById('dpo_date');
    if (!fill || !no || !dt) return;
    store('del', 'tv-upload-fill:' + box.dataset.ref);
    var b = document.createElement('button');
    b.type = 'button'; b.className = 'btn ghost small';
    b.textContent = 'Put the DPO ' + [fill.dpo_no, fill.dpo_date].filter(Boolean).join(' dated ') + ' in my answers';
    b.addEventListener('click', function () {
      if (fill.dpo_no) no.value = fill.dpo_no;
      if (fill.dpo_date) dt.value = fill.dpo_date;
      var d = no.closest('details'); if (d) d.open = true;
      no.scrollIntoView({ block: 'center' }); no.focus();
      b.remove();
    });
    out.appendChild(document.createTextNode(' ')); out.appendChild(b);
  }

  function remember(box, j) {                     // what the AI found, as a sentence ('' when nothing). The server keeps the reading.
    if (j && (j.doc === 'dpo' || j.doc === 'appearance')) return checked(box, j);
    var r = j && j.doc === 'receipt' ? j.reading : null;
    if (!r || !r.readable) return '';
    var what = [r.vendor, r.date].filter(Boolean).join(' \u00b7 ');
    if (r.currency !== 'PHP') return 'It shows ' + r.amount + ' ' + r.currency + ', not pesos, so it was not used.';
    return 'Found ' + peso(r.amount) + (what ? ' (' + what + ')' : '') + '. It will be drafted into your forms; check it there.';
  }

  document.querySelectorAll('.tv-upload').forEach(function (box) {
    var pick = box.querySelector('input[type=file]'), out = box.querySelector('.tv-upload-out');
    var msgKey = 'tv-upload-msg:' + box.dataset.ref + ':' + box.dataset.code, kept = store('get', msgKey);
    if (kept) { out.textContent = kept; store('del', msgKey); offerFill(box, out); }
    pick.addEventListener('change', function () {
      var files = Array.prototype.slice.call(pick.files || []);
      if (!files.length) return;
      pick.disabled = true;
      var done = 0, failed = '', notes = [], uncertain = false;
      files.reduce(function (p, file, i) {
        return p.then(function () {
          if (uncertain) return;
          out.textContent = 'Uploading ' + (i + 1) + ' of ' + files.length + '…';
          return send(box, file).then(function (j) {
            if (j.ok) { done++; var n = remember(box, j); if (n) notes.push(n); } else { failed = failed || j.error || 'That file did not upload.'; uncertain = !!j.uncertain; }
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
        if (uncertain) {
          var check = document.createElement('a'); check.href = location.pathname + '#item-' + box.dataset.code;
          check.className = 'btn ghost small'; check.textContent = 'Check saved files';
          check.addEventListener('click', function (event) { event.preventDefault(); location.hash = '#item-' + box.dataset.code; location.reload(); });
          out.appendChild(document.createTextNode(' ')); out.appendChild(check); return;
        }
        if (done) { store('set', msgKey, out.textContent); setTimeout(function () { location.reload(); }, 3000); }
      });
    });
  });
})();
