(() => {
  const form = document.getElementById('intake-form');
  if (!form) return;
  const scenario = form.elements.scenario, mode = form.elements.work_mode;
  const update = () => {
    for (const kind of ['new', 'existing']) {
      const panel = document.getElementById(`intake-${kind}`);
      if (panel) { panel.hidden = mode.value !== kind; panel.disabled = mode.value !== kind; }
    }
    for (const guide of form.querySelectorAll('.intake-guide')) guide.open = guide.dataset.scenario === scenario.value;
  };
  scenario.addEventListener('change', () => {
    if (scenario.value === 'reference') mode.value = 'reference';
    else if (mode.value === 'reference' && [...mode.options].some(o => o.value === 'new')) mode.value = 'new';
    const guide = [...form.querySelectorAll('.intake-guide')].find(g => g.dataset.scenario === scenario.value);
    if (form.elements.outcome && !form.elements.outcome.value) form.elements.outcome.value = guide.dataset.outcome;
    form.elements.confirmed.checked = false;
    update();
  });
  mode.addEventListener('change', () => { form.elements.confirmed.checked = false; update(); });
  for (const button of form.querySelectorAll('.intake-use')) button.addEventListener('click', () => {
    const field = form.elements[button.dataset.field];
    if (field) { field.value = button.dataset.value; form.elements.confirmed.checked = false; field.focus(); }
  });
  const read = document.getElementById('intake-read');
  const file = document.getElementById('intake-pdf');
  const source = document.getElementById('intake-source');
  const status = document.getElementById('intake-read-status');
  const suggestions = document.getElementById('intake-suggestions');
  let reading = false;
  const clearSuggestions = () => {
    suggestions.replaceChildren(); suggestions.hidden = true;
    for (const field of form.querySelectorAll('[data-pdf-suggested]')) {
      delete field.dataset.pdfSuggested;
      field.removeAttribute('aria-description');
    }
  };
  const skip = document.getElementById('intake-skip');
  skip.addEventListener('click', () => {
    file.value = ''; source.value = ''; clearSuggestions(); status.textContent = '';
    form.elements.subject.focus();
  });
  form.addEventListener('input', () => { form.elements.confirmed.checked = false; });
  form.addEventListener('submit', event => {
    if (reading) { event.preventDefault(); status.textContent = 'Wait for PDF reading to finish before registering.'; }
  });
  read.addEventListener('click', async () => {
    if (reading) return;
    if (file.files.length && source.value.trim()) {
      status.textContent = 'Choose either a file or a link, not both.'; return;
    }
    const pdf = file.files[0];
    if (!pdf && !source.value.trim()) { status.textContent = 'Select a PDF or enter a public PDF link.'; return; }
    if (pdf && pdf.size > 6 * 1024 * 1024) { status.textContent = 'Choose a PDF no larger than 6 MiB.'; return; }
    reading = true; read.disabled = true; skip.disabled = true; file.disabled = true; source.disabled = true;
    clearSuggestions(); form.elements.confirmed.checked = false;
    status.textContent = 'Reading PDF…';
    try {
      const response = await fetch('/documents/intake/read', {
        method: 'POST', credentials: 'same-origin', cache: 'no-store',
        headers: {'Content-Type': pdf ? 'application/pdf' : 'application/json', 'X-CSRF-Token': form.elements.csrf.value},
        body: pdf || JSON.stringify({url: source.value.trim()})
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'The PDF could not be read. Continue manually.');
      const notice = document.createElement('p'); notice.textContent = result.notice;
      suggestions.append(notice);
      for (const warning of result.warnings || []) {
        const paragraph = document.createElement('p'); paragraph.textContent = warning; suggestions.append(paragraph);
      }
      const allowed = ['subject', 'type', 'sender', 'document_date', 'due_date', 'references'];
      for (const [name, value] of Object.entries(result.suggestions || {})) {
        if (!allowed.includes(name) || typeof value !== 'string' || !value) continue;
        const field = form.elements[name];
        const apply = () => {
          field.value = value; field.dataset.pdfSuggested = 'true';
          field.setAttribute('aria-description', 'Suggested from the PDF; review before registration.');
          form.elements.confirmed.checked = false;
        };
        // Recheck at response time so edits made during reading are preserved.
        const filled = !field.value.trim();
        if (filled) apply();
        const paragraph = document.createElement('p');
        paragraph.textContent = `${name.replaceAll('_', ' ')}: ${value} — ${filled ? 'pre-filled; please review' : 'existing entry kept'}. `;
        const button = document.createElement('button'); button.type = 'button'; button.textContent = 'Use this suggestion';
        button.addEventListener('click', () => { apply(); field.focus(); });
        paragraph.append(button); suggestions.append(paragraph);
        for (const item of result.evidence?.[name] || []) {
          const quote = document.createElement('blockquote'); quote.textContent = `Page ${item.page}: ${item.text}`; suggestions.append(quote);
        }
      }
      suggestions.hidden = false;
      status.textContent = 'Reading finished. Review the suggested values below. The PDF has not been saved.';
    } catch (error) {
      status.textContent = error.message || 'The PDF could not be read. Continue manually.';
    } finally {
      file.value = ''; source.value = ''; reading = false; read.disabled = false;
      skip.disabled = false; file.disabled = false; source.disabled = false;
    }
  });
  update();
})();
