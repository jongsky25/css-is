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
  const announce = () => { status.focus({preventScroll:true}); status.scrollIntoView({block:'center', behavior:'smooth'}); };
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
    generation++; controller?.abort(); controller = null; status.setAttribute('aria-busy', 'false');
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
    status.textContent = pdf.size > 20 * 1024 * 1024
      ? `${pdf.name} is ${size} MiB; the limit is 20 MiB. Not uploaded or read; OCR did not run. Remove it or choose a smaller PDF.`
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
    if (pdf && pdf.size > 20 * 1024 * 1024) { status.textContent = 'Not uploaded or read; OCR did not run. The file exceeds 20 MiB. Remove it or choose a smaller PDF.'; remove.hidden = false; return; }
    const run = ++generation; controller = new AbortController(); remove.hidden = false;
    let timedOut = false;
    const timer = setTimeout(() => { timedOut = true; if (run === generation) controller?.abort(); }, 90000);
    reading = true; read.disabled = true; skip.disabled = true; file.disabled = true; source.disabled = true;
    clearSuggestions(); form.elements.confirmed.checked = false;
    status.textContent = 'Reading PDF… Keep this page open. Uploading and OCR can take up to 90 seconds.';
    status.setAttribute('aria-busy', 'true');
    try {
      const response = await fetch('/documents/intake/read', {
        method: 'POST', credentials: 'same-origin', cache: 'no-store', signal: controller.signal,
        headers: {'Content-Type': pdf ? 'application/pdf' : 'application/json', 'X-CSRF-Token': form.elements.csrf.value},
        body: pdf || JSON.stringify({url: source.value.trim()})
      });
      if (response.redirected || response.status === 401 || response.status === 403) {
        throw new Error('Your session may have expired. Sign in again, then retry. Your selected file has been kept.');
      }
      if (!(response.headers.get('content-type') || '').includes('application/json')) {
        throw new Error('The server did not return a reading result. Please retry; your file and entered details are kept.');
      }
      const result = await response.json();
      if (run !== generation) return;
      if (!response.ok) throw new Error(result.error || 'The PDF could not be read. Continue manually.');
      const notice = document.createElement('p'); notice.textContent = result.notice;
      suggestions.append(notice);
      for (const warning of result.warnings || []) {
        const paragraph = document.createElement('p'); paragraph.textContent = warning; suggestions.append(paragraph);
      }
      const allowed = ['subject', 'type', 'sender', 'document_date', 'due_date', 'references'];
      let applied = 0, found = 0;
      if (!result.suggestions || typeof result.suggestions !== 'object' || !Array.isArray(result.text_preview)) {
        throw new Error('The server returned an incomplete reading. Please retry.');
      }
      for (const [name, value] of Object.entries(result.suggestions || {})) {
        if (!allowed.includes(name) || typeof value !== 'string' || !value) continue;
        found++;
        const field = form.elements[name];
        const apply = () => {
          field.value = value; field.dataset.pdfSuggested = 'true';
          field.setAttribute('aria-description', 'Suggested from the PDF; review before registration.');
          form.elements.confirmed.checked = false;
        };
        // Recheck at response time so edits made during reading are preserved.
        const filled = !field.value.trim();
        if (filled) { apply(); applied++; }
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
      if (!found) preview.open = true;
      suggestions.hidden = false;
      const ocrPages = result.reading?.ocr_pages || [];
      const method = ocrPages.length ? `OCR ran on page(s) ${ocrPages.join(', ')}.` : 'Text was read directly; OCR was not needed.';
      const missing = allowed.filter(name => !form.elements[name].value.trim()).map(name => name.replaceAll('_', ' '));
      const next = document.createElement('p');
      next.textContent = missing.length ? `Still needs your entry or review: ${missing.join(', ')}. Details not stated clearly in the PDF are left blank.` : 'All supported correspondence fields have values; check them against the source.';
      suggestions.append(next);
      const manual = document.createElement('p'); manual.textContent = 'Choose the office scenario, work destination, concerned unit and priority yourself; PDF reading does not assign work or approve a document.'; suggestions.append(manual);
      const review = document.createElement('button'); review.type = 'button'; review.textContent = 'Review correspondence fields';
      review.addEventListener('click', () => form.elements.subject.focus()); suggestions.append(review);
      status.textContent = found
        ? `Reading complete. ${method} ${found} suggestion(s) found; ${applied} empty field(s) pre-filled, ${found - applied} existing entry/entries kept. Review the results below. Your selected file is kept for retry; no server attachment was saved.`
        : `The PDF was read, but no form fields could be identified reliably. ${method} No fields were changed. Read the extracted text below and enter the details manually, or retry with a clearer copy. Your selected file is kept.`;
      announce();
    } catch (error) {
      if (run === generation) {
        status.textContent = timedOut
          ? 'Reading timed out. No complete result was received. Your file and entered details are kept. Retry or use a smaller PDF.'
          : 'Reading did not complete. ' + (error instanceof TypeError ? 'Check your connection and retry. Your file and entered details are kept.' : (error.message || 'Retry or continue manually.'));
        announce();
      }
    } finally {
      clearTimeout(timer);
      if (run === generation) { controller = null; status.setAttribute('aria-busy', 'false'); idle(); }
    }
  });
  update();
})();
