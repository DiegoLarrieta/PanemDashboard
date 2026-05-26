// Page 3 — Model card logic.
(function () {
  const el = (id) => document.getElementById(id);

  async function loadCard() {
    const data = await api.get('/api/model/card');
    el('sumAlgo').textContent = data.summary.algorithm;
    el('sumData').textContent = data.summary.training_data;
    el('sumVal').textContent = data.summary.validation;
    el('sumBaseline').textContent = data.summary.baseline;
    el('sumRetrain').textContent = data.summary.last_retrain
      ? new Date(data.summary.last_retrain).toLocaleString() : '—';
    el('sumActuals').textContent = data.summary.trained_on_actuals_count.toLocaleString();
    el('versionLabel').textContent = data.summary.model_version ? `version ${data.summary.model_version}` : '—';
    el('sumFeatures').innerHTML = data.summary.features.map(f =>
      `<code style="display:inline-block; margin: 2px 6px 2px 0; padding: 2px 8px; background: rgba(255,255,255,0.08); border-radius: 6px;">${f}</code>`
    ).join('');
    el('metricsBody').innerHTML = data.metrics.map(m => `
      <tr>
        <td><strong>${m.algorithm}</strong></td>
        <td class="num tabular">${m.mae.toFixed(2)}</td>
        <td class="num tabular">${m.rmse.toFixed(2)}</td>
        <td class="num tabular">${m.mape.toFixed(1)}%</td>
        <td class="num tabular">${m.acc_20pct.toFixed(1)}%</td>
        <td>${m.beats_baseline ? '<span class="chip ok">yes</span>' : '<span class="chip muted">no</span>'}</td>
        <td>${m.is_active ? '<span class="chip ok">active</span>' : ''}</td>
      </tr>
    `).join('');
    el('limBox').innerHTML = data.limitations.map(l => `
      <div><h4>${l.title}</h4><p class="muted" style="margin:0;">${l.body}</p></div>
    `).join('');
  }

  async function loadCharts() {
    try {
      const b = await api.get('/api/model/mae-by-bucket');
      const ctx = document.getElementById('chartBucket').getContext('2d');
      barChart(ctx, b.buckets, [
        { label: 'Prophet', data: b.prophet, backgroundColor: C.accent },
        { label: 'Naive',   data: b.naive,   backgroundColor: 'rgba(255,255,255,0.2)' },
      ]);
    } catch (e) {}

    try {
      const r = await api.get('/api/model/residuals');
      const ctx = document.getElementById('chartResid').getContext('2d');
      histChart(ctx, r.bins, r.counts);
      el('residStats').textContent = r.n
        ? `n=${r.n}  ·  mean=${r.mean}  ·  σ=${r.std}`
        : 'No actuals recorded yet — log end-of-day sales on the Bake Plan page to populate this.';
    } catch (e) {}

    try {
      const d = await api.get('/api/model/error-over-time');
      const ctx = document.getElementById('chartDrift').getContext('2d');
      const driftLine = d.labels.map(() => null);
      lineChart(ctx, d.labels, [
        { label: '14-day rolling MAE', data: d.mae, borderColor: C.accent, backgroundColor: C.band, fill: true },
      ]);
    } catch (e) {}
  }

  async function loadRuns() {
    try {
      const data = await api.get('/api/model/runs');
      el('runsBody').innerHTML = data.runs.map(r => `
        <tr>
          <td>${r.model_version}</td>
          <td>${r.algorithm}</td>
          <td class="num tabular">${r.mae.toFixed(2)}</td>
          <td class="num tabular">${r.mape.toFixed(1)}%</td>
          <td class="num tabular">${r.acc_20pct.toFixed(1)}%</td>
          <td class="muted">${new Date(r.trained_at).toLocaleString()}</td>
          <td>${r.is_active ? '<span class="chip ok">active</span>' :
                 (r.promoted_at ? '<span class="chip muted">retired</span>' : '<span class="chip muted">shadow</span>')}</td>
          <td class="num tabular">${r.trained_on_actuals_count.toLocaleString()}</td>
        </tr>
      `).join('') || '<tr><td colspan="8" class="muted">No runs yet.</td></tr>';
    } catch (e) {}
  }

  // Retrain
  el('retrainBtn').addEventListener('click', async () => {
    if (!confirm('Retrain Prophet + LightGBM on the latest data including operator actuals?')) return;
    try {
      await api.post('/api/retrain', { top_n: 5 });
      el('retrainModal').style.display = 'flex';
      pollRetrain();
    } catch (e) { toast('Retrain failed: ' + e.message, 'warn'); }
  });
  el('closeRetrain').addEventListener('click', () => {
    el('retrainModal').style.display = 'none';
    loadCard(); loadCharts(); loadRuns();
  });

  async function pollRetrain() {
    try {
      const s = await api.get('/api/retrain/status');
      el('retrainLog').textContent = s.log || '…starting…';
      if (s.running) {
        setTimeout(pollRetrain, 2500);
      } else {
        el('retrainLog').textContent += `\n\n[${s.last_status}]`;
        toast('Retrain finished', s.last_status === 'ok' ? 'ok' : 'warn');
      }
    } catch (e) { /* ignore */ }
  }

  loadCard(); loadCharts(); loadRuns();
})();
