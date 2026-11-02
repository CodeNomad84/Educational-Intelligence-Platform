/* Shared chart defaults of the design system (P8-3) on the self-hosted Chart.js. Data comes from json_script tags. ISO date
   labels are shown in the Persian calendar by the browser (Intl, fa-IR). A null value (withheld or empty) is a gap, never 0. */
(function () {
  const css = getComputedStyle(document.documentElement);
  const token = (name, fallback) => (css.getPropertyValue(name) || fallback).trim();
  const fmt = new Intl.DateTimeFormat('fa-IR-u-ca-persian', { month: 'short', day: 'numeric' });
  const label = l => (/^\d{4}-\d{2}-\d{2}$/.test(l) ? fmt.format(new Date(l + 'T12:00:00')) : l);
  const read = id => JSON.parse(document.getElementById(id).textContent);
  if (window.Chart) {
    Chart.defaults.font.family = token('--eip-font', 'Tahoma');
    Chart.defaults.color = token('--eip-muted', '#6b7686');
    Chart.defaults.borderColor = token('--eip-border', '#e3e8ef');
    Chart.defaults.plugins.legend.display = false;
    Chart.defaults.maintainAspectRatio = false;
  }
  function chart(type, canvasId, dataId, opts = {}) {
    const el = document.getElementById(canvasId);
    if (!el || !window.Chart) return null;
    const d = read(dataId);
    const color = opts.color || token('--eip-primary', '#2457b8');
    const ds = type === 'line'
      ? { data: d.values, borderColor: color, backgroundColor: color + '1f', fill: true, tension: .3, pointRadius: 3, pointBackgroundColor: color }
      : { data: d.values, backgroundColor: color, borderRadius: 6, maxBarThickness: 42 };
    const suffix = opts.suffix || '';
    if (opts.fit) {   // y axis fitted to the data range (with padding), never beyond the natural bounds
      const v = d.values.filter(x => x !== null);
      if (v.length) {
        const pad = Math.max(1, (Math.max(...v) - Math.min(...v)) * 0.25);
        opts = Object.assign({}, opts, { min: Math.max(opts.min ?? -Infinity, Math.floor(Math.min(...v) - pad)), max: Math.min(opts.max ?? Infinity, Math.ceil(Math.max(...v) + pad)) });
      }
    }
    return new Chart(el, {
      type, data: { labels: d.labels.map(label), datasets: [ds] },
      options: {
        scales: { y: { min: opts.min, max: opts.max, beginAtZero: type === 'bar', ticks: { callback: v => v + suffix } }, x: { grid: { display: false } } },
        plugins: { tooltip: { rtl: true, callbacks: { label: c => (c.parsed.y === null ? '—' : c.parsed.y + suffix) } } },
      },
    });
  }
  window.EipCharts = { line: (c, d, o) => chart('line', c, d, o), bars: (c, d, o) => chart('bar', c, d, o), label };
})();
