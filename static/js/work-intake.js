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
  const direction = form.elements.direction;
  let directionEdited = direction.value !== 'IN', directionInferred = false;
  const directionNote = document.createElement('small');
  directionNote.hidden = true;
  direction.closest('label').append(directionNote);
  direction.addEventListener('change', () => {
    directionEdited = true; directionInferred = false; directionNote.hidden = true;
    invalidateApproval(); form.elements.confirmed.checked = false;
  });
  form.elements.sender.addEventListener('input', () => {
    if (directionEdited) return;
    const office = form.elements.sender.value.trim().replace(/\s+/g, ' ');
    const outgoing = /^(?:bureau of local health systems development|BLHSD)(?=$|[\s(,–—-])/i.test(office);
    if (!outgoing && !directionInferred) return;
    direction.value = outgoing ? 'OUT' : 'IN';
    directionInferred = outgoing;
    directionNote.textContent = 'Outgoing because the originating office is BLHSD. You can change this before approval.';
    directionNote.hidden = !outgoing;
    direction.dispatchEvent(new Event('input', {bubbles:true}));
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
    reading = false; form.dataset.legacyBusy = 'false'; read.disabled = false; skip.disabled = false;
    file.disabled = false; source.disabled = false;
  };
  const clearSuggestions = () => {
    suggestions.replaceChildren(); suggestions.hidden = true;
    form.querySelectorAll('.pdf-field-note').forEach(note => note.remove());
    for (const field of form.querySelectorAll('[data-pdf-suggested]')) {
      delete field.dataset.pdfSuggested;
      field.removeAttribute('aria-description');
    }
  };
  const skip = document.getElementById('intake-skip');
  const reset = () => {
    invalidateApproval();
    form.dispatchEvent(new Event('intake-source-cleared'));
    generation++; controller?.abort(); controller = null; status.setAttribute('aria-busy', 'false');
    file.value = ''; source.value = ''; read.hidden = false; clearSuggestions(); idle(); remove.hidden = true;
    status.textContent = 'File and reading cleared. Any form values already entered or applied are kept for review.';
    form.elements.confirmed.checked = false;
  };
  remove.addEventListener('click', reset);
  skip.addEventListener('click', () => { reset(); document.getElementById('intake-details').hidden = false; form.elements.subject.focus(); });
  const clearAutoFields = () => {
    for (const field of form.querySelectorAll('[data-pdf-value]')) {
      if (field.value === field.dataset.pdfValue) { field.value = ''; field.dispatchEvent(new Event('input', {bubbles:true})); }
      delete field.dataset.pdfValue;
    }
  };
  file.addEventListener('change', () => {
    clearAutoFields();
    clearSuggestions(); invalidateApproval(); remove.hidden = !file.files.length && !source.value.trim();
    const pdf = file.files[0]; read.hidden = !!pdf;
    if (!pdf) { status.textContent = 'No file selected. Reading has not started.'; return; }
    const size = (pdf.size / (1024 * 1024)).toFixed(1);
    status.textContent = `${pdf.name} selected (${size} MiB). Opening and reading the first page…`;
  });
  source.addEventListener('input', () => {
    clearAutoFields();
    clearSuggestions(); invalidateApproval(); remove.hidden = !file.files.length && !source.value.trim();
    status.textContent = 'Reading has not started. Tap Read document link when ready.';
  });
  form.addEventListener('input', event => { if (event.target !== form.elements.confirmed) form.elements.confirmed.checked = false; });
  let approved = false;
  const approval = document.getElementById('intake-approval');
  document.getElementById('intake-details').hidden = !form.elements.subject.value;
  document.getElementById('intake-work').hidden = true; document.getElementById('intake-register').hidden = true;
  function invalidateApproval() { approved = false; approval.textContent = 'Details need your review.'; document.getElementById('intake-work').hidden = true; document.getElementById('intake-register').hidden = true; }
  document.getElementById('intake-details').addEventListener('input', invalidateApproval);
  form.addEventListener('intake-reading-cleared', invalidateApproval);
  document.getElementById('intake-approve').addEventListener('click', () => {
    if (reading || form.dataset.pageBusy === 'true') { approval.textContent = 'Wait for reading to finish, then review the fields.'; return; }
    const invalid = [...document.querySelectorAll('#intake-details input, #intake-details textarea')].find(field => !field.checkValidity());
    if (invalid) { invalid.reportValidity(); return; }
    document.getElementById('intake-work').hidden = false; document.getElementById('intake-register').hidden = false;
    approved = true; approval.textContent = 'Details approved. Choose the work and confirm registration below.';
    document.getElementById('intake-scenario').focus();
  });
  form.addEventListener('submit', event => {
    if (!approved) { event.preventDefault(); approval.textContent = 'Review the fields and select Approve details before registering.'; document.getElementById('intake-approve').focus(); }

    if (reading || form.dataset.pageBusy === 'true') { event.preventDefault(); status.textContent = 'Wait for PDF reading to finish before registering.'; }
  });
  const showResult = result => {
    if (!result || !result.suggestions || typeof result.suggestions !== 'object' || !Array.isArray(result.text_preview)) throw new Error('Incomplete reading result. Retry.');
    clearSuggestions();
    document.getElementById('intake-details').hidden = false;
    invalidateApproval();
      const notesTitle = document.createElement('summary'); notesTitle.textContent = 'Reading notes and extracted text'; suggestions.append(notesTitle);
      const notice = document.createElement('p'); notice.textContent = result.notice;
      suggestions.append(notice);
      for (const warning of result.warnings || []) {
        const paragraph = document.createElement('p'); paragraph.textContent = warning; suggestions.append(paragraph);
      }
      const allowed = ['subject', 'type', 'sender', 'document_date', 'due_date', 'references'];
      let applied = 0, found = 0;
      if (!result.suggestions || typeof result.suggestions !== 'object' || !Array.isArray(result.text_preview)) throw new Error('Incomplete reading result. Retry.');
      for (const name of allowed) {
        const field = form.elements[name];
        if (!result.suggestions[name] && field.dataset.pdfValue !== undefined && field.value === field.dataset.pdfValue) {
          field.value = ''; delete field.dataset.pdfValue;
          field.dispatchEvent(new Event('input', {bubbles:true}));
        }
      }
      for (const [name, value] of Object.entries(result.suggestions)) {
        if (!allowed.includes(name) || typeof value !== 'string' || !value) continue;
        found++;
        const field = form.elements[name];
        const filled = !field.value.trim() || (field.dataset.pdfValue !== undefined && field.value === field.dataset.pdfValue);
        if (filled) {
          field.value = value; field.dataset.pdfValue = value; field.dataset.pdfSuggested = 'true';
          field.dispatchEvent(new Event('input', {bubbles:true}));
          field.dispatchEvent(new Event('change', {bubbles:true}));
          form.elements.confirmed.checked = false; applied++;
        }
        const note = document.createElement('details'); note.className = 'pdf-field-note';
        const caption = document.createElement('summary'); caption.textContent = filled ? 'Read from source — check evidence' : 'Your entry kept — compare source'; note.append(caption);
        const excerpt = document.createElement('small'); excerpt.textContent = `${filled ? 'Read from source — review' : 'Your entry kept'} · ` + (result.evidence?.[name] || []).map(item => `Page ${item.page}: ${item.text}`).join(' ');
        note.append(excerpt); field.closest('label').append(note);
      }
      for (const name of allowed) {
        const field = form.elements[name];
        const conflicts = result.conflicts?.[name];
        if (Array.isArray(conflicts) && conflicts.length) {
          const note = document.createElement('div'); note.className = 'pdf-field-note';
          const heading = document.createElement('strong'); heading.textContent = 'Different readings found. Edit this field after checking the source:'; note.append(heading);
          for (const item of conflicts) {
            const candidate = document.createElement('p'); candidate.textContent = `Page ${item.page}: ${item.value}`; note.append(candidate);
          }
          field.closest('label').append(note);
          continue;
        }
        if (field.value.trim()) continue;
        const note = document.createElement('small'); note.className = 'pdf-field-note';
        note.textContent = name === 'due_date' ? 'No reliable deadline captured. Check the source; leave blank if none is stated.' : 'Not identified reliably. Check the source and enter this detail.';
        field.closest('label').append(note);
      }
      const subjectReadings = result.field_readings?.subject || [];
      for (const reading of subjectReadings) {
        const detail = document.createElement('details'); detail.className = 'pdf-field-note';
        detail.open = reading.status !== 'read';
        const heading = document.createElement('summary');
        heading.textContent = `Page ${reading.page}: ${reading.status === 'read' ? 'DTRAK subject box read — check source' : 'Subject extraction needs review'}`;
        detail.append(heading);
        const reason = document.createElement('p'); reason.textContent = reading.reason || 'No subject-box result was returned.'; detail.append(reason);
        if (typeof reading.preview === 'string' && /^data:image\/jpeg;base64,[A-Za-z0-9+/=]+$/.test(reading.preview) && reading.preview.length < 150000) {
          const image = document.createElement('img'); image.src = reading.preview; image.alt = 'Detected DTRAK subject box'; image.style.maxWidth = '100%'; detail.append(image);
        }
        const raw = document.createElement('pre'); raw.textContent = reading.raw || 'No text was returned for this subject box.'; detail.append(raw);
        if (reading.status !== 'read' && result.scope === 'selected_pages') {
          const retryPage = document.createElement('button'); retryPage.type = 'button'; retryPage.textContent = 'Retry this page';
          retryPage.addEventListener('click', () => form.dispatchEvent(new CustomEvent('intake-retry-page', {detail:{page:reading.page}}))); detail.append(retryPage);
        }
        form.elements.subject.closest('label').append(detail);
      }
      const preview = document.createElement('details');
      const summary = document.createElement('summary'); summary.textContent = 'What was read — extracted text';
      preview.append(summary);
      if (!result.text_preview.length) {
        const empty = document.createElement('p'); empty.textContent = 'The reader returned no page-text preview. Retry reading or inspect the original page; no text preview is available for this result.'; preview.append(empty);
      }
      for (const item of result.text_preview || []) {
        const heading = document.createElement('h4'); heading.textContent = `Page ${item.page}`;
        const text = document.createElement('pre'); text.textContent = item.text || '(No readable text returned for this page. Retry reading or inspect the page preview.)';
        preview.append(heading, text);
        if (item.truncated) {
          const note = document.createElement('p'); note.textContent = 'Preview limited to the first 2,000 characters of this page.'; preview.append(note);
        }
      }
      if (result.preview_truncated) {
        const note = document.createElement('p'); note.textContent = 'Showing up to 10 completed pages only.'; preview.append(note);
      }
      suggestions.append(preview);
      suggestions.open = !found;
      if (!found) preview.open = true;
      suggestions.hidden = false;
      const ocrPages = result.reading?.ocr_pages || [];
      const method = ocrPages.length ? `OCR ran on page(s) ${ocrPages.join(', ')}.` : 'Text was read directly; OCR was not needed.';
      const missing = allowed.filter(name => !form.elements[name].value.trim()).map(name => name.replaceAll('_', ' '));
      const next = document.createElement('p');
      next.textContent = missing.length ? `Still needs your entry or review: ${missing.join(', ')}. Details not stated clearly in the PDF are left blank.` : 'All supported correspondence fields have values; check them against the source.';
      suggestions.append(next);
      status.textContent = found
        ? `${result.scope === 'selected_pages' ? 'Completed selected pages reviewed.' : 'Reading complete.'} ${method} ${found} suggestion(s) found; ${applied} empty field(s) pre-filled, ${found - applied} existing entry/entries kept. Review the results below. Your selected file is kept for retry; no server attachment was saved.`
        : `${result.scope === 'selected_pages' ? 'Selected pages were read' : 'The PDF was read'}, but no form fields could be identified reliably. ${method} No fields were changed. Read the extracted text below and enter the details manually, or retry with a clearer copy. Your selected file is kept.`;
      document.getElementById('intake-details').scrollIntoView({block:'start',behavior:'smooth'});
  };
  form.addEventListener('intake-reading-result', event => {
    try { showResult(event.detail); }
    catch (_) { invalidateApproval(); status.textContent = 'The reading result could not be displayed. Your entered details are kept. Use Review completed pages to retry, or enter details manually.'; announce(); }
  });
  form.addEventListener('intake-reading-cleared', clearSuggestions);
  read.addEventListener('click', async () => {
    if (reading) return;
    if (file.files.length && source.value.trim()) {
      status.textContent = 'Choose either a file or a link, not both.'; return;
    }
    const pdf = file.files[0];
    if (!pdf && !source.value.trim()) { status.textContent = 'Select a PDF or enter a public PDF link.'; return; }
    if (pdf && pdf.size > 20 * 1024 * 1024) { status.textContent = 'Not uploaded or read; OCR did not run. The file exceeds 20 MiB. Remove it or choose a smaller PDF.'; remove.hidden = false; return; }
    form.dispatchEvent(new Event('intake-legacy-reading'));
    const run = ++generation; controller = new AbortController(); remove.hidden = false;
    let timedOut = false;
    const timer = setTimeout(() => { timedOut = true; if (run === generation) controller?.abort(); }, 90000);
    reading = true; form.dataset.legacyBusy = 'true'; read.disabled = true; skip.disabled = true; file.disabled = true; source.disabled = true;
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
      showResult(result);
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
