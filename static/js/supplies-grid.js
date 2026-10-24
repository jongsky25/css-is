/* Supplies inventory and personal saved views. Record selection stays server-side. */
(() => {
  'use strict';
  const panel = document.getElementById('inventory-interactive');
  if (!panel || typeof window.Tabulator !== 'function') return;
  const controls = document.getElementById('inventory-view-controls');
  const toggle = document.getElementById('inventory-toggle');
  const standard = document.getElementById('inventory-standard');
  const status = document.getElementById('inventory-table-status');
  const filters = document.getElementById('inventory-filters');
  const sort = document.getElementById('inventory-sort');
  const element = document.getElementById('inventory-grid');
  const viewSelect = document.getElementById('inventory-saved-view');
  const viewName = document.getElementById('inventory-view-name');
  const viewStatus = document.getElementById('inventory-view-status');
  const viewForm = document.getElementById('inventory-save-view');
  const exportButton = document.getElementById('inventory-export');
  const exportStatus = document.getElementById('inventory-export-status');
  let exportReady = false, exporting = false;
  const fields = ['code', 'description', 'unit', 'on_hand', 'reserved', 'available', 'critical_level', 'target_level', 'physical', 'availability', 'active'];
  let savedViews = null, loadingViews = null, saving = false;
  let table = null, controller = null, generation = 0;
  const filterFields = ['q', 'unit', 'physical', 'availability', 'active'];
  const defaultFilters = () => Object.fromEntries(filterFields.map(field => [field, field === 'active' ? (panel.dataset.inactive === '1' ? 'all' : 'active') : field === 'q' ? panel.dataset.query : '']));
  let applied = defaultFilters();

  function link(cell) {
    const a = document.createElement('a');
    a.href = '/supplies/items/' + encodeURIComponent(cell.getRow().getData().id);
    a.textContent = String(cell.getValue() ?? '');
    return a;
  }
  function plain(value) {
    const span = document.createElement('span');
    span.textContent = value;
    return span;
  }
  const labels = {unrecorded:'Stock not recorded', inactive:'Inactive', out_of_stock:'Out of stock',
    critical:'Critical', normal:'Normal', fully_reserved:'Fully reserved', low_available:'Low available', available:'Available'};
  function quantity(cell) { return plain(cell.getValue() ?? (cell.getField() === 'target_level' ? 'Not set' : 'Not recorded')); }
  function showStandard(message = '') {
    generation++;
    exportReady = false; updateExportButton();
    if (controller) controller.abort();
    panel.hidden = true;
    standard.hidden = false;
    toggle.textContent = 'Interactive inventory';
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
    const order = params.sort?.[0] || {field: 'code', dir: 'asc'};
    target.searchParams.set('page', params.page || 1);
    target.searchParams.set('sort', order.field);
    target.searchParams.set('dir', order.dir);
    for (const [key, value] of Object.entries(applied)) target.searchParams.set(key, value);
    exportReady = false; updateExportButton();
    element.setAttribute('aria-busy', 'true');
    status.textContent = 'Loading matching items…';
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
      status.textContent = data.last_row ? `${data.last_row} matching records · page ${data.page} of ${data.last_page}.` : 'No matching items.';
      exportReady = true;
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
      if (current === generation) { element.removeAttribute('aria-busy'); updateExportButton(); }
    }
  }
  function start(saved = null) {
    panel.hidden = false;
    standard.hidden = true;
    toggle.textContent = 'Standard table';
    toggle.setAttribute('aria-expanded', 'true');
    try {
      table = new Tabulator(element, {
        layout: 'fitColumns', maxHeight: '65vh', renderVertical: 'basic', placeholder: 'No matching items.',
        pagination: true, paginationMode: 'remote', paginationSize: 30, paginationButtonCount: 3,
        paginationOutOfRange: 'last', sortMode: 'remote', columnHeaderSortMulti: false,
        initialSort: [{column: saved?.sort || 'code', dir: saved?.dir || 'asc'}], ajaxURL: panel.dataset.url,
        ajaxRequestFunc: request, dataLoaderError: 'Unable to load items.',
        columns: [
          {title:'Code',field:'code',minWidth:155,formatter:link},
          {title:'Description',field:'description',minWidth:230,widthGrow:3,formatter:'plaintext'},
          {title:'Unit',field:'unit',minWidth:100,formatter:'plaintext'},
          ...[['on_hand','On hand'],['reserved','Reserved'],['available','Available'],['critical_level','Critical level'],['target_level','Target level']]
            .map(([field,title]) => ({title,field,minWidth:125,formatter:quantity})),
          {title:'Physical stock',field:'physical',minWidth:160,formatter:cell=>plain(labels[cell.getValue()])},
          {title:'Availability',field:'availability',minWidth:160,formatter:cell=>plain(labels[cell.getValue()])},
          {title:'Catalog status',field:'active',minWidth:125,formatter:cell=>plain(cell.getValue() ? 'Active' : 'Inactive')},
        ].map(column => ({...column, ...(saved?.columns[column.field] || {})})),
      });
      const choices = document.querySelector('.inventory-column-choices');
      choices.replaceChildren();
      // Code remains visible so each item retains its existing detail link.
      for (const [field, title] of [['description','Description'],['unit','Unit'],['on_hand','On hand'],
        ['reserved','Reserved'],['available','Available'],['critical_level','Critical level'],
        ['target_level','Target level'],['physical','Physical stock'],['availability','Availability'],['active','Catalog status']]) {
        const option = document.createElement('label'), checkbox = document.createElement('input');
        checkbox.type = 'checkbox'; checkbox.checked = saved?.columns[field]?.visible ?? true;
        checkbox.addEventListener('change', () => table?.getColumn(field).toggle());
        option.append(checkbox, document.createTextNode(title)); choices.append(option);
      }
      table.on('dataSorted', () => {
        const order = table?.getSorters()[0];
        sort.value = order ? order.field + ':' + order.dir : 'code:asc';
      });
    } catch (error) {
      showStandard('The interactive table is unavailable. You can continue using the standard table.');
    }
  }
  function resetFilters() {
    filters.reset(); applied = defaultFilters();
    for (const [field, value] of Object.entries(applied)) filters.elements[field].value = value;
  }
  toggle.addEventListener('click', () => {
    if (table) showStandard();
    else { resetSelection(); resetFilters(); start(); loadViews().catch(viewError); }
  });
  filters.addEventListener('submit', event => {
    event.preventDefault();
    const next = Object.fromEntries(filterFields.map(field => [field, filters.elements[field].value]));
    applied = next;
    const [column, dir] = sort.value.split(':');
    table?.setSort(column, dir);
  });
  sort.addEventListener('change', () => {
    const [column, dir] = sort.value.split(':');
    table?.setSort(column, dir);
  });
  document.getElementById('inventory-reset').addEventListener('click', () => {
    showStandard(); resetSelection(); resetFilters(); start();
  });

  function selectedView() { return savedViews?.find(view => String(view.id) === viewSelect.value); }
  function viewError(error) { viewStatus.textContent = error.message || 'Saved views are unavailable. Reload the page and try again.'; }
  function viewURL(view) {
    const url = new URL('/supplies/items', window.location.origin);
    url.searchParams.set('inactive', view.state.active === 'active' ? '0' : '1');
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
    document.getElementById('inventory-open-view').disabled = saving || !selected;
    document.getElementById('inventory-update-view').disabled = saving || !selected;
    document.getElementById('inventory-delete-view').disabled = saving || !selected;
    document.getElementById('inventory-create-view').disabled = saving || !savedViews;
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
    if (!loadingViews) loadingViews = jsonRequest('/supplies/inventory-views')
      .then(data => { savedViews = data.views; renderViews(); return savedViews; })
      .finally(() => { loadingViews = null; });
    return loadingViews;
  }
  function currentState() {
    const order = table.getSorters()[0] || {field: 'code', dir: 'asc'};
    const columns = {};
    for (const field of fields) {
      const column = table.getColumn(field), width = column.getWidth();
      columns[field] = {visible: column.isVisible()};
      if (Number.isFinite(width) && width >= 75) columns[field].width = Math.round(width);
    }
    return {schema: 1, ...applied, sort: order.field, dir: order.dir, columns};
  }
  function updateExportButton() { exportButton.disabled = !exportReady || exporting; }
  exportButton.addEventListener('click', async () => {
    if (!table || !exportReady || exporting) return;
    const state = currentState(), target = new URL('/supplies/inventory-export.csv', window.location.origin);
    for (const key of [...filterFields, 'sort', 'dir']) {
      target.searchParams.set(key, state[key]);
    }
    target.searchParams.set('columns', fields.filter(field => state.columns[field].visible).join(','));
    exporting = true; updateExportButton(); exportStatus.textContent = 'Preparing CSV for all matching pages…';
    try {
      const response = await fetch(target, {credentials: 'same-origin', cache: 'no-store', redirect: 'error',
        signal: AbortSignal.timeout(60000), headers: {Accept: 'text/csv'}});
      if (!response.ok) {
        const data = response.headers.get('content-type')?.includes('application/json') ? await response.json() : {};
        throw new Error(data.error || 'CSV export could not load. Reload the page and try again.');
      }
      if (!response.headers.get('content-type')?.includes('text/csv')) throw new Error('Unexpected export response. Reload the page and try again.');
      const blob = await response.blob(), url = URL.createObjectURL(blob), anchor = document.createElement('a');
      anchor.href = url; anchor.download = 'supply-inventory.csv';
      document.body.append(anchor); anchor.click(); anchor.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      exportStatus.textContent = 'CSV downloaded for the view selected when export started.';
    } catch (error) { exportStatus.textContent = error.message || 'CSV export failed. Try again.'; }
    finally { exporting = false; updateExportButton(); }
  });
  async function changeView(action) {
    if (saving || !table) return;
    const selected = selectedView();
    if (action !== 'create' && !selected) return;
    const data = {action};
    if (selected && action !== 'create') Object.assign(data, {id: selected.id, revision: selected.revision});
    if (action !== 'delete') Object.assign(data, {name: viewName.value, state: currentState()});
    saving = true; updateViewButtons(); viewStatus.textContent = 'Saving view…';
    try {
      const result = await jsonRequest('/supplies/inventory-views', {method: 'POST',
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
  document.getElementById('inventory-open-view').addEventListener('click', () => {
    const view = selectedView();
    if (view) window.location.assign(viewURL(view));
  });
  viewForm.addEventListener('submit', event => { event.preventDefault(); changeView('create'); });
  document.getElementById('inventory-update-view').addEventListener('click', () => changeView('update'));
  document.getElementById('inventory-delete-view').addEventListener('click', () => changeView('delete'));
  controls.hidden = false;
  const requested = new URL(window.location.href).searchParams.get('saved_view');
  if (requested) loadViews().then(views => {
    const view = views.find(item => String(item.id) === requested);
    if (!view) throw new Error('Saved view not found or unavailable to you. Open the interactive table to choose another.');
    renderViews(requested);
    applied = Object.fromEntries(filterFields.map(field => [field, view.state[field]]));
    const unit = filters.elements.unit;
    if (applied.unit && !Array.from(unit.options).some(option => option.value === applied.unit)) {
      unit.add(new Option('Saved unit (no matching items)', applied.unit));
    }
    for (const [field, value] of Object.entries(applied)) filters.elements[field].value = value;
    sort.value = view.state.sort + ':' + view.state.dir;
    start(view.state);
  }).catch(error => { status.textContent = error.message; });
})();
