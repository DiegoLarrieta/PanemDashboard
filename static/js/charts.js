// Chart.js theme tuned for the glass surfaces.
if (window.Chart) {
  const muted = 'rgba(247, 244, 238, 0.65)';
  const grid  = 'rgba(255, 255, 255, 0.08)';
  Chart.defaults.color = muted;
  Chart.defaults.font.family = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif";
  Chart.defaults.font.size = 12;
  Chart.defaults.borderColor = grid;
  Chart.defaults.scale.grid.color = grid;
  Chart.defaults.scale.grid.tickColor = grid;
  Chart.defaults.scale.ticks.color = muted;
  Chart.defaults.plugins.legend.labels.color = muted;
  Chart.defaults.plugins.legend.labels.boxWidth = 10;
  Chart.defaults.plugins.legend.labels.usePointStyle = true;
  Chart.defaults.plugins.tooltip.backgroundColor = 'rgba(20,12,4,0.92)';
  Chart.defaults.plugins.tooltip.titleColor = '#fff';
  Chart.defaults.plugins.tooltip.bodyColor = '#f7f4ee';
  Chart.defaults.plugins.tooltip.borderColor = 'rgba(255,255,255,0.22)';
  Chart.defaults.plugins.tooltip.borderWidth = 1;
  Chart.defaults.plugins.tooltip.padding = 10;
  Chart.defaults.plugins.tooltip.cornerRadius = 10;
}

const C = {
  accent:   '#f0a04b',
  accent2:  '#9bcf6b',
  warn:     '#ff6b5a',
  muted:    'rgba(247,244,238,0.55)',
  band:     'rgba(240,160,75,0.18)',
  band2:    'rgba(155,207,107,0.18)',
};

function lineChart(ctx, labels, datasets, options) {
  return new Chart(ctx, {
    type: 'line',
    data: { labels, datasets },
    options: Object.assign({
      responsive: true,
      maintainAspectRatio: false,
      interaction: { intersect: false, mode: 'index' },
      elements: { point: { radius: 0, hoverRadius: 4 }, line: { tension: 0.3, borderWidth: 2.5 } },
      plugins: { legend: { display: datasets.length > 1, position: 'top', align: 'end' } },
      scales: { y: { beginAtZero: true } },
    }, options || {}),
  });
}

function barChart(ctx, labels, datasets, options) {
  return new Chart(ctx, {
    type: 'bar',
    data: { labels, datasets },
    options: Object.assign({
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: datasets.length > 1, position: 'top', align: 'end' } },
      scales: { y: { beginAtZero: true } },
      borderRadius: 6,
    }, options || {}),
  });
}

function scatterChart(ctx, datasets, options) {
  return new Chart(ctx, {
    type: 'scatter',
    data: { datasets },
    options: Object.assign({
      responsive: true,
      maintainAspectRatio: false,
      elements: { point: { radius: 4, hoverRadius: 6 } },
      plugins: { legend: { display: datasets.length > 1, position: 'top', align: 'end' } },
      scales: { y: { beginAtZero: true }, x: { beginAtZero: true } },
    }, options || {}),
  });
}

function histChart(ctx, bins, counts, options) {
  return new Chart(ctx, {
    type: 'bar',
    data: {
      labels: bins,
      datasets: [{ data: counts, backgroundColor: C.accent, borderRadius: 4 }],
    },
    options: Object.assign({
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: { x: { grid: { display: false } }, y: { beginAtZero: true } },
    }, options || {}),
  });
}
