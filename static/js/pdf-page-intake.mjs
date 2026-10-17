// Local-file page processing. No persistence: results and PDF bytes live only in this tab.
const form = document.getElementById('intake-form');
if (form) {
  const el = id => document.getElementById(id);
  const file = el('intake-pdf'), source = el('intake-source'), panel = el('pdf-pages');
  const open = el('pdf-open'), read = el('pdf-read-pages'), retry = el('pdf-retry');
  const cancel = el('pdf-cancel'), review = el('pdf-review'), progress = el('pdf-progress');
  const selection = el('pdf-selection'), canvas = el('pdf-preview');
  let documentPdf = null, loading = null, previewTask = null, active = null;
  let generation = 0, busy = false, previewPage = 1;
  const results = new Map(), failed = new Map();
  let attempted = new Set();
  const MAX_TOTAL_TEXT = 100000;

  function controls(value) {
    busy = value; form.dataset.pageBusy = String(value);
    for (const item of [open, read, retry, review, file, source, selection, el('pdf-prev'), el('pdf-next'), el('intake-read'), el('intake-skip')]) item.disabled = value;
    cancel.disabled = !value;
  }
  function list() {
    const list = el('pdf-results'); list.replaceChildren();
    for (const number of [...attempted].sort((a,b) => a-b)) {
      const item = document.createElement('li');
      item.textContent = results.has(number) ? `Page ${number}: read ${results.get(number).ocr ? 'with OCR' : 'directly'} (${results.get(number).text.length} characters).`
        : failed.has(number) ? `Page ${number}: ${failed.get(number)}` : `Page ${number}: not processed.`;
      list.append(item);
    }
    retry.hidden = !failed.size; review.hidden = !results.size;
  }
  function cancelRun() {
    generation++; active?.abort(); active = null; previewTask?.cancel();
    controls(false); list();
    progress.textContent = `Reading cancelled. ${results.size} completed page(s) kept. Unprocessed pages have not been read. Review completed pages or select pages to continue.`;
  }
  const destroy = task => { if(task) Promise.resolve(task.destroy()).catch(()=>{}); };
  function clear() {
    cancelRun(); destroy(loading); loading = null; documentPdf = null;
    results.clear(); failed.clear(); attempted.clear(); panel.hidden = true;
    canvas.width = canvas.height = 1; list(); progress.textContent = '';
    el('pdf-info').textContent = ''; el('pdf-page-label').textContent = ''; selection.value = '';
  }
  file.addEventListener('change', clear);
  source.addEventListener('input', clear);
  form.addEventListener('intake-source-cleared', clear);
  // Starting the legacy reader explicitly replaces this reading context.
  form.addEventListener('intake-legacy-reading', clear);
  window.addEventListener('pagehide', clear);
  cancel.addEventListener('click', cancelRun);

  function selected() {
    const numbers = new Set();
    for (const part of selection.value.split(',')) {
      const match = part.trim().match(/^(\d+)(?:\s*-\s*(\d+))?$/);
      if (!match) throw new Error('Enter page numbers or ranges, such as 1-3, 7.');
      const first = Number(match[1]), last = Number(match[2] || match[1]);
      if (first < 1 || last < first || last > documentPdf.numPages || last - first >= 10) throw new Error('Choose valid pages, up to 10 per batch.');
      for (let n=first; n<=last; n++) numbers.add(n);
      if (numbers.size > 10) throw new Error('Read at most 10 pages per batch.');
    }
    return [...numbers].sort((a,b) => a-b);
  }
  async function preview() {
    const run = generation;
    previewTask?.cancel();
    const page = await documentPdf.getPage(previewPage);
    if (run !== generation) return;
    const base = page.getViewport({scale:1});
    const viewport = page.getViewport({scale:Math.min(1, 420/base.width, 600/base.height)});
    canvas.width = Math.ceil(viewport.width); canvas.height = Math.ceil(viewport.height);
    el('pdf-page-label').textContent = `Page ${previewPage} of ${documentPdf.numPages}`;
    const task = page.render({canvasContext:canvas.getContext('2d'), viewport}); previewTask = task;
    try { await task.promise; } finally { if(previewTask === task) previewTask = null; page.cleanup(); }
  }
  for (const [id, delta] of [['pdf-prev',-1],['pdf-next',1]]) el(id).addEventListener('click', async () => {
    if (busy || !documentPdf) return;
    previewPage = Math.min(documentPdf.numPages, Math.max(1, previewPage+delta));
    el('pdf-prev').disabled = el('pdf-next').disabled = true;
    try { await preview(); } catch { progress.textContent = 'This page preview could not be displayed.'; }
    finally { el('pdf-prev').disabled = el('pdf-next').disabled = busy; }
  });
  open.addEventListener('click', async () => {
    if (busy) return;
    if (!file.files[0] || source.value.trim()) {
      el('intake-read-status').textContent = 'Select a local PDF only for page preview. For a Drive file, download it to Files first.'; return;
    }
    const chosen = file.files[0];
    // Local safety guard, not an upload limit. The whole source remains on device.
    if (chosen.size > 100*1024*1024) {
      el('intake-read-status').textContent = 'This file exceeds the 100 MiB on-device preview limit. Split it locally first.'; return;
    }
    clear(); form.dispatchEvent(new Event('intake-reading-cleared')); const run = generation; controls(true); panel.hidden = false;
    progress.textContent = 'Opening the PDF on your device. The original file is not being uploaded.';
    try {
      const pdfjs = await import('/static/vendor/pdfjs/pdf.min.mjs');
      if (run !== generation) return;
      pdfjs.GlobalWorkerOptions.workerSrc = '/static/vendor/pdfjs/pdf.worker.min.mjs';
      const bytes = await chosen.arrayBuffer();
      if (run !== generation) return;
      loading = pdfjs.getDocument({data:bytes, isEvalSupported:false, cMapUrl:'/static/vendor/pdfjs/cmaps/',
        cMapPacked:true, standardFontDataUrl:'/static/vendor/pdfjs/standard_fonts/', stopAtErrors:true});
      // Do not leave encrypted PDFs waiting for an unseen password prompt.
      const task = loading;
      loading.onPassword = () => { destroy(task); };
      const pdf = await loading.promise;
      if (run !== generation) { await pdf.destroy(); return; }
      if (pdf.numPages > 500) throw new Error('Choose a PDF with at most 500 pages for on-device preview.');
      documentPdf = pdf; previewPage = 1;
      selection.value = pdf.numPages > 1 ? `1-${Math.min(3,pdf.numPages)}` : '1';
      el('pdf-info').textContent = `${chosen.name}: ${pdf.numPages} pages. Only selected pages will be read; remaining pages are unprocessed.`;
      await preview();
      if (run !== generation) return;
      progress.textContent = 'Preview ready. The first few pages are suggested; adjust the selection, then read selected pages.';
      el('intake-read-status').textContent = 'PDF opened locally. No pages have been read yet.';
    } catch (error) {
      if (run === generation) { destroy(loading); loading = null; documentPdf = null;
        progress.textContent = 'Could not preview this PDF. It may be protected, damaged, or too complex for this device. Try a smaller/unlocked copy, or use whole-file reading for files up to 20 MiB.'; }
    } finally { if (run === generation) controls(false); }
  });

  async function request(path, body, type, run) {
    const controller = new AbortController(); active = controller;
    const timer = setTimeout(() => controller.abort(), 30000);
    try {
      const response = await fetch(path, {method:'POST', credentials:'same-origin', cache:'no-store', signal:controller.signal,
        headers:{'Content-Type':type,'X-CSRF-Token':form.elements.csrf.value}, body});
      if (run !== generation) throw new Error('Cancelled');
      if (response.redirected || response.status === 401 || response.status === 403) throw new Error('Sign in again, then retry the failed pages.');
      if (!(response.headers.get('content-type') || '').includes('application/json')) throw new Error('Server unavailable. Retry this page.');
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Page reading failed. Retry it.');
      return data;
    } catch (error) {
      if (error.name === 'AbortError') throw new Error('Page request timed out or was cancelled. Retry it.');
      throw error;
    } finally { clearTimeout(timer); if (active === controller) active = null; }
  }
  async function imageFor(page, run) {
    const base = page.getViewport({scale:1});
    if (!Number.isFinite(base.width * base.height) || base.width <= 0 || base.height <= 0) throw new Error('Invalid page dimensions.');
    const scale = Math.min(200/72, Math.sqrt(3900000 / (base.width*base.height)), 8192/base.width, 8192/base.height);
    const viewport = page.getViewport({scale});
    const image = document.createElement('canvas'); image.width = Math.ceil(viewport.width); image.height = Math.ceil(viewport.height);
    let task;
    try {
      task = page.render({canvasContext:image.getContext('2d'), viewport, background:'white'});
      previewTask = task;
      await task.promise;
      if (run !== generation) throw new Error('Cancelled');
      for (const quality of [.82,.65,.45]) {
        const blob = await new Promise(resolve => image.toBlob(resolve,'image/jpeg',quality));
        if (blob && blob.size <= 2*1024*1024) return blob;
      }
      throw new Error('Page image is too large. Use a smaller or lower-resolution source.');
    } finally { image.width = image.height = 1; if(previewTask === task) previewTask = null; }
  }
  async function aggregate(run) {
    if (!results.size) return;
    const result = await request('/documents/intake/pages-result', JSON.stringify({pages:[...results.values()]}), 'application/json', run);
    if (run === generation) {
      const incomplete = [...attempted].filter(n => !results.has(n)).sort((a,b)=>a-b);
      if (incomplete.length) result.warnings.unshift(`Not read successfully: page(s) ${incomplete.join(', ')}. These pages are not included in the suggestions.`);
      form.dispatchEvent(new CustomEvent('intake-reading-result', {detail:result}));
    }
  }
  async function batch(numbers) {
    if (busy || !documentPdf) return;
    if (numbers.length > 10) { progress.textContent = 'Select at most 10 failed pages to retry in one batch.'; return; }
    if (new Set([...results.keys(), ...numbers]).size > 50) { progress.textContent = 'At most 50 completed pages per reading. Clear the reading to start another.'; return; }
    const run = ++generation; controls(true); el('intake-remove').hidden = false;
    for (const n of numbers) attempted.add(n);
    list();
    try {
      for (const [index, number] of numbers.entries()) {
        if (run !== generation) break;
        if (results.has(number)) continue;
        progress.textContent = `Reading page ${number} (${index+1} of ${numbers.length} selected). ${results.size} page(s) completed.`;
        let page;
        try {
          page = await documentPdf.getPage(number);
          const content = await page.getTextContent();
          let text = content.items.map(item => (item.str || '') + (item.hasEOL ? '\n' : ' ')).join('').trim();
          let ocr = text.replace(/\W/g,'').length < 40;
          if (ocr) {
            const blob = await imageFor(page, run);
            if (run !== generation) break;
            const result = await request('/documents/intake/page', blob, 'image/jpeg', run);
            if (typeof result.text !== 'string') throw new Error('Incomplete page result. Retry it.');
            text = result.text;
          }
          if (run !== generation) break;
          if (!text.trim()) throw new Error('No readable text found. Try a clearer copy.');
          if (text.length + [...results.values()].reduce((n,item)=>n+item.text.length,0) > MAX_TOTAL_TEXT) throw new Error('Reading text limit reached. Clear and select fewer pages.');
          results.set(number,{page:number,text,ocr}); failed.delete(number);
        } catch (error) {
          if (run === generation) failed.set(number,error.message || 'Could not read this page. Retry it.');
        } finally { page?.cleanup(); if (run === generation) list(); }
      }
      if (run === generation) {
        progress.textContent = `${results.size} page(s) completed; ${failed.size} failed. Other pages remain unprocessed. Read more pages, retry failures, or review completed pages.`;
        await aggregate(run);
      }
    } catch (error) {
      if (run === generation) progress.textContent = `Completed readings are kept. Could not prepare suggestions: ${error.message}. Use Review completed pages to retry.`;
    } finally { if (run === generation) { controls(false); list(); } }
  }
  read.addEventListener('click', () => {
    if (!documentPdf) { progress.textContent = 'Open a PDF preview first.'; return; }
    try { batch(selected()); } catch(error) { progress.textContent = error.message; }
  });
  retry.addEventListener('click', () => batch([...failed.keys()]));
  review.addEventListener('click', async () => {
    const run = ++generation; controls(true);
    try { await aggregate(run); } catch(error) { if (run===generation) progress.textContent = 'Could not prepare suggestions. Completed readings are kept; retry. ' + error.message; }
    finally { if(run===generation) controls(false); }
  });
}
