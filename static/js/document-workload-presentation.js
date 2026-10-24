/* Editable presentations over fresh, authorized document aggregates. */
(() => {
  'use strict';
  const button = document.getElementById('workload-presentation-export');
  const status = document.getElementById('workload-presentation-status');
  const form = document.querySelector('#document-dashboard .dashboard-filters');
  if (!button || !status || !form) return;
  if (typeof window.PptxGenJS !== 'function' || typeof window.JSZip !== 'function') {
    status.textContent = 'PowerPoint export could not load. Refresh to retry; dashboard tables remain available.';
    return;
  }
  const applied = new URLSearchParams(new FormData(form));
  button.disabled = false;
  status.textContent = 'Export includes fresh counts and complete count tables, up to 1,000 lead groups. Apply changed filters with Refresh dashboard first.';
  button.addEventListener('click', async () => {
    button.disabled = true;
    status.textContent = 'Preparing PowerPoint report…';
    try {
      const response = await fetch(`/documents/dashboard/presentation-data?${applied}`, {
        credentials: 'same-origin', cache: 'no-store', headers: {Accept: 'application/json'},
      });
      if (response.redirected) throw new Error('Sign in again and refresh the dashboard before exporting.');
      if (!response.headers.get('content-type')?.includes('application/json')) {
        throw new Error('The report could not load. Refresh the dashboard and retry.');
      }
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'The report could not be read. Refresh and retry.');
      const pptx = new window.PptxGenJS();
      pptx.layout = 'LAYOUT_WIDE';
      pptx.author = 'Office Connect';
      pptx.company = 'Office Connect';
      pptx.title = 'Document workload report';
      pptx.subject = 'Document workload dashboard snapshot';
      pptx.lang = 'en-PH';
      pptx.theme = {headFontFace: 'Arial', bodyFontFace: 'Arial', lang: 'en-PH'};
      pptx.defineSlideMaster({title: 'WORKLOAD', background: {color: 'FFFFFF'}, objects: [
        {text: {text: `Office Connect • Snapshot ${data.as_of}`, options: {
          x: 0.5, y: 7.1, w: 11.8, h: 0.22, fontSize: 9, color: '526477', margin: 0,
        }}},
      ], slideNumber: {x: 12.35, y: 7.1, w: 0.4, h: 0.22, fontSize: 9, color: '526477'}});
      function slide(title) {
        const target = pptx.addSlide({masterName: 'WORKLOAD'});
        target.addText(title, {x: 0.5, y: 0.3, w: 12.2, h: 0.55, fontSize: 25, bold: true, color: '172B40', margin: 0});
        return target;
      }
      function text(target, value, y, h, fontSize = 16) {
        target.addText(value, {x: 0.5, y, w: 12.2, h, fontSize, color: '172B40', margin: 0});
      }
      const cover = slide('Document workload report');
      text(cover, `${data.total} matching documents • ${data.leads.length} lead groups`, 1.2, 0.6, 22);
      text(cover, `Queue: ${data.queue_label}\nApplied search: ${data.scope.q || 'All permitted records'}\nSnapshot: ${data.as_of}`, 2.05, 1.9);
      text(cover, `Overdue: before ${data.today}. Due soon includes today through ${data.soon}, the next three working days.\nUnknown or invalid deadlines are not overdue. Closed/cancelled documents have no urgency alert.\nCounts describe documents assigned to leads, not individual contributions or performance.`, 4.2, 1.8, 15);
      const dimensions = [
        ['workflow', 'Workflow stages', 'Current workflow stages across all matching pages.'],
        ['deadlines', 'Deadlines', `Five non-overlapping groups. Due soon: ${data.today} through ${data.soon}, including today.`],
        ['leads', 'Workload by assigned lead', `Chart: largest ${Math.min(data.chart_lead_limit, data.leads.length)} of ${data.leads.length} lead groups. Complete counts follow in tables. Unresolved includes missing assignments.`],
      ];
      for (const [key, title, note] of dimensions) {
        const target = slide(title);
        const entries = key === 'leads' ? data[key].slice(0, data.chart_lead_limit) : data[key];
        if (entries.some(row => row.count)) {
          target.addChart(pptx.ChartType.bar, [{name: 'Documents', labels: entries.map(row => {
            const label = String(row.label);
            return label.length > 55 ? `${label.slice(0, 54)}…` : label;
          }), values: entries.map(row => row.count)}], {
            x: 0.55, y: 1.1, w: 12.1, h: 4.6, barDir: 'bar',
            catAxisLabelFontSize: key === 'leads' ? 10 : 13, valAxisLabelFontSize: 12,
            valAxisMinVal: 0, valAxisMajorUnit: Math.max(1, Math.ceil(Math.max(...entries.map(row => row.count)) / 5)),
            showValue: true, showLegend: false, showTitle: false, showCatName: false,
            dataLabelPosition: 'outEnd', dataLabelFormatCode: '0', showBorder: false,
            chartColors: ['287A60'], showShadow: false,
          });
        } else text(target, 'No matching documents.', 1.5, 0.8, 22);
        text(target, `${note}\nLong chart labels may be shortened; tables retain full labels. Counts describe documents, not staff performance.`, 6.0, 0.85, 12);
      }
      for (const [key, title] of dimensions) {
        const target = slide(`${title} — complete counts`);
        const entries = data[key];
        if (!entries.length) {
          text(target, 'No matching documents.', 1.3, 0.8, 20);
          continue;
        }
        const rows = [[key === 'leads' ? 'Lead' : 'State', 'Documents'].map(value => ({
          text: value, options: {bold: true, color: 'FFFFFF', fill: '287A60'},
        })), ...entries.map(row => [String(row.label), String(row.count)])];
        target.addTable(rows, {x: 0.5, y: 1.15, w: 12.25, h: 5.65, colW: [10.0, 2.25],
          fontFace: 'Arial', fontSize: 12, color: '172B40', margin: 0.07,
          border: {type: 'solid', color: 'D1D9E0', pt: 0.5}, valign: 'top',
          autoPage: true, autoPageRepeatHeader: true, autoPageHeaderRows: 1,
          autoPageSlideStartY: 0.5, newSlideStartY: 0.5, verbose: false,
        });
      }
      await pptx.writeFile({fileName: 'office-connect-document-workload-report.pptx', compression: true});
      status.textContent = `PowerPoint report downloaded: ${data.total} matching documents and ${data.leads.length} lead groups. Snapshot ${data.as_of}.`;
    } catch (error) {
      status.textContent = `${error.message || 'PowerPoint export failed.'} Dashboard tables remain available; refresh and retry.`;
    } finally {
      button.disabled = false;
    }
  });
})();
