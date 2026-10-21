// Calendar item, "Another office": keep the invitation or letter in Drive and offer what the AI read from it.
// The file is shrunk on the device when it is a big photo, sent once, and kept in the office Drive; the page only
// shows the link. The reading is a SUGGESTION: it fills nothing until the person presses "Use these", and nothing is
// saved until they press Save.
(function () {
  'use strict';
  var MAX = 6 * 1024 * 1024, EDGE = 2000;
  var box = document.querySelector('[data-invitation-upload]');
  if (!box) return;
  var input = box.querySelector('input[type=file]'), status = box.querySelector('[data-status]'),
      offer = box.querySelector('[data-offer]'), form = document.querySelector('form.cal-outside');

  function say(text, bad) { status.textContent = text; status.className = 'cal-hint' + (bad ? ' cal-doc-error' : ''); }

  function shrink(file) {
    if (!/^image\/(jpeg|png|webp)$/.test(file.type) || file.size < 1.5 * 1024 * 1024 || !window.createImageBitmap) {
      return Promise.resolve(file);
    }
    return createImageBitmap(file).then(function (bmp) {
      var k = Math.min(1, EDGE / Math.max(bmp.width, bmp.height)), c = document.createElement('canvas');
      c.width = Math.round(bmp.width * k); c.height = Math.round(bmp.height * k);
      c.getContext('2d').drawImage(bmp, 0, 0, c.width, c.height);
      return new Promise(function (resolve) {
        c.toBlob(function (b) { resolve(b && b.size < file.size ? new File([b], file.name.replace(/\.\w+$/, '') + '.jpg', { type: 'image/jpeg' }) : file); }, 'image/jpeg', 0.82);
      });
    }).catch(function () { return file; });
  }

  function why(status) {
    if (status === 403) return 'The server could not verify the request. Reload the page and retry.';
    if (status === 401) return 'You were signed out. Sign in again, then retry.';
    if (status === 413) return 'That file is too large. Use one under 6 MB.';
    if (status === 429) return 'Too many tries. Wait a minute and retry.';
    return 'The upload was refused (code ' + status + ').';
  }

  function post(file) {
    return fetch(box.dataset.url, { method: 'POST', credentials: 'same-origin', body: file,
                                    headers: { 'X-Filename': encodeURIComponent(file.name) } })
      .then(function (r) {
        return r.text().then(function (t) {
          var j = null; try { j = JSON.parse(t); } catch (e) { /* an error page */ }
          return j && typeof j === 'object' ? j : { ok: false, error: why(r.status) };
        });
      }, function () { return { ok: false, error: 'The upload did not go through. Check your connection and try again.' }; });
  }

  function field(name) { return form ? form.elements[name] : null; }
  var INVITED = { resource_person: 'resource person', attendee: 'participant' };

  function show(reading) {
    offer.textContent = '';
    if (!reading || !reading.readable) { return; }
    var p = document.createElement('p'); p.className = 'cal-hint';
    p.textContent = 'Read from the letter (check it before using): ' +
      [reading.host && 'from ' + reading.host, reading.invited_as && 'invited as ' + INVITED[reading.invited_as],
       reading.key_lines && '“' + reading.key_lines + '”', reading.note].filter(Boolean).join(' — ');
    var b = document.createElement('button'); b.type = 'button'; b.className = 'cal-btn'; b.textContent = 'Use these';
    b.addEventListener('click', function () {
      if (reading.host && field('host')) field('host').value = reading.host;
      if (reading.invited_as && field('invited_as')) field('invited_as').value = reading.invited_as;
      if (reading.key_lines && field('invitation')) field('invitation').value = reading.key_lines;
      say('Filled in. Read it, change what is wrong, then press Save.');
    });
    offer.appendChild(p); offer.appendChild(b);
  }

  input.addEventListener('change', function () {
    var file = input.files && input.files[0];
    if (!file) return;
    offer.textContent = '';
    say('Sending the letter…');
    shrink(file).then(function (f) {
      if (f.size > MAX) return { ok: false, error: file.name + ' is too large (over 6 MB).' };
      return post(f);
    }).then(function (j) {
      input.value = '';
      if (!j.ok) { say(j.error || 'The letter could not be kept.', true); return; }
      var link = box.querySelector('[data-link]');
      link.href = j.url; link.textContent = j.name; link.hidden = false;
      if (j.reading && j.reading.readable) say('The letter is kept. Review what was read from it below.');
      else say(j.ai_off ? 'The letter is kept. Reading it is switched off or used up for now; type the key lines instead.'
                        : 'The letter is kept, but it could not be read. Type the key lines instead.');
      show(j.reading);
    });
  });
})();
