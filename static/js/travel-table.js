/* Optional read-only enhancement; all filtering/order/ownership stays on the server. */
(() => {
  'use strict';
  const panel = document.getElementById('claims-interactive');
  const toggle = document.getElementById('claims-toggle');
  if (!panel || !toggle || typeof Tabulator !== 'function') return;
  const native = document.getElementById('claims-native');
  const status = document.getElementById('claims-status');
  const standard = document.getElementById('claims-standard-link');
  let table, generation = 0, controller;
  toggle.hidden = false;
  function fallback(message) {
    generation++;
    controller?.abort();
    panel.hidden = true; native.hidden = false;
    toggle.setAttribute('aria-expanded', 'false');
    toggle.textContent = 'Open interactive table';
    status.textContent = message;
  }
  toggle.addEventListener('click', () => {
    if (!panel.hidden) { fallback('Standard table shown in its original selection and page.'); return; }
    panel.hidden = false; native.hidden = true;
    toggle.setAttribute('aria-expanded', 'true'); toggle.textContent = 'Show standard table';
    if (table) { table.destroy(); table = null; }
    try {
      table = new Tabulator('#claims-grid', {
        layout: 'fitDataStretch', maxHeight: '65vh', renderVertical: 'basic',
        placeholder: 'No matching filings.', pagination: true, paginationMode: 'remote',
        paginationSize: 30, paginationButtonCount: 3, paginationInitialPage: Number(panel.dataset.page),
        paginationOutOfRange: 'last', ajaxURL: panel.dataset.url,
        columnDefaults: {headerSort: false, formatter: 'plaintext', minWidth: 140, variableHeight: true},
        ajaxRequestFunc: async (_url, _config, params) => {
          const current = ++generation;
          controller?.abort();
          controller = typeof AbortController === 'function' ? new AbortController() : null;
          const url = new URL(panel.dataset.url, location.origin);
          url.searchParams.set('page', String(params.page || 1));
          const plain = new URL(url); plain.searchParams.delete('format');
          standard.href = plain.pathname + plain.search;
          status.textContent = 'Loading your filings…';
          try {
            const response = await fetch(url, {credentials: 'same-origin', cache: 'no-store', signal: controller?.signal});
            if (!response.ok || !response.headers.get('Content-Type')?.includes('application/json')) throw Error('unavailable');
            const result = await response.json();
            if (current !== generation) throw Error('superseded');
            if (!Array.isArray(result.data) || !Number.isInteger(result.total) || !Number.isInteger(result.page)) throw Error('invalid response');
            status.textContent = `${result.total} matching filings. Interactive page ${result.page} of ${result.last_page}.`;
            return result;
          } catch (error) {
            if (current === generation) fallback('Interactive table unavailable. The original standard page is shown; use “Reload this selection as a standard table” for the requested page.');
            throw error;
          }
        },
        columns: [
          {title: 'Reference', field: 'ref_code', formatter: cell => {
            const link = document.createElement('a');
            link.textContent = String(cell.getValue() || '');
            // Build the destination from the reference, never arbitrary server HTML or URLs.
            link.href = '/travel/f/' + encodeURIComponent(cell.getValue());
            return link;
          }},
          {title: 'Claim type', field: 'kind'}, {title: 'Activity', field: 'act_title', minWidth: 240},
          {title: 'Recorded start', field: 'act_start'}, {title: 'Recorded end', field: 'act_end'},
          {title: 'Filing status', field: 'status'},
        ],
      });
    } catch (_error) { fallback('Interactive table unavailable. Continue with the standard table.'); }
  });
})();
