/* Editable PowerPoint reports from a fresh, authorized stock snapshot. */
(() => {
  'use strict';
  const button = document.getElementById('stock-presentation-export');
  const status = document.getElementById('stock-presentation-status');
  const form = document.querySelector('#stock-dashboard .dashboard-filters');
  if (!button || !status || !form) return;
  if (typeof window.PptxGenJS !== 'function' || typeof window.JSZip !== 'function') {
    status.textContent = 'PowerPoint export could not load. Refresh to retry; dashboard tables remain available.';
    return;
  }
  // Capture applied scope from the rendered form before users edit draft filters.
  const applied = new URLSearchParams(new FormData(form));
  button.disabled = false;
  status.textContent = 'Export includes fresh counts and all matching below-critical items, up to 1,000. Apply changed filters with Refresh dashboard first.';
  button.addEventListener('click', async () => {
    button.disabled = true;
    status.textContent = 'Preparing PowerPoint report…';
    try {
      const response = await fetch(`/supplies/stock-dashboard/presentation-data?${applied}`, {
        credentials: 'same-origin', cache: 'no-store', headers: {Accept: 'application/json'},
      });
      if (response.redirected || !response.headers.get('content-type')?.includes('application/json')) {
        throw new Error('Sign in again and refresh the dashboard before exporting.');
      }
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'The report could not be read. Refresh and retry.');
      const pptx = new window.PptxGenJS();
      pptx.layout = 'LAYOUT_WIDE';
      pptx.author = 'Office Connect';
      pptx.subject = 'Supplies stock dashboard snapshot';
      pptx.title = 'Supplies stock report';
      pptx.company = 'Office Connect';
      pptx.lang = 'en-PH';
      pptx.theme = {headFontFace: 'Arial', bodyFontFace: 'Arial', lang: 'en-PH'};
      pptx.defineSlideMaster({title: 'STOCK', background: {color: 'FFFFFF'}, objects: [
        {text: {text: `Office Connect • Snapshot ${data.as_of}`, options: {
          x: 0.5, y: 7.1, w: 11.8, h: 0.22, fontSize: 9, color: '526477', margin: 0,
        }}},
      ], slideNumber: {x: 12.35, y: 7.1, w: 0.4, h: 0.22, fontSize: 9, color: '526477'}});
      function slide(title) {
        const result = pptx.addSlide({masterName: 'STOCK'});
        result.addText(title, {x: 0.5, y: 0.3, w: 12.2, h: 0.55, fontSize: 25, bold: true, color: '172B40', margin: 0});
        return result;
      }
      function text(target, value, y, h, fontSize = 16) {
        target.addText(value, {x: 0.5, y, w: 12.2, h, fontSize, color: '172B40', margin: 0});
      }
      const cover = slide('Supplies stock report');
      const catalog = {active: 'Active items', all: 'Include inactive items', inactive: 'Inactive items only'};
      text(cover, `${data.total} matching catalog items • ${data.low_count} below critical level`, 1.2, 0.6, 22);
      text(cover, `Applied search: ${data.scope.q || 'All items'}\nUnit: ${data.scope.unit || 'All units'}\nCatalog: ${catalog[data.scope.active]}\nSnapshot: ${data.as_of}`, 2.05, 2.1);
      text(cover, 'Counts are items, not sums of quantities across different units.\nBelow-critical tables include every matching recorded active item with on-hand stock strictly below its critical level.\nTargets are existing catalog settings, not purchase recommendations.', 4.55, 1.5, 15);
      for (const [key, title, note] of [
        ['physical', 'Physical stock', 'Unrecorded stock is not a confirmed zero. Critical means positive on-hand stock below the critical level.'],
        ['availability', 'Availability after reservations', 'Availability is on hand minus reserved. Fully reserved means positive stock with zero availability. Low available is positive availability below critical.'],
      ]) {
        const target = slide(title);
        const entries = data[key];
        if (data.total) {
          target.addChart(pptx.ChartType.bar, [{name: 'Catalog items', labels: entries.map(row => row.label), values: entries.map(row => row.count)}], {
            x: 0.55, y: 1.1, w: 12.1, h: 4.6, barDir: 'bar', catAxisLabelFontSize: 14,
            valAxisLabelFontSize: 12, valAxisMinVal: 0, valAxisMajorUnit: Math.max(1, Math.ceil(data.total / 5)),
            showValue: true, showLegend: false, showTitle: false, showCatName: false,
            dataLabelPosition: 'outEnd', dataLabelFormatCode: '0', showBorder: false,
            chartColors: ['287A60'], showShadow: false,
          });
        } else text(target, 'No matching catalog items.', 1.5, 0.8, 22);
        text(target, `${note}\nEquality with the critical level is not low. Inactive items are counted separately. Counts cover all matching pages.`, 6.0, 0.8, 13);
      }
      const low = slide('Recorded active items below critical level');
      if (!data.low_items.length) {
        text(low, 'No recorded active items below their critical level match this scope.', 1.3, 1.0, 20);
      } else {
        // Native tables retain exact decimal strings. Auto-pagination repeats column headers.
        const rows = [['Item', 'Unit', 'On hand', 'Reserved', 'Available', 'Critical', 'Target'].map(value => ({
          text: value, options: {bold: true, color: 'FFFFFF', fill: '287A60'},
        })), ...data.low_items.map(item => [
          `${item.code} — ${item.description}`, item.unit, item.on_hand, item.reserved,
          item.available, item.critical_level, item.target_level ?? 'Not set',
        ])];
        low.addTable(rows, {x: 0.5, y: 1.15, w: 12.25, h: 5.65,
          colW: [4.0, 1.25, 1.4, 1.4, 1.4, 1.4, 1.4],
          fontFace: 'Arial', fontSize: 11, color: '172B40', margin: 0.07,
          border: {type: 'solid', color: 'D1D9E0', pt: 0.5}, valign: 'top',
          autoPage: true, autoPageRepeatHeader: true, autoPageHeaderRows: 1,
          autoPageSlideStartY: 0.5, newSlideStartY: 0.5, verbose: false,
        });
      }
      await pptx.writeFile({fileName: 'office-connect-supplies-stock-report.pptx', compression: true});
      status.textContent = `PowerPoint report downloaded: ${data.total} matching items and ${data.low_count} below-critical items. Snapshot ${data.as_of}.`;
    } catch (error) {
      status.textContent = error.message || 'PowerPoint export failed. Refresh and retry; dashboard tables remain available.';
    } finally {
      button.disabled = false;
    }
  });
})();
