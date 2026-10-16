/* Upgrade sharing controls when the saved short link is ready. Originals remain usable. */
(() => {
  const groups = new Map();
  document.querySelectorAll('[data-short-link]').forEach(node => {
    const url = node.dataset.shortLink;
    if (!groups.has(url)) groups.set(url, []);
    groups.get(url).push(node);
  });
  if (!groups.size) return;
  const notices = new Map();
  for (const nodes of groups.values()) nodes.forEach(node => {
    const notice = document.createElement('p');
    notice.className = 'hint noprint';
    notice.setAttribute('role', 'status');
    notice.setAttribute('aria-live', 'polite');
    node.appendChild(notice);
    notices.set(node, notice);
  });
  function message(nodes, text) {
    nodes.forEach(node => { notices.get(node).textContent = text; });
  }
  let rounds = 0;
  async function refresh() {
    if (document.hidden) { setTimeout(refresh, 15000); return; }
    for (const [original, nodes] of groups) {
      try {
        const response = await fetch('/short-links/status?url=' + encodeURIComponent(original));
        if (!response.ok || !response.headers.get('content-type')?.includes('application/json')) {
          message(nodes, 'Could not check the short link. Reopen this page to try again, or use the original link.');
          groups.delete(original);
          continue;
        }
        const result = await response.json();
        let note = result.message || '';
        if (result.retry_after_seconds > 0) {
          note += ' Next attempt in about ' + Math.ceil(result.retry_after_seconds / 60) + ' minute(s).';
        }
        message(nodes, note);
        if (result.url) nodes.forEach(node => {
          node.querySelectorAll('[data-short-text]').forEach(el => { el.textContent = result.url; });
          node.querySelectorAll('[data-short-href]').forEach(el => { el.href = result.url; });
          node.querySelectorAll('[data-short-qr]').forEach(el => { el.src = result.qr; });
          node.querySelectorAll('[data-short-download]').forEach(el => { el.href = result.qr; });
        });
        if (result.done) groups.delete(original);
      } catch (_) {
        message(nodes, 'Could not check the short link. You can use the original link now.');
      }
    }
    if (groups.size && ++rounds < 40) setTimeout(refresh, 15000);
    else if (groups.size) {
      for (const nodes of groups.values()) message(nodes,
        'A short link is not ready yet. Use the original link or reopen this page later to check again.');
    }
  }
  refresh();
})();
