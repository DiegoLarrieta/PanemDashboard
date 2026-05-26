// Minimal fetch wrapper. All requests are credentialed so the JWT cookie rides along.
const api = {
  async get(path) {
    const r = await fetch(path, { credentials: 'same-origin' });
    if (r.status === 401) { location.href = '/login'; throw new Error('unauthorized'); }
    if (!r.ok) throw new Error(`GET ${path}: ${r.status}`);
    return r.json();
  },
  async post(path, body) {
    const r = await fetch(path, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {}),
    });
    if (r.status === 401) { location.href = '/login'; throw new Error('unauthorized'); }
    if (!r.ok) {
      const txt = await r.text();
      throw new Error(`POST ${path}: ${r.status} ${txt}`);
    }
    return r.json();
  },
};

// Number/date helpers used everywhere.
const fmt = {
  int: (n) => (n == null ? '—' : Math.round(n).toLocaleString('en-US')),
  pct: (n) => (n == null ? '—' : (n * 100).toFixed(1) + '%'),
  money: (n) => (n == null ? '—' : '$' + Math.round(n).toLocaleString('en-US')),
  signed: (n) => {
    if (n == null) return '—';
    const r = Math.round(n);
    return (r > 0 ? '+' : '') + r.toLocaleString('en-US');
  },
  date: (d) => new Intl.DateTimeFormat('en-US', {
    weekday: 'short', month: 'short', day: 'numeric',
    timeZone: 'America/Monterrey',
  }).format(new Date(d)),
};

function toast(msg, kind) {
  const el = document.createElement('div');
  el.className = 'banner ' + (kind || 'info') + ' glass';
  el.style.cssText = 'position:fixed;right:24px;bottom:24px;z-index:300;min-width:280px;';
  el.innerHTML = `<div class="body"><strong>${msg}</strong></div>`;
  document.body.appendChild(el);
  setTimeout(() => { el.style.transition = 'opacity 0.4s'; el.style.opacity = '0'; }, 2400);
  setTimeout(() => el.remove(), 2900);
}
