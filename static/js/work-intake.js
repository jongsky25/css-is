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
  const remove = document.getElementById('intake-remove');
  let reading = false, generation = 0, controller = null;
  const idle = () => {
    reading = false; read.disabled = false; skip.disabled = false;
    file.disabled = false; source.disabled = false;
  };
  const clearSuggestions = () => {
    suggestions.replaceChildren(); suggestions.hidden = true;
    for (const field of form.querySelectorAll('[data-pdf-suggested]')) {
      delete field.dataset.pdfSuggested;
      field.removeAttribute('aria-description');
    }
  };
  const skip = document.getElementById('intake-skip');
  const reset = () => {
    generation++; controller?.abort(); controller = null;
    file.value = ''; source.value = ''; clearSuggestions(); idle(); remove.hidden = true;
    status.textContent = 'File and reading cleared. Any form values already entered or applied are kept for review.';
    form.elements.confirmed.checked = false;
  };
  remove.addEventListener('click', reset);
  skip.addEventListener('click', () => { reset(); form.elements.subject.focus(); });
  file.addEventListener('change', () => {
    clearSuggestions(); remove.hidden = !file.files.length && !source.value.trim();
    const pdf = file.files[0];
    if (!pdf) { status.textContent = 'No file selected. Reading has not started.'; return; }
    const size = (pdf.size / (1024 * 1024)).toFixed(1);
    status.textContent = pdf.size > 6 * 1024 * 1024
      ? `${pdf.name} is ${size} MiB; the limit is 6 MiB. Not uploaded or read; OCR did not run. Remove it or choose a smaller PDF.`
      : `${pdf.name} selected (${size} MiB). Reading has not started. Tap Read and pre-fill to read it.`;
  });
  source.addEventListener('input', () => {
    clearSuggestions(); remove.hidden = !file.files.length && !source.value.trim();
    status.textContent = 'Reading has not started. Tap Read and pre-fill when ready.';
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
    if (pdf && pdf.size > 6 * 1024 * 1024) { status.textContent = 'Not uploaded or read; OCR did not run. The file exceeds 6 MiB. Remove it or choose a smaller PDF.'; remove.hidden = false; return; }
    const run = ++generation; controller = new AbortController(); remove.hidden = false;
    reading = true; read.disabled = true; skip.disabled = true; file.disabled = true; source.disabled = true;
    clearSuggestions(); form.elements.confirmed.checked = false;
    status.textContent = 'Reading PDF… Scanned pages may take up to 45 seconds for OCR.';
    try {
      const response = await fetch('/documents/intake/read', {
        method: 'POST', credentials: 'same-origin', cache: 'no-store', signal: controller.signal,
        headers: {'Content-Type': pdf ? 'application/pdf' : 'application/json', 'X-CSRF-Token': form.elements.csrf.value},
        body: pdf || JSON.stringify({url: source.value.trim()})
      });
      const result = await response.json();
      if (run !== generation) return;
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
      const preview = document.createElement('details');
      const summary = document.createElement('summary'); summary.textContent = 'What was read — extracted text';
      preview.append(summary);
      for (const item of result.text_preview || []) {
        const heading = document.createElement('h4'); heading.textContent = `Page ${item.page}`;
        const text = document.createElement('pre'); text.textContent = item.text || '(No readable text on this page.)';
        preview.append(heading, text);
        if (item.truncated) {
          const note = document.createElement('p'); note.textContent = 'Preview limited to the first 2,000 characters of this page.'; preview.append(note);
        }
      }
      if (result.preview_truncated) {
        const note = document.createElement('p'); note.textContent = 'Showing the first 10 pages only.'; preview.append(note);
      }
      suggestions.append(preview);
      if (!Object.keys(result.suggestions || {}).length) preview.open = true;
      suggestions.hidden = false;
      const ocrPages = result.reading?.ocr_pages || [];
      const method = ocrPages.length ? `OCR ran on page(s) ${ocrPages.join(', ')}.` : 'Text was read directly; OCR was not needed.';
      status.textContent = `Reading complete. ${method} ${Object.keys(result.suggestions || {}).length} field suggestion(s) found. Review the suggestions and extracted text below. The PDF has not been saved.`;
    } catch (error) {
      if (run === generation) status.textContent = 'Reading did not complete. ' + (error.message || 'Continue manually.');
    } finally {
      if (run === generation) { file.value = ''; source.value = ''; controller = null; idle(); }
    }
  });
  update();
})();
