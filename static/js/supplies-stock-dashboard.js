/* Optional charts over server-rendered, authorized aggregate counts. */
(() => {
  'use strict';
  const root = document.getElementById('stock-dashboard');
  if (!root) return;
  const status = document.getElementById('stock-chart-status');
  if (typeof window.echarts?.init !== 'function') return;
  const charts = [];
  try {
    const data = JSON.parse(document.getElementById('stock-dashboard-data').textContent);
    const color = getComputedStyle(root).getPropertyValue('--ink').trim() || '#172b40';
    for (const key of ['physical', 'availability']) {
      const entries = data[key];
      if (!entries.some(row => row.count)) continue;
      const element = document.getElementById(`stock-${key}-chart`);
      element.hidden = false;
      element.style.height = `${Math.max(260, entries.length * 36 + 55)}px`;
      const chart = window.echarts.init(element, null, {renderer: 'svg'});
      charts.push(chart);
      chart.setOption({
        animation: false, textStyle: {color},
        grid: {left: 12, right: 45, top: 15, bottom: 25, containLabel: true},
        tooltip: {show: false},
        xAxis: {type: 'value', minInterval: 1, axisLabel: {color}},
        yAxis: {type: 'category', inverse: true, data: entries.map(row => row.label),
          axisLabel: {color, width: 150, overflow: 'truncate'}},
        series: [{type: 'bar', data: entries.map(row => row.count), barMaxWidth: 24,
          itemStyle: {color: '#287a60'}, label: {show: true, position: 'right', color}}],
      });
      chart.on('click', event => {
        const row = entries[event.dataIndex];
        if (!row?.count || !row.href) return;
        const target = new URL(row.href, window.location.origin);
        if (target.origin === window.location.origin && target.pathname === '/supplies/items') window.location.assign(target);
      });
    }
    status.textContent = charts.length ? 'Charts loaded. Select a bar or use the linked count tables to open matching records.' : 'No matching records. The count tables show the current result.';
    const observer = new ResizeObserver(() => charts.forEach(chart => chart.resize()));
    observer.observe(root);
    window.addEventListener('pagehide', event => {
      if (!event.persisted) { observer.disconnect(); charts.forEach(chart => chart.dispose()); }
    });
    window.addEventListener('pageshow', event => { if (event.persisted) window.location.reload(); });
  } catch (error) {
    charts.forEach(chart => chart.dispose());
    for (const element of root.querySelectorAll('.dashboard-chart')) element.hidden = true;
    status.textContent = 'Charts could not load. Use the linked count tables below.';
  }
})();
