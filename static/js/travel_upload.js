// Travel checklist: upload files for a row. Each file is shrunk on the device when it is a big photo, sent to
// the server, and the server puts it in the office Drive. The page only ever shows the folder link.
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

  document.querySelectorAll('.tv-upload').forEach(function (box) {
    var pick = box.querySelector('input[type=file]'), out = box.querySelector('.tv-upload-out');
    pick.addEventListener('change', function () {
      var files = Array.prototype.slice.call(pick.files || []);
      if (!files.length) return;
      pick.disabled = true;
      var done = 0, failed = '';
      files.reduce(function (p, file, i) {
        return p.then(function () {
          out.textContent = 'Uploading ' + (i + 1) + ' of ' + files.length + '…';
          return send(box, file).then(function (j) { if (j.ok) done++; else failed = failed || j.error || 'That file did not upload.'; });
        });
      }, Promise.resolve()).then(function () {
        pick.disabled = false; pick.value = '';
        if (done && !failed) { location.href = location.pathname + '?ok=' + encodeURIComponent(done + (done === 1 ? ' file' : ' files') + ' saved.') + '#item-' + box.dataset.code; return; }
        out.textContent = (failed || 'Nothing was uploaded.') + (done ? ' (' + done + ' saved.)' : '');
        if (done) setTimeout(function () { location.reload(); }, 2500);
      });
    });
  });
})();
