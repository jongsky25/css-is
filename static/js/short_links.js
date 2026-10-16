/* Upgrade sharing controls when the saved short link is ready. Originals remain usable. */
(() => {
  const groups = new Map();
  document.querySelectorAll('[data-short-link]').forEach(node => {
    const url = node.dataset.shortLink;
    if (!groups.has(url)) groups.set(url, []);
    groups.get(url).push(node);
  });
  if (!groups.size) return;
  let rounds = 0;
  async function refresh() {
    if (document.hidden) { setTimeout(refresh, 15000); return; }
    for (const [original, nodes] of groups) {
      try {
        const response = await fetch('/short-links/status?url=' + encodeURIComponent(original));
        if (!response.ok || !response.headers.get('content-type')?.includes('application/json')) {
          groups.delete(original);
          continue;
        }
        const result = await response.json();
        if (result.url) nodes.forEach(node => {
          node.querySelectorAll('[data-short-text]').forEach(el => { el.textContent = result.url; });
          node.querySelectorAll('[data-short-href]').forEach(el => { el.href = result.url; });
          node.querySelectorAll('[data-short-qr]').forEach(el => { el.src = result.qr; });
          node.querySelectorAll('[data-short-download]').forEach(el => { el.href = result.qr; });
        });
        if (result.done) groups.delete(original);
      } catch (_) { /* Keep the usable original until a later attempt. */ }
    }
    if (groups.size && ++rounds < 40) setTimeout(refresh, 15000);
  }
  refresh();
})();
