// Share an issued advisory to a group chat (docs/ADVISORY_SLIDES_PLAN.md, Share button).
// Phones: the system share sheet with the image and the message. Elsewhere: copy the message and
// download the image. Without JavaScript the Download link and the readonly message still work.
(function () {
  var box = document.querySelector('[data-advisory-share]');
  if (!box) return;
  var shareBtn = box.querySelector('[data-share-button]');
  var copyBtn = box.querySelector('[data-copy-button]');
  var caption = box.querySelector('#share-caption');
  var status = box.querySelector('[data-share-status]');
  function say(text) { if (status) status.textContent = text; }

  if (navigator.clipboard && copyBtn) {
    copyBtn.hidden = false;
    copyBtn.addEventListener('click', function () {
      navigator.clipboard.writeText(caption.value).then(function () { say('Message copied. Paste it in the chat.'); },
        function () { caption.select(); say('Select the message and copy it.'); });
    });
  }
  if (!navigator.share || !shareBtn) return;
  shareBtn.hidden = false;
  shareBtn.addEventListener('click', function () {
    say('Opening the share menu…');
    fetch(box.getAttribute('data-image'), { credentials: 'same-origin' })
      .then(function (r) { if (!r.ok) throw new Error('image'); return r.blob(); })
      .then(function (blob) {
        var file = new File([blob], box.getAttribute('data-filename') || 'advisory.png', { type: 'image/png' });
        var data = { files: [file], text: caption.value };
        if (navigator.canShare && !navigator.canShare(data)) data = { text: caption.value };
        return navigator.share(data);
      })
      .then(function () { say(''); })
      .catch(function (err) {
        if (err && err.name === 'AbortError') { say(''); return; }
        say('This phone could not share the picture directly. Use Download image and Copy message instead.');
      });
  });
})();
