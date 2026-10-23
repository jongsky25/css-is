/* Read-only registry pilot. All data selection, filtering and ordering are server-side. */
(() => {
  'use strict';
  const panel = document.getElementById('registry-interactive');
  if (!panel || typeof window.Tabulator !== 'function') return;
  const controls = document.getElementById('registry-view-controls');
  const toggle = document.getElementById('registry-toggle');
  const standard = document.getElementById('registry-standard');
  const status = document.getElementById('registry-table-status');
  const filters = document.getElementById('registry-filters');
  const sort = document.getElementById('registry-sort');
  const element = document.getElementById('registry-grid');
  let table = null, controller = null, generation = 0;
  let applied = {status: '', verification: ''};

  function text(value) { return String(value ?? '').replaceAll('_', ' '); }
  function paragraph(parent, value, className) {
    const line = document.createElement('p');
    line.textContent = value;
    if (className) line.className = className;
    parent.append(line);
  }
  function link(cell) {
    const a = document.createElement('a');
    a.href = '/documents/' + Number(cell.getRow().getData().id);
    a.textContent = String(cell.getValue() ?? '');
    return a;
  }
  function plain(value) {
    const span = document.createElement('span');
    span.textContent = value;
    return span;
  }
  function subject(cell) {
    const row = cell.getRow().getData(), wrapper = document.createElement('div');
    wrapper.append(link(cell));
    if (row.gmail_imported) paragraph(wrapper, 'Imported from Gmail', 'doc-source');
    if (row.search_excerpt) paragraph(wrapper, row.search_source + ': ' + row.search_excerpt);
    return wrapper;
  }
  function workflow(cell) {
    const row = cell.getRow().getData(), wrapper = document.createElement('div');
    wrapper.textContent = text(cell.getValue());
    if (row.archived_at) paragraph(wrapper, 'Archived ' + row.archived_at);
    if (row.reconcile) paragraph(wrapper, 'Directive needs reconciliation');
    return wrapper;
  }
  function showStandard(message = '') {
    generation++;
    if (controller) controller.abort();
    panel.hidden = true;
    standard.hidden = false;
    toggle.textContent = 'Interactive table';
    toggle.setAttribute('aria-expanded', 'false');
    status.textContent = message;
    if (table) { table.destroy(); table = null; }
    element.replaceChildren();
  }
  async function request(url, config, params) {
    if (controller) controller.abort();
    controller = new AbortController();
    const active = controller, current = ++generation;
    const timer = setTimeout(() => active.abort(), 15000);
    const target = new URL(url, window.location.origin);
    const order = params.sort?.[0] || {field: 'registered', dir: 'desc'};
    target.searchParams.set('page', params.page || 1);
    target.searchParams.set('sort', order.field);
    target.searchParams.set('dir', order.dir);
    for (const [key, value] of Object.entries(applied)) target.searchParams.set(key, value);
    element.setAttribute('aria-busy', 'true');
    status.textContent = 'Loading matching documents…';
    try {
      const response = await fetch(target, {credentials: 'same-origin', cache: 'no-store',
        redirect: 'error', signal: active.signal, headers: {Accept: 'application/json'}});
      if (!response.ok || !response.headers.get('content-type')?.includes('application/json')) {
        throw new Error('Table request failed');
      }
      const data = await response.json();
      if (current !== generation) throw new Error('Superseded table request');
      if (!Array.isArray(data.data) || !Number.isInteger(data.last_row) || !Number.isInteger(data.last_page)) {
        throw new Error('Unexpected table response');
      }
      status.textContent = data.last_row ? `${data.last_row} matching records · page ${data.page} of ${data.last_page}.` : 'No matching documents.';
      return data;
    } catch (error) {
      if (current === generation) {
        // Leave no stale interactive rows on a failed refresh or expired session.
        setTimeout(() => {
          if (current === generation) showStandard('The interactive table could not load. The standard table is available; try again or reload the page.');
        }, 0);
      }
      throw error;
    } finally {
      clearTimeout(timer);
      if (current === generation) element.removeAttribute('aria-busy');
    }
  }
  function start() {
    panel.hidden = false;
    standard.hidden = true;
    toggle.textContent = 'Standard table';
    toggle.setAttribute('aria-expanded', 'true');
    try {
      table = new Tabulator(element, {
        layout: 'fitColumns', maxHeight: '65vh', renderVertical: 'basic', placeholder: 'No matching documents.',
        pagination: true, paginationMode: 'remote', paginationSize: 30, paginationButtonCount: 3,
        paginationOutOfRange: 'last', sortMode: 'remote', columnHeaderSortMulti: false,
        initialSort: [{column: 'registered', dir: 'desc'}], ajaxURL: panel.dataset.url,
        ajaxRequestFunc: request, dataLoaderError: 'Unable to load documents.',
        columns: [
          {title: 'Number', field: 'number', minWidth: 155, formatter: link},
          {title: 'Subject', field: 'subject', minWidth: 230, widthGrow: 3, variableHeight: true, formatter: subject},
          {title: 'Verification', field: 'verification', minWidth: 155,
            formatter: cell => plain(cell.getValue() === 'pending' ? 'Awaiting verification' : text(cell.getValue()))},
          {title: 'Workflow', field: 'status', minWidth: 160, variableHeight: true, formatter: workflow},
          {title: 'Due date', field: 'due_date', minWidth: 125, formatter: cell => plain(cell.getValue() || 'Unknown')},
          {title: 'Lead', field: 'lead', minWidth: 185, formatter: 'plaintext'},
          {title: 'Registered', field: 'registered', visible: false},
        ],
      });
      const choices = document.querySelector('.registry-column-choices');
      choices.replaceChildren();
      // Column chooser always retains the Number link, so records remain actionable.
      for (const [field, label] of [['subject', 'Subject'], ['verification', 'Verification'],
        ['status', 'Workflow'], ['due_date', 'Due date'], ['lead', 'Lead']]) {
        const option = document.createElement('label'), checkbox = document.createElement('input');
        checkbox.type = 'checkbox'; checkbox.checked = true;
        checkbox.addEventListener('change', () => table?.getColumn(field).toggle());
        option.append(checkbox, document.createTextNode(label)); choices.append(option);
      }
      table.on('dataSorted', () => {
        const order = table?.getSorters()[0];
        sort.value = order ? order.field + ':' + order.dir : 'registered:desc';
      });
    } catch (error) {
      showStandard('The interactive table is unavailable. You can continue using the standard table.');
    }
  }
  toggle.addEventListener('click', () => {
    if (table) showStandard();
    else { filters.reset(); applied = {status: '', verification: ''}; start(); }
  });
  filters.addEventListener('submit', event => {
    event.preventDefault();
    applied = {status: filters.elements.status.value, verification: filters.elements.verification.value};
    const [column, dir] = sort.value.split(':');
    table?.setSort(column, dir);
  });
  sort.addEventListener('change', () => {
    const [column, dir] = sort.value.split(':');
    table?.setSort(column, dir);
  });
  document.getElementById('registry-reset').addEventListener('click', () => {
    showStandard(); filters.reset(); applied = {status: '', verification: ''}; start();
  });
  controls.hidden = false;
})();
