const root = document.getElementById('doc-ink');
if (root) {
  const fileInput = document.getElementById('doc-ink-file');
  const status = document.getElementById('doc-ink-status');
  const controls = root.querySelector('.doc-ink-controls');
  const stage = root.querySelector('.doc-ink-stage');
  const pageCanvas = document.getElementById('doc-ink-pdf');
  const overlay = document.getElementById('doc-ink-overlay');
  const label = document.getElementById('doc-ink-page-label');
  const saved = JSON.parse(document.getElementById('doc-ink-saved').textContent);
  let pdf = null, pageNumber = 1, digest = '', draft = [], active = null, busy = false;

  function paint() {
    const ctx = overlay.getContext('2d');
    ctx.clearRect(0, 0, overlay.width, overlay.height);
    const prior = saved.filter(item => item.kind === 'ink' && item.page_number === pageNumber && item.source_sha256 === digest);
    const strokes = [...prior.flatMap(item => item.strokes), ...draft, ...(active ? [active] : [])];
    ctx.strokeStyle = '#ba2323';
    ctx.lineWidth = Math.max(2, overlay.width / 350);
    ctx.lineCap = ctx.lineJoin = 'round';
    for (const points of strokes) {
      if (points.length < 2) continue;
      ctx.beginPath();
      ctx.moveTo(points[0][0] * overlay.width, points[0][1] * overlay.height);
      for (const [x, y] of points.slice(1)) ctx.lineTo(x * overlay.width, y * overlay.height);
      ctx.stroke();
    }
  }

  async function showPage() {
    if (!pdf || busy) return;
    busy = true;
    draft = [];
    try {
      const page = await pdf.getPage(pageNumber);
      const natural = page.getViewport({ scale: 1 });
      const scale = Math.min(1.5, Math.max(.3, (root.clientWidth - 40) / natural.width));
      const viewport = page.getViewport({ scale });
      pageCanvas.width = overlay.width = Math.round(viewport.width);
      pageCanvas.height = overlay.height = Math.round(viewport.height);
      pageCanvas.style.width = overlay.style.width = pageCanvas.width + 'px';
      pageCanvas.style.height = overlay.style.height = pageCanvas.height + 'px';
      stage.style.width = pageCanvas.width + 'px';
      stage.style.height = pageCanvas.height + 'px';
      await page.render({ canvasContext: pageCanvas.getContext('2d'), viewport }).promise;
      label.textContent = `Page ${pageNumber} of ${pdf.numPages}`;
      document.getElementById('doc-ink-prev').disabled = pageNumber === 1;
      document.getElementById('doc-ink-next').disabled = pageNumber === Math.min(pdf.numPages, 500);
      controls.hidden = stage.hidden = false;
      paint();
    } finally { busy = false; }
  }

  fileInput.addEventListener('change', async () => {
    if (draft.length && !confirm('Discard unsaved pen marks?')) return;
    const file = fileInput.files?.[0];
    controls.hidden = stage.hidden = true;
    pdf = null; digest = ''; draft = []; pageNumber = 1;
    if (!file) return;
    if (file.size > 20 * 1024 * 1024 || (file.type && file.type !== 'application/pdf')) {
      status.textContent = 'Choose a PDF no larger than 20 MiB.';
      return;
    }
    try {
      status.textContent = 'Reading the local PDF…';
      const bytes = new Uint8Array(await file.arrayBuffer());
      const hash = await crypto.subtle.digest('SHA-256', bytes);
      digest = [...new Uint8Array(hash)].map(n => n.toString(16).padStart(2, '0')).join('');
      const pdfjs = await import('/static/vendor/pdfjs/pdf.min.mjs');
      pdfjs.GlobalWorkerOptions.workerSrc = '/static/vendor/pdfjs/pdf.worker.min.mjs';
      pdf = await pdfjs.getDocument({ data: bytes, isEvalSupported: false,
        cMapUrl: '/static/vendor/pdfjs/cmaps/', cMapPacked: true,
        standardFontDataUrl: '/static/vendor/pdfjs/standard_fonts/', stopAtErrors: true }).promise;
      status.textContent = 'Draw on the page, then save. The server checks this file against Drive before accepting pen marks.';
      await showPage();
    } catch (_) {
      status.textContent = 'This PDF could not be opened. Select a readable local copy.';
    }
  });

  function point(event) {
    const rect = overlay.getBoundingClientRect();
    return [Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)),
      Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height))];
  }
  overlay.addEventListener('pointerdown', event => {
    if (busy || !pdf) return;
    overlay.setPointerCapture(event.pointerId);
    active = [point(event)]; paint();
  });
  overlay.addEventListener('pointermove', event => {
    if (!active) return;
    active.push(point(event)); paint();
  });
  function finish(event) {
    if (!active) return;
    active.push(point(event));
    draft.push(active); active = null; paint();
  }
  overlay.addEventListener('pointerup', finish);
  overlay.addEventListener('pointercancel', () => { active = null; paint(); });
  document.getElementById('doc-ink-prev').addEventListener('click', () => { if (pageNumber > 1 && (!draft.length || confirm('Discard unsaved pen marks?'))) { pageNumber--; showPage(); } });
  document.getElementById('doc-ink-next').addEventListener('click', () => { if (pdf && pageNumber < Math.min(pdf.numPages, 500) && (!draft.length || confirm('Discard unsaved pen marks?'))) { pageNumber++; showPage(); } });
  document.getElementById('doc-ink-undo').addEventListener('click', () => { draft.pop(); paint(); });
  document.getElementById('doc-ink-clear').addEventListener('click', () => { draft = []; paint(); });
  document.getElementById('doc-ink-save').addEventListener('click', async () => {
    if (!pdf || !draft.length || busy) { status.textContent = 'Draw a mark before saving.'; return; }
    busy = true; status.textContent = 'Checking the Drive version and saving…';
    try {
      const response = await fetch(root.dataset.saveUrl, { method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ csrf: root.dataset.csrf, revision: root.dataset.revision,
          kind: 'ink', page_number: pageNumber, strokes: draft, source_sha256: digest }) });
      if (!response.ok) { status.textContent = (await response.text()).slice(0, 500); return; }
      location.reload();
    } catch (_) {
      status.textContent = 'The marks could not be saved. Check your connection and try again.';
    } finally { busy = false; }
  });
}
