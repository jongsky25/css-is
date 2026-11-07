(() => {
  const panel = document.getElementById('document-understanding');
  if (!panel) return;
  const form = panel.closest('form'), target = panel.querySelector('#understanding-suggestions');
  const field = name => form.elements.namedItem(name);
  const changed = input => input.dispatchEvent(new Event('input', {bubbles: true}));
  const set = (name, value) => { const input = field(name); input.value = value || ''; changed(input); };
  const requests = Array.from(panel.querySelectorAll('[data-request]'));
  const entryControls = panel.querySelector('#request-entry-controls');
  const addRequest = panel.querySelector('#request-entry-add');
  const entryStatus = panel.querySelector('#request-entry-status');
  // Keep stable slots and every entered value; hide only completely blank forms.
  function hasEntry(request) {
    return Array.from(request.querySelectorAll('input, textarea, select')).some(input => {
      if (input.type === 'checkbox') return input.checked;
      if (input.name.endsWith('_kind')) return input.value !== 'manual';
      return Boolean(input.value.trim());
    });
  }
  function updateAddRequest() {
    if (addRequest) addRequest.disabled = requests.every(request => !request.hidden);
  }
  function revealRequest(index) {
    const request = requests.find(item => item.dataset.request === String(index));
    if (!request) return;
    request.hidden = false;
    request.open = true;
    updateAddRequest();
  }
  if (entryControls && addRequest) {
    requests.forEach(request => {
      request.hidden = !hasEntry(request);
      if (!request.hidden) request.open = true;
    });
    entryControls.hidden = false;
    updateAddRequest();
    addRequest.addEventListener('click', () => {
      const request = requests.find(item => item.hidden);
      if (!request) return;
      revealRequest(request.dataset.request);
      entryStatus.textContent = `Request ${Number(request.dataset.request) + 1} opened.${addRequest.disabled ? ' All five request forms are shown.' : ''}`;
      field(`need_${request.dataset.request}_action`).focus();
    });
  }
  function resetConfirmations() {
    panel.querySelectorAll('input[type=checkbox]').forEach(input => { input.checked = false; });
  }
  form.addEventListener('input', event => {
    const confirmation = field('review_confirmed');
    if (confirmation && event.target !== confirmation) confirmation.checked = false;
  });
  panel.addEventListener('input', event => {
    const name = event.target.name || '';
    if (event.target.type === 'checkbox') return;
    if (name.startsWith('need_')) {
      const index = name.split('_')[1];
      field(`need_${index}_confirmed`).checked = false;
      panel.querySelector(`[data-request="${index}"] summary`).textContent = `Request ${Number(index)+1}${field(`need_${index}_action`).value.trim() ? '' : ' (optional)'}`;
    }
    else if (name.startsWith('focus_')) field('focus_confirmed').checked = false;
    else if (name === 'needs_status') field('needs_status_confirmed').checked = false;
  });
  function show(data) {
    target.replaceChildren();
    panel.querySelector('#understanding-warning').textContent = data?.warning || 'No request analysis available. Review manually.';
    for (const request of data?.requests || []) {
      const card = document.createElement('div'); card.className = 'doc-card';
      const quote = document.createElement('p'); quote.textContent = `Source ${request.page}: ${request.evidence}`;
      const button = document.createElement('button'); button.type = 'button'; button.textContent = 'Use this request for review';
      button.addEventListener('click', () => {
        const index = [0,1,2,3,4].find(i => !hasEntry(requests.find(item => item.dataset.request === String(i))));
        if (index === undefined) { panel.querySelector('#understanding-warning').textContent = 'All five request slots contain entries. Review existing requests or record remaining requests separately.'; return; }
        for (const key of ['action','output','recipient','deadline','submission','evidence','page','kind']) set(`need_${index}_${key}`, request[key]);
        set('needs_status', 'requests');
        revealRequest(index);
        button.disabled = true; button.textContent = 'Added — check and confirm below';
        field(`need_${index}_action`).focus();
      });
      card.append(quote);
      const labels = {output:'Expected output',recipient:'Requested from',deadline:'Deadline',submission:'Submission'};
      for (const [key, label] of Object.entries(labels)) {
        if (!request[key]) continue;
        const detail = document.createElement('p');
        detail.textContent = `${label}: ${request[key]} · Evidence: ${request.detail_evidence?.[key] || request.evidence}`;
        card.append(detail);
      }
      for (const warning of request.warnings || []) {
        const note = document.createElement('p'); note.textContent = warning; card.append(note);
      }
      card.append(button); target.append(card);
    }
    for (const focus of data?.focus || []) {
      const card = document.createElement('p');
      const quote = document.createElement('span'); quote.textContent = `${focus.label} · Source ${focus.page}: ${focus.evidence} `;
      const button = document.createElement('button'); button.type = 'button'; button.textContent = 'Use focus area for review';
      button.addEventListener('click', () => {
        const name = !field('focus_primary').value ? 'focus_primary' : !field('focus_secondary').value && field('focus_primary').value !== focus.value ? 'focus_secondary' : null;
        if (!name) { panel.querySelector('#understanding-warning').textContent = 'Focus areas already contain entries. Review or change them below.'; return; }
        set(name, focus.value);
        set('focus_evidence', (field('focus_evidence').value + ` Source ${focus.page}: ${focus.evidence}`).trim().slice(0,1000));
        button.disabled = true; button.textContent = 'Added — check and confirm below';
      });
      card.append(quote, button); target.append(card);
    }
    if (data?.status === 'information_only') {
      const note = document.createElement('p'); note.textContent = '“For information only” wording found. Confirm manually only after checking the entire source for requests.'; target.append(note);
    }
  }
  form.addEventListener('document-understanding-result', event => { resetConfirmations(); show(event.detail); });
  function sourceChanged() {
    resetConfirmations(); target.replaceChildren();
    panel.querySelector('#understanding-warning').textContent = 'Source cleared or changed. Existing entries are retained for comparison; check them against the new source and confirm again.';
  }
  form.addEventListener('intake-source-cleared', sourceChanged);
  document.getElementById('intake-pdf')?.addEventListener('change', sourceChanged);
  document.getElementById('intake-source')?.addEventListener('input', sourceChanged);
  const initial = document.getElementById('understanding-initial');
  if (initial) show(JSON.parse(initial.textContent));
})();
