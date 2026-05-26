// Page 2 — Product Deep-Dive logic.
(function () {
  const path = location.pathname;
  const sku = decodeURIComponent(path.split('/product/')[1] || '');
  const branch = new URLSearchParams(location.search).get('branch') || '';
  if (!sku || !branch) { location.href = '/'; return; }

  const els = {
    title: document.getElementById('prodTitle'),
    branch: document.getElementById('prodBranch'),
    skuLabel: document.getElementById('prodSku'),
    nextBake: document.getElementById('nextBake'),
    backBtn: document.getElementById('backBtn'),
    recoNumber: document.getElementById('recoNumber'),
    recoCI: document.getElementById('recoCI'),
    recoBaseline: document.getElementById('recoBaseline'),
    recoModel: document.getElementById('recoModel'),
    recoRetrain: document.getElementById('recoRetrain'),
    accept: document.getElementById('acceptBtn'),
    override: document.getElementById('overrideBtn'),
    similar: document.querySelector('#similarTable tbody'),
    overlay: document.getElementById('overlay'),
    ovSku: document.getElementById('ovSku'),
    ovUnits: document.getElementById('ovUnits'),
    ovReason: document.getElementById('ovReason'),
    ovNote: document.getElementById('ovNote'),
    ovCancel: document.getElementById('ovCancel'),
    ovSave: document.getElementById('ovSave'),
  };
  els.backBtn.href = `/?branch=${encodeURIComponent(branch)}`;
  els.skuLabel.textContent = sku;
  els.branch.textContent = branch;

  let forecastId = null;

  async function load() {
    const data = await api.get(`/api/product/${encodeURIComponent(sku)}/deep-dive?branch=${encodeURIComponent(branch)}`);
    els.title.textContent = data.item_name || sku;
    els.nextBake.textContent = fmt.date(data.next_bake);

    const r = data.recommendation;
    forecastId = r.forecast_id;
    els.recoNumber.textContent = fmt.int(r.predicted_units);
    // Label as 7-day total to match the plan page
    const weekRange = (r.week_start && r.week_end)
      ? ` · ${fmt.date(r.week_start)} – ${fmt.date(r.week_end)}`
      : '';
    els.recoCI.textContent = (r.ci_low != null)
      ? `80% CI: ${fmt.int(r.ci_low)} – ${fmt.int(r.ci_high)} units · 7-day total${weekRange}`
      : 'no prediction';
    els.recoBaseline.textContent = fmt.int(r.baseline_lag7);
    els.recoModel.textContent = r.model_version || '—';
    els.recoRetrain.textContent = r.last_retrain ? new Date(r.last_retrain).toLocaleDateString() : '—';

    // History
    {
      const ctx = document.getElementById('chartHistory').getContext('2d');
      lineChart(ctx, data.history_chart.labels, [{
        label: 'Units sold', data: data.history_chart.qty,
        borderColor: C.accent2, backgroundColor: C.band2, fill: true,
      }]);
    }
    // History + Forecast chart
    {
      const ctx = document.getElementById('chartFvA').getContext('2d');
      const fa = data.forecast_vs_actual;
      lineChart(ctx, fa.labels, [
        {
          label: 'Actual / Historical', data: fa.actual,
          borderColor: C.accent2, backgroundColor: C.band2, fill: true, spanGaps: false,
        },
        {
          label: 'Predicted (next week)', data: fa.predicted,
          borderColor: C.accent, backgroundColor: C.band,
          borderDash: [5, 3], spanGaps: false,
        },
        { label: 'CI high', data: fa.ci_high, borderColor: 'transparent', backgroundColor: 'rgba(240,160,75,0.12)', fill: '+1', pointRadius: 0, spanGaps: true },
        { label: 'CI low',  data: fa.ci_low,  borderColor: 'transparent', backgroundColor: 'rgba(240,160,75,0.12)', fill: false, pointRadius: 0, spanGaps: true },
      ], { plugins: { legend: { labels: { filter: i => !i.text.startsWith('CI') } } } });
    }
    // Seasonality
    {
      const ctx = document.getElementById('chartDow').getContext('2d');
      barChart(ctx, data.seasonality.labels, [{ data: data.seasonality.avg, backgroundColor: C.accent }]);
    }
    // Temperature response
    {
      const ctx = document.getElementById('chartTemp').getContext('2d');
      barChart(ctx, ['Cold days', 'Warm days'], [{
        data: [data.response.cold, data.response.warm],
        backgroundColor: ['#7aa9d9', '#f0a04b'],
      }]);
    }
    // Quincena
    {
      const ctx = document.getElementById('chartQ').getContext('2d');
      barChart(ctx, ['Payday', 'Other days'], [{
        data: [data.response.quincena, data.response.non_quincena],
        backgroundColor: [C.accent2, 'rgba(255,255,255,0.18)'],
      }]);
    }
    // Peers
    {
      const ctx = document.getElementById('chartPeers').getContext('2d');
      barChart(ctx, data.peers.labels, [{ data: data.peers.qty, backgroundColor: C.accent }],
        { indexAxis: 'y' });
    }
    // Similar
    els.similar.innerHTML = data.similar.map(s => `
      <tr><td>${s.sku}</td><td>${s.item_name || ''}</td><td class="num tabular">${s.r.toFixed(2)}</td></tr>
    `).join('') || `<tr><td colspan="3" class="muted">No comparable SKUs yet.</td></tr>`;
    // Revenue vs units
    {
      const ctx = document.getElementById('chartRev').getContext('2d');
      const datasets = [{
        label: 'Historical day',
        data: data.revenue_curve.points,
        backgroundColor: 'rgba(155,207,107,0.55)',
      }];
      if (data.revenue_curve.predicted) {
        datasets.push({
          label: 'Predicted bake',
          data: [data.revenue_curve.predicted],
          backgroundColor: C.accent,
          pointRadius: 8,
        });
      }
      scatterChart(ctx, datasets, {
        scales: {
          x: { title: { display: true, text: 'units sold' } },
          y: { title: { display: true, text: 'revenue (MXN)' } },
        },
      });
    }
  }

  els.accept.addEventListener('click', () => { toast('Recorded acceptance', 'ok'); });
  els.override.addEventListener('click', () => {
    if (!forecastId) { toast('No active forecast to override', 'warn'); return; }
    els.ovSku.textContent = sku;
    els.ovUnits.value = els.recoNumber.textContent;
    els.ovReason.value = 'gut_feel';
    els.ovNote.value = '';
    els.overlay.style.display = 'flex';
  });
  els.ovCancel.addEventListener('click', () => { els.overlay.style.display = 'none'; });
  els.ovSave.addEventListener('click', async () => {
    try {
      await api.post('/api/feedback/override', {
        forecast_id: forecastId,
        override_units: +els.ovUnits.value,
        reason: els.ovReason.value,
        note: els.ovNote.value,
      });
      els.overlay.style.display = 'none';
      toast('Override saved', 'ok');
    } catch (e) { toast('Save failed: ' + e.message, 'warn'); }
  });

  load().catch(e => toast('Load failed: ' + e.message, 'warn'));
})();
