/* Review is local and read-only. Only the final submit uses the existing send route. */
(function () {
  'use strict';
  var form = document.querySelector('[data-notice-form]');
  if (!form) return;
  var preview = form.querySelector('[data-notice-preview]');
  var review = form.querySelector('[data-notice-review]');
  var edit = form.querySelector('[data-notice-edit]');
  var send = form.querySelector('[data-notice-send]');
  var agenda = form.elements.agenda;
  var extra = form.elements.extra;
  var reviewed = false;
  function reset() {
    reviewed = false;
    preview.hidden = true;
    review.hidden = false;
  }
  agenda.addEventListener('input', reset);
  extra.addEventListener('input', function () { extra.setCustomValidity(''); reset(); });
  edit.addEventListener('click', function () { reset(); agenda.focus(); });
  form.addEventListener('submit', function (event) {
    if (reviewed && event.submitter === send) {
      send.disabled = true;
      send.textContent = 'Sending…';
      form.setAttribute('aria-busy', 'true');
      return;
    }
    event.preventDefault();
    var addresses = extra.value.split(/[\n,;]+/).map(function (v) { return v.trim(); }).filter(Boolean);
    var invalid = addresses.find(function (v) { return !/^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$/.test(v) || v.length > 120; });
    var unique = Array.from(new Set(addresses.map(function (v) { return v.toLowerCase(); })));
    extra.setCustomValidity(invalid ? 'Enter valid email addresses, one per line.' : unique.length > 20 ? 'Add at most 20 extra addresses.' : '');
    if (!form.reportValidity()) return;
    preview.querySelector('[data-review-agenda]').textContent = agenda.value.replace(/\r/g, '').split('\n').map(function (v) { return v.trim().replace(/\s+/g, ' '); }).filter(Boolean).join('\n') || 'No agenda added.';
    preview.querySelector('[data-review-extra]').textContent = unique.length ? 'Additional recipients:\n' + unique.join('\n') : 'No additional recipients.';
    reviewed = true;
    preview.hidden = false;
    review.hidden = true;
    preview.focus();
  });
})();
