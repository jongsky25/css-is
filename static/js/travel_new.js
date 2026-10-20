/* Keep the no-JavaScript form usable; progressively hide unrelated questions. */
(function () {
  'use strict';
  var form = document.querySelector('form[data-submission-status]');
  if (!form) return;
  function show(node, visible) {
    node.hidden = !visible;
    node.querySelectorAll('input, select').forEach(function (input) { input.disabled = !visible; });
  }
  function update() {
    var selected = form.querySelector('[name="kind"]:checked:not(:disabled)');
    var kind = selected ? selected.value : '';
    form.querySelectorAll('[data-claim-kinds]').forEach(function (node) {
      show(node, !!kind && node.dataset.claimKinds.split(' ').indexOf(kind) >= 0);
    });
    show(document.getElementById('liq-fields'), kind === 'liquidation');
    show(document.getElementById('external-advance'), kind === 'liquidation' && !form.elements.ca.value);
  }
  form.querySelectorAll('.tv-nojs-kinds').forEach(function (node) { node.hidden = true; });
  form.addEventListener('change', update);
  update();

  if (!window.fetch || !window.FormData || !window.URLSearchParams) return;
  var feedback = form.querySelector('[data-submission-feedback]');
  var message = form.querySelector('[data-submission-message]');
  var checkButton = form.querySelector('[data-check-submission]');
  var retryButton = form.querySelector('[data-retry-submission]');
  var statusLink = form.querySelector('[data-submission-link]');
  var submitButton = form.querySelector('button[type="submit"]');
  var label = submitButton.textContent;
  var pendingBody = null, busy = false, locked = [];
  checkButton.hidden = false;

  function setAttempt(key, statusUrl) {
    form.elements.operation_id.value = key;
    form.dataset.submissionStatus = statusUrl;
    statusLink.href = statusUrl;
    form.action = '/travel/new/' + encodeURIComponent(key);
    var pageUrl = new URL(window.location.href);
    pageUrl.pathname = '/travel/new/' + encodeURIComponent(key);
    pageUrl.searchParams.delete('operation');
    window.history.replaceState(null, '', pageUrl.href);
  }
  setAttempt(form.elements.operation_id.value, form.dataset.submissionStatus);

  function say(text) {
    feedback.hidden = false;
    message.textContent = text;
  }
  function lock() {
    locked = [];
    form.querySelectorAll('input, select, textarea').forEach(function (input) {
      if (!input.disabled) { locked.push(input); input.disabled = true; }
    });
    submitButton.disabled = true;
    submitButton.textContent = 'Opening your checklist…';
  }
  function unlock() {
    locked.forEach(function (input) { input.disabled = false; });
    locked = [];
    submitButton.disabled = false;
    submitButton.textContent = label;
    update();
  }
  function read(response) {
    if (response.redirected || !/application\/json/.test(response.headers.get('content-type') || '')) {
      throw new Error('No confirmed response');
    }
    return response.json();
  }
  function jsonRequest(url, options) {
    var controller = window.AbortController ? new AbortController() : null;
    var timer = null;
    if (controller) {
      options.signal = controller.signal;
      timer = setTimeout(function () { controller.abort(); }, 20000);
    }
    return fetch(url, options).then(read).finally(function () { clearTimeout(timer); });
  }
  function completed(result) {
    if (result.state !== 'completed') return false;
    retryButton.hidden = true;
    say(result.message);
    if (result.location && /^\/travel\/f\/TF-\d{4}-\d+$/.test(result.location)) {
      window.location.assign(result.location);
    }
    return true;
  }
  function check() {
    checkButton.disabled = true;
    return jsonRequest(form.dataset.submissionStatus, {credentials: 'same-origin', cache: 'no-store', headers: {Accept: 'application/json'}})
      .then(function (result) {
        if (!completed(result)) say(result.message || 'The result is not confirmed yet. Check again.');
        return result.state;
      }).catch(function () {
        say('The result could not be confirmed. Check your connection and sign-in, then check again before starting another filing.');
        return 'unknown';
      }).finally(function () { checkButton.disabled = false; });
  }
  function send() {
    busy = true;
    retryButton.hidden = true;
    say('Opening your checklist…');
    return jsonRequest(form.action, {method: 'POST', credentials: 'same-origin',
      headers: {'Content-Type': 'application/x-www-form-urlencoded', Accept: 'application/json'}, body: pendingBody})
      .then(function (result) {
        if (completed(result)) return;
        if (result.state === 'rejected' && result.operation_id && result.status_url) {
          unlock();
          setAttempt(result.operation_id, result.status_url);
          pendingBody = null;
          if (result.ack_required) {
            var ack = form.querySelector('[name="ack"]');
            if (!ack) { ack = document.createElement('input'); ack.type = 'hidden'; ack.name = 'ack'; form.appendChild(ack); }
            ack.value = '1';
            label = 'Continue anyway';
            submitButton.textContent = label;
            say(result.message + ' Accounting will not release a new advance while an old one is open. Select Continue anyway only if you want to proceed.');
          } else say(result.message);
          return;
        }
        retryButton.hidden = false;
        return check();
      }).catch(function () {
        retryButton.hidden = false;
        say('The connection was interrupted. Checking whether your filing was opened…');
        return check();
      }).finally(function () { busy = false; });
  }
  form.addEventListener('submit', function (event) {
    event.preventDefault();
    if (busy || pendingBody !== null) return;
    pendingBody = new URLSearchParams(new FormData(form)).toString();
    lock();
    send();
  });
  checkButton.addEventListener('click', function () { if (!busy) check(); });
  retryButton.addEventListener('click', function () {
    if (busy || pendingBody === null) return;
    busy = true;
    check().then(function (state) {
      if (state === 'ready' || state === 'pending' || state === 'rejected') return send();
    }).finally(function () { busy = false; });
  });
})();
