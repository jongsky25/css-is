/* One immutable attempt per form. Only result checks are automatic. */
(() => {
  const form = document.getElementById('intake-form');
  const feedback = document.getElementById('registration-feedback');
  if (!form || !feedback || !form.elements.submission_id?.value || !window.fetch) return;
  const status = document.getElementById('registration-status');
  const check = document.getElementById('registration-check');
  const retry = document.getElementById('registration-retry');
  const link = document.getElementById('registration-result');
  const endpoint = '/documents/registrations/' + encodeURIComponent(form.elements.submission_id.value);
  let snapshot = null, busy = false, saved = false, controls = [];
  function announce(message) {
    feedback.hidden = false;
    status.textContent = message;
    status.focus({preventScroll: true});
    status.scrollIntoView({block: 'nearest'});
  }
  function lock() {
    if (controls.length) return;
    controls = [...form.querySelectorAll('input,select,textarea,button')]
      .filter(element => element !== check && element !== retry)
      .map(element => [element, element.disabled]);
    for (const [element] of controls) element.disabled = true;
  }
  function unlock() {
    for (const [element, disabled] of controls) element.disabled = disabled;
    controls = [];
  }
  function working(value) {
    busy = value;
    check.disabled = retry.disabled = value;
    status.setAttribute('aria-busy', String(value));
  }
  async function request(url, options, seconds) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), seconds * 1000);
    try {
      const response = await fetch(url, {...options, credentials: 'same-origin',
        headers: {Accept: 'application/json'}, signal: controller.signal});
      if (response.redirected || !response.headers.get('content-type')?.includes('application/json')) throw new Error('unconfirmed');
      return {response, data: await response.json()};
    } finally { clearTimeout(timer); }
  }
  function success(data, {conflict = false} = {}) {
    if (data.state !== 'saved' || typeof data.url !== 'string' || typeof data.number !== 'string') throw new Error('unconfirmed');
    const url = new URL(data.url, window.location.origin);
    if (url.origin !== window.location.origin || !/^\/(documents|work)\/[1-9]\d*$/.test(url.pathname) || url.search || url.hash) throw new Error('unconfirmed');
    saved = true;
    retry.hidden = check.hidden = true;
    link.href = url.href;
    link.hidden = false;
    announce(conflict ? 'Already saved as ' + data.number + '. These changed details have not been applied. Open the saved record to review it.'
      : 'Saved as ' + data.number + '. Opening the saved record…');
    if (!conflict) window.location.assign(url.href);
  }
  async function checkResult(options = {}) {
    announce('Checking whether this registration was saved…');
    try {
      const {response, data} = await request(endpoint, {method: 'GET', cache: 'no-store'}, 10);
      if (response.ok && data.state === 'saved') { success(data, options); return; }
      if (data.state === 'unavailable') {
        announce('The saved result is unavailable to this account. Sign in again if needed, then check your document register before starting another registration.');
        return;
      }
    } catch { /* An interrupted check never authorizes another business write. */ }
    retry.hidden = !snapshot;
    announce('Save not confirmed. It may still be processing. Check again or retry this same submission. Your entered details are kept on this page.');
  }
  async function send() {
    if (busy || saved || !snapshot) return;
    working(true);
    lock();
    retry.hidden = true;
    announce('Saving correspondence. Keep this page open…');
    try {
      const {response, data} = await request(form.action, {method: 'POST', body: new URLSearchParams(snapshot)}, 30);
      if (response.ok && data.state === 'saved') success(data);
      else if (response.status === 400 && data.state === 'invalid') {
        snapshot = null;
        unlock();
        announce(data.error || 'Check the entered fields and submit again.');
      } else await checkResult({conflict: data.state === 'conflict'});
    } catch { await checkResult(); }
    finally { working(false); }
  }
  form.addEventListener('submit', event => {
    // Existing field approval and PDF-reading guards run first.
    if (event.defaultPrevented) return;
    event.preventDefault();
    if (busy || saved || snapshot) return;
    snapshot = new URLSearchParams(new FormData(form)).toString();
    send();
  });
  check.addEventListener('click', async () => {
    if (busy || saved) return;
    working(true);
    try { await checkResult(); } finally { working(false); }
  });
  retry.addEventListener('click', send);
})();
