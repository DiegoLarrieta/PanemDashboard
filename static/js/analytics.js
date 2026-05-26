// Analytics page — Page 4
// Depends on api.js and charts.js being loaded first.

// -----------------------------------------------------------------------
// Branch palette
// -----------------------------------------------------------------------
const BRANCH_PALETTE = [
  '#f0a04b', '#9bcf6b', '#ff9eb5', '#7ecfff',
  '#c49bff', '#ffdc6b', '#ff8c42',
];
function branchColor(idx) { return BRANCH_PALETTE[idx % BRANCH_PALETTE.length]; }

// -----------------------------------------------------------------------
// Chart instances
// -----------------------------------------------------------------------
const charts = {};
function destroyChart(key) {
  if (charts[key]) { charts[key].destroy(); charts[key] = null; }
}

// -----------------------------------------------------------------------
// Global branch selector — single source of truth
// -----------------------------------------------------------------------
function getGlobalBranch() {
  return document.getElementById('globalBranch').value;
}

// -----------------------------------------------------------------------
// Helper: build query string
// -----------------------------------------------------------------------
function qs(params) {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== null && v !== undefined && v !== '') p.append(k, v);
  }
  const s = p.toString();
  return s ? '?' + s : '';
}

// -----------------------------------------------------------------------
// 1. Sales Over Time
// -----------------------------------------------------------------------
async function loadSalesOverTime() {
  const branch      = getGlobalBranch();
  const granularity = document.getElementById('sotGranularity').value;
  try {
    const data = await api.get('/api/analytics/sales-over-time' + qs({ branch, granularity }));
    destroyChart('sot');
    const ctx = document.getElementById('chartSalesOverTime').getContext('2d');
    const datasets = data.datasets.map((ds, i) => ({
      label: ds.branch,
      data: ds.data,
      borderColor: branchColor(i),
      backgroundColor: branchColor(i) + '22',
      fill: data.datasets.length === 1,
    }));
    charts['sot'] = lineChart(ctx, data.labels, datasets, {
      plugins: { legend: { display: data.datasets.length > 1, position: 'top', align: 'end' } },
    });
  } catch (e) { console.error('sales-over-time', e); }
}

// -----------------------------------------------------------------------
// 2. Top Products
// -----------------------------------------------------------------------
async function loadTopProducts() {
  const branch = getGlobalBranch();
  try {
    const data = await api.get('/api/analytics/top-products' + qs({ branch, top_n: 10 }));
    destroyChart('tp');
    const ctx = document.getElementById('chartTopProducts').getContext('2d');
    charts['tp'] = barChart(ctx, data.labels,
      [{ label: 'Total units sold', data: data.values, backgroundColor: C.accent, borderRadius: 6 }],
      { indexAxis: 'y', plugins: { legend: { display: false } },
        scales: { x: { beginAtZero: true }, y: { ticks: { font: { size: 11 } } } } }
    );
  } catch (e) { console.error('top-products', e); }
}

// -----------------------------------------------------------------------
// 3. Weekday Heatmap
// -----------------------------------------------------------------------
async function loadWeekdayHeatmap() {
  const branch = getGlobalBranch();
  try {
    const data = await api.get('/api/analytics/weekday-heatmap' + qs({ branch }));
    destroyChart('wd');
    const ctx = document.getElementById('chartWeekdayHeatmap').getContext('2d');
    const maxProducts = Math.min(data.products.length, 5);
    const datasets = data.products.slice(0, maxProducts).map((prod, i) => ({
      label: prod, data: data.matrix[i],
      backgroundColor: branchColor(i), borderRadius: 4,
    }));
    charts['wd'] = barChart(ctx, data.days, datasets, {
      plugins: { legend: { display: true, position: 'top', align: 'end' } },
      scales: { y: { beginAtZero: true } },
    });
  } catch (e) { console.error('weekday-heatmap', e); }
}

// -----------------------------------------------------------------------
// 4. Monthly Seasonality
// -----------------------------------------------------------------------
async function loadMonthlySeasonality() {
  const branch = getGlobalBranch();
  const sku    = document.getElementById('msSku').value;
  try {
    const data = await api.get('/api/analytics/monthly-seasonality' + qs({ branch, sku: sku || null }));
    destroyChart('ms');
    const ctx = document.getElementById('chartMonthlySeasonality').getContext('2d');
    charts['ms'] = barChart(ctx, data.labels,
      [{ label: 'Avg daily units', data: data.values, backgroundColor: C.accent2, borderRadius: 6 }],
      { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } }
    );
  } catch (e) { console.error('monthly-seasonality', e); }
}

// -----------------------------------------------------------------------
// 5. Weather Impact
// -----------------------------------------------------------------------
async function loadWeatherImpact() {
  const branch = getGlobalBranch();
  try {
    const data = await api.get('/api/analytics/weather-impact' + qs({ branch }));
    destroyChart('wi');
    const ctx = document.getElementById('chartWeatherImpact').getContext('2d');
    charts['wi'] = barChart(ctx, ['Cold', 'Mild', 'Warm'],
      [{ label: 'Avg daily units', data: [data.cold, data.mild, data.warm],
         backgroundColor: ['#7ecfff', C.accent2, C.accent], borderRadius: 6 }],
      { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } }
    );
  } catch (e) { console.error('weather-impact', e); }
}

// -----------------------------------------------------------------------
// 6. Holiday Effect
// -----------------------------------------------------------------------
async function loadHolidayImpact() {
  const branch = getGlobalBranch();
  try {
    const data = await api.get('/api/analytics/holiday-impact' + qs({ branch }));
    destroyChart('hi');
    const ctx = document.getElementById('chartHolidayImpact').getContext('2d');
    charts['hi'] = barChart(ctx, data.labels,
      [{ label: 'Avg daily units', data: data.values,
         backgroundColor: [C.muted, '#c49bff', C.warn], borderRadius: 6 }],
      { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } }
    );
  } catch (e) { console.error('holiday-impact', e); }
}

// -----------------------------------------------------------------------
// Reload ALL charts with current global branch
// -----------------------------------------------------------------------
function reloadAll() {
  const label = document.getElementById('globalBranch');
  const display = document.getElementById('activeBranchLabel');
  if (display) display.textContent = label.options[label.selectedIndex].text;

  return Promise.all([
    loadSalesOverTime(),
    loadTopProducts(),
    loadWeekdayHeatmap(),
    loadMonthlySeasonality(),
    loadWeatherImpact(),
    loadHolidayImpact(),
  ]);
}

// -----------------------------------------------------------------------
// Populate SKU datalist
// -----------------------------------------------------------------------
async function populateSkuSelector() {
  const branch = getGlobalBranch();
  try {
    const data = await api.get('/api/analytics/top-products' + qs({ branch, top_n: 50 }));
    const datalist = document.getElementById('skuList');
    if (datalist && data.labels) {
      datalist.innerHTML = '';
      data.labels.forEach(name => {
        const opt = document.createElement('option');
        opt.value = name;
        datalist.appendChild(opt);
      });
    }
  } catch (e) { /* non-critical */ }
}

// -----------------------------------------------------------------------
// Wire up controls
// -----------------------------------------------------------------------
function bindControls() {
  // Global branch selector — reloads everything
  document.getElementById('globalBranch').addEventListener('change', async () => {
    await populateSkuSelector();
    document.getElementById('msSku').value = '';
    reloadAll();
  });

  // Per-chart local controls
  document.getElementById('sotGranularity').addEventListener('change', loadSalesOverTime);
  document.getElementById('msSku').addEventListener('change', loadMonthlySeasonality);
}

// -----------------------------------------------------------------------
// Heatmap (Plotly)
// -----------------------------------------------------------------------
let _hmView = 'monthly';

const HM_CAPTIONS = {
  monthly: 'Rows = months · Columns = years · Cell = total units sold',
  weekly:  'Rows = day of week · Columns = month · Cell = avg daily units',
  hourly:  'Rows = hour of day · Columns = day of week · Cell = total units sold',
};

function getHeatmapBranch() {
  return document.getElementById('hmBranch')?.value || 'all';
}

async function loadHeatmap() {
  const plot    = document.getElementById('hmPlot');
  const loading = document.getElementById('hmLoading');
  const empty   = document.getElementById('hmEmpty');
  const caption = document.getElementById('hmCaption');
  if (!plot) return;

  plot.style.display    = 'none';
  loading.style.display   = 'block';
  loading.textContent     = _hmView === 'hourly'
    ? 'Loading hourly data… (may take ~15s on first load)'
    : 'Loading heatmap…';
  empty.style.display   = 'none';
  caption.textContent   = HM_CAPTIONS[_hmView];

  // Show/hide month filter (only useful for hourly)
  document.getElementById('hmMonthWrap').style.display = _hmView === 'hourly' ? '' : 'none';

  const branch = getHeatmapBranch();
  const item   = document.getElementById('hmItem').value;
  const month  = document.getElementById('hmMonth').value;

  const params = new URLSearchParams({ view: _hmView, branch });
  if (item  !== 'all') params.set('item',  item);
  if (month !== 'all') params.set('month', month);

  try {
    const data = await api.get('/api/analytics/heatmap?' + params.toString());
    loading.style.display = 'none';

    const hasData = data.z && data.z.some(row => row.some(v => v > 0));
    if (!hasData) { empty.style.display = 'block'; return; }

    const trace = {
      type: 'heatmap',
      z: data.z,
      x: data.x,
      y: data.y,
      colorscale: [
        [0.00, '#ffffff'],
        [0.25, '#fde8c8'],
        [0.50, '#f5b96e'],
        [0.75, '#f0a04b'],
        [1.00, '#c96a00'],
      ],
      showscale: true,
      xgap: 2, ygap: 2,
      hoverongaps: false,
      colorbar: {
        tickfont: { color: '#f7f4ee', size: 11 },
        outlinewidth: 0,
        thickness: 14,
      },
      hovertemplate: '<b>%{y}</b> · %{x}<br>Units: <b>%{z:,.0f}</b><extra></extra>',
    };

    const layout = {
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor:  '#050300',
      font:  { color: '#f7f4ee', size: 12 },
      xaxis: { tickfont: { size: 11 }, gridcolor: 'rgba(255,255,255,0.06)', linecolor: 'transparent' },
      yaxis: { tickfont: { size: 11 }, gridcolor: 'rgba(255,255,255,0.06)', linecolor: 'transparent', autorange: 'reversed' },
      margin: { l: 70, r: 20, t: 10, b: 50 },
      height: 400,
    };

    plot.style.display = 'block';
    Plotly.react(plot, [trace], layout, { responsive: true, displayModeBar: false });
  } catch(e) {
    loading.style.display = 'none';
    empty.style.display   = 'block';
    console.error('heatmap', e);
  }
}

async function populateHeatmapItems() {
  const branch = getHeatmapBranch();
  try {
    const data = await api.get('/api/analytics/heatmap-items?' + new URLSearchParams({ branch }));
    const sel = document.getElementById('hmItem');
    const cur = sel.value;
    sel.innerHTML = '<option value="all">All products</option>';
    data.items.forEach(name => {
      const o = document.createElement('option');
      o.value = name; o.textContent = name;
      sel.appendChild(o);
    });
    // Restore selection if still valid
    if ([...sel.options].some(o => o.value === cur)) sel.value = cur;
  } catch(e) { /* non-critical */ }
}

function bindHeatmapControls() {
  // View toggle buttons
  document.querySelectorAll('.heatmap-view-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.heatmap-view-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      _hmView = btn.dataset.view;
      loadHeatmap();
    });
  });

  document.getElementById('hmBranch').addEventListener('change', async () => {
    await populateHeatmapItems();
    loadHeatmap();
  });
  document.getElementById('hmItem').addEventListener('change', loadHeatmap);
  document.getElementById('hmMonth').addEventListener('change', loadHeatmap);
}

// -----------------------------------------------------------------------
// Init
// -----------------------------------------------------------------------
(async function init() {
  bindControls();
  bindHeatmapControls();
  await populateSkuSelector();
  await populateHeatmapItems();
  await reloadAll();
  loadHeatmap();
})();
