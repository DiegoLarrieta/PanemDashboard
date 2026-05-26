// Page 1 — Today's Bake Plan logic.
(function () {
  const els = {
    branch: document.getElementById('branch'),
    bakeDate: document.getElementById('bakeDate'),
    confSlider: document.getElementById('confSlider'),
    table: document.querySelector('#planTable tbody'),
    actionHead: document.getElementById('actionHead'),
    emptyHint: document.getElementById('emptyHint'),
    title: document.getElementById('pageTitle'),
    branchLabel: document.getElementById('branchLabel'),
    dateLabel: document.getElementById('dateLabel'),
    modelVersion: document.getElementById('modelVersion'),
    modePill: document.getElementById('modePill'),
    lockBtn: document.getElementById('lockBtn'),
    actualsBtn: document.getElementById('actualsBtn'),
    genFcBtn: document.getElementById('genFcBtn'),
    bannerSlot: document.getElementById('bannerSlot'),
    kpiUnits: document.getElementById('kpiUnits'),
    kpiRevenue: document.getElementById('kpiRevenue'),
    kpiWaste: document.getElementById('kpiWaste'),
    kpiRisk: document.getElementById('kpiRisk'),
    overlay: document.getElementById('overlay'),
    ovSku: document.getElementById('ovSku'),
    ovUnits: document.getElementById('ovUnits'),
    ovReason: document.getElementById('ovReason'),
    ovNote: document.getElementById('ovNote'),
    ovCancel: document.getElementById('ovCancel'),
    ovSave: document.getElementById('ovSave'),
    ovDelete: document.getElementById('ovDelete'),
  };

  let charts = { byBranch: null, vsActual: null };
  let state = { rows: [], mode: 'plan', is_locked: false, editingForecastId: null };

  // Persist branch selection via URL.
  const url = new URL(location.href);
  const initialBranch = url.searchParams.get('branch');
  if (initialBranch) els.branch.value = initialBranch;
  const initialDate = url.searchParams.get('bake_date');
  if (initialDate) els.bakeDate.value = initialDate;

  function syncUrl() {
    const u = new URL(location.href);
    u.searchParams.set('branch', els.branch.value);
    u.searchParams.set('bake_date', els.bakeDate.value);
    history.replaceState(null, '', u);
  }

  function setMode(mode, isLocked) {
    state.mode = mode; state.is_locked = isLocked;
    const pill = els.modePill;
    pill.className = 'modepill ' + mode;
    pill.querySelector('.text').textContent =
      mode === 'plan' ? 'Plan' : mode === 'locked' ? 'Locked' : 'Actuals';
    els.actionHead.textContent =
      mode === 'actuals' ? 'Actuals' :
      mode === 'locked'  ? 'Locked' : 'Override';
    els.lockBtn.disabled = mode !== 'plan';
    els.lockBtn.textContent = isLocked ? 'Plan locked' : 'Lock plan & send to oven';
    if (isLocked) els.lockBtn.classList.remove('btn--primary');
    else els.lockBtn.classList.add('btn--primary');
  }

  function actionCell(row) {
    if (state.mode === 'plan') {
      const cur = row.override != null ? row.override : '';
      const changedClass = row.override != null ? ' changed' : '';
      return `<input class="override-input${changedClass}" type="number" min="0" step="1"
                 data-fid="${row.id}" value="${cur}" placeholder="${Math.round(row.predicted_units)}">
              <button class="btn btn--ghost" style="padding:4px 10px;font-size:11px;"
                      data-fid="${row.id}" data-act="reason">${row.override_reason || 'reason'}</button>`;
    } else if (state.mode === 'actuals') {
      return `<button class="btn btn--ghost" style="padding:4px 12px;font-size:11px;"
                data-act="log-actuals" data-sku="${row.sku}" data-branch="${row.branch}"
                data-week-start="${row.week_start}" data-week-end="${row.week_end}">
                📋 Log daily
              </button>`;
    }
    return `<span class="chip muted">—</span>`;
  }

  function risk(row) {
    // Stock-out risk: last week's total > lower bound of next-week forecast
    return (row.last_week_total != null) && (row.last_week_total > row.next7_lo);
  }

  function renderTable(rows) {
    state.rows = rows;
    const minConf = +els.confSlider.value;
    const total = rows.length;
    const visible = rows.filter(r => {
      const denom = r.next7_pred || 1;
      const certaintyPct = Math.max(0, 100 * (1 - Math.max(0, r.next7_pred - r.next7_lo) / denom));
      return certaintyPct >= minConf;
    });
    els.emptyHint.style.display = total === 0 ? 'block' : 'none';
    els.table.innerHTML = visible.map(r => {
      const ci = `${Math.round(r.next7_lo)}–${Math.round(r.next7_hi)}`;
      const pred = r.override != null ? r.override : r.next7_pred;
      const lwt  = r.last_week_total != null ? Math.round(r.last_week_total) : '—';
      const delta = r.last_week_total != null
        ? Math.round(r.next7_pred - r.last_week_total)
        : null;
      const deltaChip = delta != null
        ? `<span class="chip ${delta >= 0 ? 'ok' : 'warn'}" style="margin-left:5px;vertical-align:middle;font-size:11px;">${delta >= 0 ? '+' : ''}${delta}</span>`
        : '';
      const overrideChip = r.override != null
        ? `<span class="chip ok" style="margin-left:5px;vertical-align:middle;font-size:11px;">overridden</span>`
        : '';
      return `<tr class="${risk(r) ? 'risk' : ''} ${state.mode !== 'plan' ? 'locked' : ''}" data-sku="${r.sku}" data-branch="${r.branch}">
        <td><strong>${r.sku}</strong></td>
        <td>${r.item_name || ''}</td>
        <td class="num">${lwt}</td>
        <td class="num" style="white-space:nowrap;"><strong>${Math.round(pred)}</strong>${deltaChip}${overrideChip}</td>
        <td class="num muted tabular">${ci}</td>
        <td class="num">${actionCell(r)}</td>
        <td><a class="muted" href="/product/${encodeURIComponent(r.sku)}?branch=${encodeURIComponent(r.branch)}">why? →</a></td>
      </tr>`;
    }).join('');
    bindRowHandlers();
  }

  function bindRowHandlers() {
    els.table.querySelectorAll('tr').forEach(tr => {
      tr.addEventListener('click', (e) => {
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'BUTTON' || e.target.tagName === 'A') return;
        const sku = tr.dataset.sku, branch = tr.dataset.branch;
        if (sku && branch) location.href = `/product/${encodeURIComponent(sku)}?branch=${encodeURIComponent(branch)}`;
      });
    });
    els.table.querySelectorAll('input.override-input[data-fid]').forEach(inp => {
      inp.addEventListener('change', async () => {
        const fid = +inp.dataset.fid;
        const row = state.rows.find(r => r.id === fid);
        if (!row) return;
        const v = inp.value === '' ? null : +inp.value;
        if (v === null) {
          await fetch(`/api/feedback/override/${fid}`, { method: 'DELETE', credentials: 'same-origin' });
          row.override = null; row.override_reason = null;
          toast('Override cleared', 'info');
        } else {
          state.editingForecastId = fid;
          state.editingUnits = v;
          openOverrideModal(row);
        }
      });
    });
    els.table.querySelectorAll('button[data-act="reason"]').forEach(btn => {
      btn.addEventListener('click', () => {
        const fid = +btn.dataset.fid;
        const row = state.rows.find(r => r.id === fid);
        if (row) { state.editingForecastId = fid; state.editingUnits = row.override ?? row.predicted_units; openOverrideModal(row); }
      });
    });
  }

  // ── Actuals modal ──────────────────────────────────────────────────────
  let acState = { weekRows: [], weekActuals: {}, datesLogged: [], selectedDate: null };

  async function openActualsModal() {
    // Use the current week from state.rows
    if (!state.rows.length) return;
    const weekStart = state.rows[0].week_start;
    const weekEnd   = state.rows[0].week_end;
    const branch    = els.branch.value;

    // Fetch already-logged actuals for the week
    let acData = { actuals: {}, dates_logged: [] };
    try {
      acData = await api.get(`/api/feedback/actuals?branch=${encodeURIComponent(branch)}&week_start=${weekStart}&week_end=${weekEnd}`);
    } catch(e) {}

    acState.weekRows    = state.rows;
    acState.weekActuals = acData.actuals;
    acState.datesLogged = acData.dates_logged;

    // Default to today if today is in the week, else first day of week
    const todayStr = new Date().toISOString().slice(0,10);
    const days = [];
    let d = new Date(weekStart + 'T12:00:00');
    const end = new Date(weekEnd + 'T12:00:00');
    while (d <= end) { days.push(d.toISOString().slice(0,10)); d.setDate(d.getDate()+1); }

    acState.selectedDate = days.includes(todayStr) ? todayStr : days[0];

    renderDayStrip(days);
    renderActualsTable();
    document.getElementById('actualsOverlay').style.display = 'flex';
  }

  function renderDayStrip(days) {
    const strip = document.getElementById('acDayStrip');
    const DAY_NAMES = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
    strip.innerHTML = days.map(d => {
      const dt = new Date(d + 'T12:00:00');
      const name = DAY_NAMES[dt.getDay()];
      const num  = dt.getDate();
      const done = acState.datesLogged.includes(d);
      const active = d === acState.selectedDate;
      return `<button class="day-pill ${active ? 'active' : ''} ${done ? 'done' : ''}" data-date="${d}"
        style="padding:6px 12px; border-radius:20px; border:1px solid var(--glass-border);
               background:${active ? 'var(--accent)' : done ? 'rgba(155,207,107,0.15)' : 'var(--glass-bg)'};
               color:${active ? '#000' : 'var(--ink)'}; cursor:pointer; font-size:12px; display:flex; flex-direction:column; align-items:center; gap:2px;">
        <span style="font-weight:600;">${name}</span>
        <span>${num}</span>
        ${done ? '<span style="font-size:9px; color:var(--ok);">✓</span>' : '<span style="font-size:9px; color:var(--muted);">○</span>'}
      </button>`;
    }).join('');
    strip.querySelectorAll('.day-pill').forEach(btn => {
      btn.addEventListener('click', () => {
        acState.selectedDate = btn.dataset.date;
        // Rebuild strip to update active state
        renderDayStrip(days);
        renderActualsTable();
      });
    });
  }

  function renderActualsTable() {
    const d = acState.selectedDate;
    const dt = new Date(d + 'T12:00:00');
    const DAY_NAMES = ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];
    document.getElementById('acSelectedLabel').textContent =
      `${DAY_NAMES[dt.getDay()]} ${d}`;

    const tbody = document.getElementById('acSkuRows');
    tbody.innerHTML = acState.weekRows.map(row => {
      // Find forecast for this specific day
      const dayFc = row.daily ? row.daily.find(x => x.date === d) : null;
      const pred = dayFc ? dayFc.pred : '—';
      const key  = `${row.sku}|${d}`;
      const existing = acState.weekActuals[key];
      const soldVal   = existing ? existing.qty_sold   : '';
      const wastedVal = existing ? existing.qty_wasted : '';
      const logged = !!existing;
      return `<tr style="border-bottom:1px solid rgba(255,255,255,0.06);">
        <td style="padding:8px 0; font-size:13px; ${logged ? 'color:var(--ok)' : ''}">${row.item_name || row.sku}${logged ? ' ✓' : ''}</td>
        <td style="text-align:right; padding:8px; font-size:13px; color:var(--muted);">${pred}</td>
        <td style="text-align:right; padding:4px 8px;">
          <input type="number" min="0" step="1" value="${soldVal}"
                 data-sku="${row.sku}" data-type="sold"
                 style="width:70px; text-align:right; background:var(--glass-bg); border:1px solid var(--glass-border); border-radius:6px; color:var(--ink); padding:4px 6px;">
        </td>
        <td style="text-align:right; padding:4px 0;">
          <input type="number" min="0" step="1" value="${wastedVal}"
                 data-sku="${row.sku}" data-type="wasted"
                 style="width:70px; text-align:right; background:var(--glass-bg); border:1px solid var(--glass-border); border-radius:6px; color:var(--ink); padding:4px 6px;">
        </td>
      </tr>`;
    }).join('');
  }

  document.getElementById('acCancel').addEventListener('click', () => {
    document.getElementById('actualsOverlay').style.display = 'none';
  });

  document.getElementById('acSave').addEventListener('click', async () => {
    const d    = acState.selectedDate;
    const branch = els.branch.value;
    const rows = document.querySelectorAll('#acSkuRows tr');
    let saved = 0, errors = 0;
    for (const tr of rows) {
      const soldInp   = tr.querySelector('input[data-type="sold"]');
      const wastedInp = tr.querySelector('input[data-type="wasted"]');
      const sku = soldInp.dataset.sku;
      if (soldInp.value === '' && wastedInp.value === '') continue;
      try {
        await api.post('/api/feedback/actual', {
          branch, sku,
          bake_date: d,
          qty_sold:   soldInp.value   === '' ? 0 : +soldInp.value,
          qty_wasted: wastedInp.value === '' ? 0 : +wastedInp.value,
        });
        // Update local state so checkmark appears immediately
        acState.weekActuals[`${sku}|${d}`] = {
          qty_sold: +soldInp.value, qty_wasted: +wastedInp.value
        };
        if (!acState.datesLogged.includes(d)) acState.datesLogged.push(d);
        saved++;
      } catch(e) { errors++; }
    }
    if (errors) toast(`${errors} items failed to save`, 'warn');
    if (saved)  toast(`Saved actuals for ${d}`, 'ok');
    // Refresh strip and table to show checkmarks
    const days = [];
    let dd = new Date(acState.weekRows[0].week_start + 'T12:00:00');
    const endD = new Date(acState.weekRows[0].week_end + 'T12:00:00');
    while (dd <= endD) { days.push(dd.toISOString().slice(0,10)); dd.setDate(dd.getDate()+1); }
    renderDayStrip(days);
    renderActualsTable();
  });

  function openOverrideModal(row) {
    els.ovSku.textContent = `${row.sku} · ${row.item_name || ''}`;
    els.ovUnits.value = state.editingUnits ?? row.override ?? Math.round(row.predicted_units);
    els.ovReason.value = row.override_reason || 'gut_feel';
    els.ovNote.value = '';
    // Show delete button only when an override already exists
    els.ovDelete.style.display = row.override != null ? 'inline-flex' : 'none';
    els.overlay.style.display = 'flex';
  }
  els.ovCancel.addEventListener('click', () => { els.overlay.style.display = 'none'; });
  els.ovDelete.addEventListener('click', async () => {
    const fid = state.editingForecastId;
    if (!fid) return;
    try {
      await fetch(`/api/feedback/override/${fid}`, { method: 'DELETE', credentials: 'same-origin' });
      els.overlay.style.display = 'none';
      toast('Override deleted', 'info');
      load();
    } catch (e) { toast('Delete failed: ' + e.message, 'warn'); }
  });
  els.ovSave.addEventListener('click', async () => {
    const fid = state.editingForecastId;
    if (!fid) return;
    try {
      await api.post('/api/feedback/override', {
        forecast_id: fid,
        override_units: +els.ovUnits.value,
        reason: els.ovReason.value,
        note: els.ovNote.value,
      });
      els.overlay.style.display = 'none';
      toast('Override saved', 'ok');
      load();
    } catch (e) { toast('Save failed: ' + e.message, 'warn'); }
  });

  function renderKpis(k) {
    els.kpiUnits.textContent   = fmt.int(k.units_to_bake);
    els.kpiRevenue.textContent = fmt.money(k.projected_revenue);
    els.kpiWaste.textContent   = fmt.int(k.expected_waste);
    els.kpiRisk.textContent    = fmt.int(k.stockout_risk_skus);
    // Show tracked waste rate if actuals have been logged
    const wasteEl = document.getElementById('kpiWasteRate');
    if (wasteEl && k.waste_rate != null) {
      wasteEl.textContent = (k.waste_rate * 100).toFixed(1) + '%';
      wasteEl.closest('.kpi')?.classList.remove('hidden');
    }
  }

  function renderBanner(mode, isLocked) {
    const slot = els.bannerSlot;
    slot.innerHTML = '';
    if (isLocked) {
      slot.innerHTML = `<div class="banner ok glass" style="max-width:420px;">
        <div class="icon">🔒</div>
        <div class="body"><strong>Plan locked</strong><div class="sub">Bake order has been sent to the oven.</div></div>
      </div>`;
    } else if (mode === 'locked') {
      slot.innerHTML = `<div class="banner info glass" style="max-width:420px;">
        <div class="icon">⏱</div>
        <div class="body"><strong>Plan window closed</strong><div class="sub">Locks daily at ${window.SERVER_LOCK || '16:00'} — bake in progress.</div></div>
      </div>`;
    } else if (mode === 'actuals') {
      slot.innerHTML = `<div class="banner info glass" style="max-width:420px;">
        <div class="icon">📋</div>
        <div class="body"><strong>End-of-day actuals</strong><div class="sub">Record what really sold to feed the next retrain.</div></div>
      </div>`;
    }
  }

  async function load() {
    syncUrl();
    const branch = els.branch.value;
    const bake_date = els.bakeDate.value;
    els.branchLabel.textContent = branch;
    els.title.textContent = 'Weekly bake plan';

    try {
      const data = await api.get(`/api/forecast?branch=${encodeURIComponent(branch)}&bake_date=${bake_date}`);
      // If the API snapped to a different date, update the picker so the user sees where we landed.
      if (data.week_start && data.week_start !== bake_date) {
        els.bakeDate.value = data.week_start;
        syncUrl();
      }
      // Show week range in subtitle
      if (data.week_start && data.week_end) {
        els.dateLabel.textContent = `${fmt.date(data.week_start)} – ${fmt.date(data.week_end)}`;
      } else {
        els.dateLabel.textContent = fmt.date(bake_date);
      }
      setMode(data.mode, data.is_locked);
      renderBanner(data.mode, data.is_locked);
      renderKpis(data.kpis);
      els.modelVersion.textContent = data.rows[0] ? `model ${data.rows[0].model_version}` : '';
      renderTable(data.rows);
    } catch (e) {
      toast('Failed to load forecast: ' + e.message, 'warn');
    }

    try {
      const bySum = await api.get(`/api/forecast/branches-summary?bake_date=${bake_date}`);
      const ctx = document.getElementById('chartByBranch').getContext('2d');
      if (charts.byBranch) charts.byBranch.destroy();
      charts.byBranch = barChart(ctx, bySum.data.map(d => d.branch), [{
        data: bySum.data.map(d => d.units), backgroundColor: C.accent, borderRadius: 6,
      }], { indexAxis: 'y' });
    } catch (e) {}

    try {
      const vs = await api.get(`/api/forecast/vs-actual?branch=${encodeURIComponent(branch)}&days=7`);
      const ctx = document.getElementById('chartVsActual').getContext('2d');
      if (charts.vsActual) charts.vsActual.destroy();
      charts.vsActual = lineChart(ctx, vs.labels, [
        { label: 'Predicted', data: vs.predicted, borderColor: C.accent, backgroundColor: C.band },
        { label: 'Actual', data: vs.actual, borderColor: C.accent2, backgroundColor: C.band2 },
      ]);
    } catch (e) {}
  }

  els.branch.addEventListener('change', load);
  els.bakeDate.addEventListener('change', load);
  els.confSlider.addEventListener('input', () => renderTable(state.rows));

  // "Log actuals" button — opens the day-by-day actuals modal.
  els.actualsBtn.addEventListener('click', () => openActualsModal());
  els.lockBtn.addEventListener('click', async () => {
    if (state.is_locked) return;
    if (!confirm('Lock plan and send to oven? Operators can no longer override after this.')) return;
    try {
      await api.post('/api/feedback/lock', {
        branch: els.branch.value, bake_date: els.bakeDate.value,
      });
      toast('Plan locked', 'ok');
      load();
    } catch (e) { toast('Lock failed: ' + e.message, 'warn'); }
  });

  // ── Generate forecast button ─────────────────────────────────────────────
  if (els.genFcBtn) {
    els.genFcBtn.addEventListener('click', async () => {
      if (!confirm('Generate forecasts for the next 14 days? This may take a minute.')) return;
      els.genFcBtn.disabled = true;
      els.genFcBtn.textContent = '⏳ Generating…';
      try {
        await api.post('/api/forecast/generate', {});
        // Poll until done
        const poll = setInterval(async () => {
          try {
            const s = await api.get('/api/forecast/generate/status');
            if (!s.running) {
              clearInterval(poll);
              els.genFcBtn.disabled = false;
              els.genFcBtn.textContent = '🔮 Generate forecast';
              if (s.last_status === 'ok') {
                toast('Forecasts generated — change the date to see next week', 'ok');
                load();
              } else {
                toast('Forecast generation failed: ' + s.last_status, 'warn');
              }
            }
          } catch (e) { clearInterval(poll); }
        }, 3000);
      } catch (e) {
        els.genFcBtn.disabled = false;
        els.genFcBtn.textContent = '🔮 Generate forecast';
        toast('Could not start: ' + e.message, 'warn');
      }
    });
  }

  load();
})();
