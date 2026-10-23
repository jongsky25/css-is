/* Registry table and personal saved views. Record selection stays server-side. */
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
  const viewSelect = document.getElementById('registry-saved-view');
  const viewName = document.getElementById('registry-view-name');
  const viewStatus = document.getElementById('registry-view-status');
  const viewForm = document.getElementById('registry-save-view');
  const fields = ['number', 'subject', 'verification', 'status', 'due_date', 'lead'];
  let savedViews = null, loadingViews = null, saving = false;
  let table = null, controller = null, generation = 0;
  let applied = {status: '', verification: '', deadline: ''};

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
  function deadline(cell) {
    const row = cell.getRow().getData(), wrapper = document.createElement('div');
    wrapper.textContent = cell.getValue() || (row.deadline_label ? '' : 'Unknown');
    if (row.deadline_label) {
      const badge = document.createElement('span');
      badge.className = 'registry-deadline';
      badge.dataset.deadline = row.deadline_state;
      badge.textContent = row.deadline_label;
      if (wrapper.textContent) wrapper.append(document.createElement('br'));
      wrapper.append(badge);
    }
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
  function start(saved = null) {
    panel.hidden = false;
    standard.hidden = true;
    toggle.textContent = 'Standard table';
    toggle.setAttribute('aria-expanded', 'true');
    try {
      table = new Tabulator(element, {
        layout: 'fitColumns', maxHeight: '65vh', renderVertical: 'basic', placeholder: 'No matching documents.',
        pagination: true, paginationMode: 'remote', paginationSize: 30, paginationButtonCount: 3,
        paginationOutOfRange: 'last', sortMode: 'remote', columnHeaderSortMulti: false,
        initialSort: [{column: saved?.sort || 'registered', dir: saved?.dir || 'desc'}], ajaxURL: panel.dataset.url,
        ajaxRequestFunc: request, dataLoaderError: 'Unable to load documents.',
        columns: [
          {title: 'Number', field: 'number', minWidth: 155, formatter: link},
          {title: 'Subject', field: 'subject', minWidth: 230, widthGrow: 3, variableHeight: true, formatter: subject},
          {title: 'Verification', field: 'verification', minWidth: 155,
            formatter: cell => plain(cell.getValue() === 'pending' ? 'Awaiting verification' : text(cell.getValue()))},
          {title: 'Workflow', field: 'status', minWidth: 160, variableHeight: true, formatter: workflow},
          {title: 'Due date', field: 'due_date', minWidth: 125, variableHeight: true, formatter: deadline},
          {title: 'Lead', field: 'lead', minWidth: 185, formatter: 'plaintext'},
          {title: 'Registered', field: 'registered', visible: false},
        ].map(column => ({...column, ...(saved?.columns[column.field] || {})})),
      });
      const choices = document.querySelector('.registry-column-choices');
      choices.replaceChildren();
      // Column chooser always retains the Number link, so records remain actionable.
      for (const [field, label] of [['subject', 'Subject'], ['verification', 'Verification'],
        ['status', 'Workflow'], ['due_date', 'Due date'], ['lead', 'Lead']]) {
        const option = document.createElement('label'), checkbox = document.createElement('input');
        checkbox.type = 'checkbox'; checkbox.checked = saved?.columns[field]?.visible ?? true;
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
    else { resetSelection(); filters.reset(); applied = {status: '', verification: '', deadline: ''}; start(); loadViews().catch(viewError); }
  });
  filters.addEventListener('submit', event => {
    event.preventDefault();
    applied = {status: filters.elements.status.value, verification: filters.elements.verification.value,
      deadline: filters.elements.deadline.value};
    const [column, dir] = sort.value.split(':');
    table?.setSort(column, dir);
  });
  sort.addEventListener('change', () => {
    const [column, dir] = sort.value.split(':');
    table?.setSort(column, dir);
  });
  document.getElementById('registry-reset').addEventListener('click', () => {
    showStandard(); resetSelection(); filters.reset(); applied = {status: '', verification: '', deadline: ''}; start();
  });

  function selectedView() { return savedViews?.find(view => String(view.id) === viewSelect.value); }
  function viewError(error) { viewStatus.textContent = error.message || 'Saved views are unavailable. Reload the page and try again.'; }
  function viewURL(view) {
    const url = new URL('/documents', window.location.origin);
    url.searchParams.set('queue', view.state.queue);
    url.searchParams.set('q', view.state.q);
    url.searchParams.set('saved_view', view.id);
    return url;
  }
  function resetSelection() {
    viewSelect.value = ''; viewName.value = ''; viewStatus.textContent = '';
    const url = new URL(window.location.href);
    url.searchParams.delete('saved_view');
    history.replaceState(null, '', url);
    updateViewButtons();
  }
  function updateViewButtons() {
    const selected = Boolean(selectedView());
    document.getElementById('registry-open-view').disabled = saving || !selected;
    document.getElementById('registry-update-view').disabled = saving || !selected;
    document.getElementById('registry-delete-view').disabled = saving || !selected;
    document.getElementById('registry-create-view').disabled = saving || !savedViews;
    viewSelect.disabled = saving;
    viewName.disabled = saving;
  }
  function renderViews(selected = viewSelect.value) {
    viewSelect.replaceChildren(new Option('Choose a saved view', ''));
    for (const view of savedViews) viewSelect.append(new Option(view.name, String(view.id)));
    viewSelect.value = selected || '';
    viewName.value = selectedView()?.name || '';
    updateViewButtons();
  }
  async function jsonRequest(url, options = {}) {
    const response = await fetch(url, {credentials: 'same-origin', cache: 'no-store', redirect: 'error',
      signal: AbortSignal.timeout(15000), ...options});
    if (!response.headers.get('content-type')?.includes('application/json')) throw new Error('Saved views could not load. Reload the page and try again.');
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'The saved view could not be changed.');
    if (!Array.isArray(data.views)) throw new Error('Unexpected saved views response. Reload the page.');
    return data;
  }
  async function loadViews() {
    if (savedViews) return savedViews;
    if (!loadingViews) loadingViews = jsonRequest('/documents/grid-views')
      .then(data => { savedViews = data.views; renderViews(); return savedViews; })
      .finally(() => { loadingViews = null; });
    return loadingViews;
  }
  function currentState() {
    const scope = new URL(panel.dataset.url, window.location.origin).searchParams;
    const order = table.getSorters()[0] || {field: 'registered', dir: 'desc'};
    const columns = {};
    for (const field of fields) {
      const column = table.getColumn(field), width = column.getWidth();
      columns[field] = {visible: column.isVisible()};
      if (Number.isFinite(width) && width >= 75) columns[field].width = Math.round(width);
    }
    return {schema: 1, queue: scope.get('queue') || 'all', q: scope.get('q') || '',
      ...applied, sort: order.field, dir: order.dir, columns};
  }
  async function changeView(action) {
    if (saving || !table) return;
    const selected = selectedView();
    if (action !== 'create' && !selected) return;
    const data = {action};
    if (selected && action !== 'create') Object.assign(data, {id: selected.id, revision: selected.revision});
    if (action !== 'delete') Object.assign(data, {name: viewName.value, state: currentState()});
    saving = true; updateViewButtons(); viewStatus.textContent = 'Saving view…';
    try {
      const result = await jsonRequest('/documents/grid-views', {method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-CSRF-Token': panel.dataset.csrf}, body: JSON.stringify(data)});
      savedViews = result.views;
      renderViews(result.saved_id ? String(result.saved_id) : '');
      if (result.saved_id) history.replaceState(null, '', viewURL(selectedView()));
      else resetSelection();
      viewStatus.textContent = action === 'delete' ? 'Saved view deleted. The current table is unchanged.' : 'View saved to your account.';
    } catch (error) { viewError(error); }
    finally { saving = false; updateViewButtons(); }
  }
  viewSelect.addEventListener('change', () => { viewName.value = selectedView()?.name || ''; updateViewButtons(); });
  document.getElementById('registry-open-view').addEventListener('click', () => {
    const view = selectedView();
    if (view) window.location.assign(viewURL(view));
  });
  viewForm.addEventListener('submit', event => { event.preventDefault(); changeView('create'); });
  document.getElementById('registry-update-view').addEventListener('click', () => changeView('update'));
  document.getElementById('registry-delete-view').addEventListener('click', () => changeView('delete'));
  controls.hidden = false;
  const requested = new URL(window.location.href).searchParams.get('saved_view');
  if (requested) loadViews().then(views => {
    const view = views.find(item => String(item.id) === requested);
    if (!view) throw new Error('Saved view not found or unavailable to you. Open the interactive table to choose another.');
    const scope = new URL(panel.dataset.url, window.location.origin).searchParams;
    if ((scope.get('queue') || 'all') !== view.state.queue || (scope.get('q') || '') !== view.state.q) {
      window.location.replace(viewURL(view)); return;
    }
    renderViews(requested);
    applied = {status: view.state.status, verification: view.state.verification, deadline: view.state.deadline || ''};
    for (const [field, value] of Object.entries(applied)) filters.elements[field].value = value;
    sort.value = view.state.sort + ':' + view.state.dir;
    start(view.state);
  }).catch(error => { status.textContent = error.message; });
})();
