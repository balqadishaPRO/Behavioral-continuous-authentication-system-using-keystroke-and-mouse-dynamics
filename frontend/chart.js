// Risk-over-time chart shared by app.html and admin.html.
// One bar per 10 s window, placed on a real time axis (idle stretches show as gaps).
// points: [{t: seconds since epoch, risk, keys, mouse, locked}], risk/keys/mouse in 0..1 (keys/mouse may be null).
const RISK_COLORS = { ok: '#3b6cf6', bad: '#d92d20' };
const WINDOW_S = 10;

function riskChart(el, points, threshold) {
  const W = 800, H = 180, L = 44, R = 70, T = 22, B = 26;  // top margin leaves room for the 🔒 over a 100% bar  // right margin holds the threshold label
  const pw = W - L - R, ph = H - T - B;
  if (!points.length) { el.innerHTML = '<p class="muted">No scored windows yet.</p>'; return; }

  const t0 = points[0].t - WINDOW_S;
  const span = Math.max(points.at(-1).t - t0, 60);
  const x = s => L + (s / span) * pw;           // s = seconds since t0
  const y = r => T + (1 - r) * ph;
  const barW = Math.max(2, (WINDOW_S / span) * pw - 2);  // 2px gap between neighbouring windows
  const fmt = s => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')}`;

  // streak = suspicious windows in a row, same rule as the server
  let streak = 0;
  const rows = points.map(p => ({ ...p, s: p.t - t0, streak: streak = p.risk > threshold ? streak + 1 : 0 }));

  const step = [15, 30, 60, 120, 300, 600, 1800].find(v => span / v <= 8) || 3600;
  let svg = `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Risk per 10 second window over time">`;
  for (const r of [0, 0.25, 0.5, 0.75, 1]) {
    svg += `<line x1="${L}" x2="${W - R}" y1="${y(r)}" y2="${y(r)}" stroke="#eaecf0"/>
      <text x="${L - 6}" y="${y(r) + 4}" text-anchor="end" font-size="11" fill="#667085">${r * 100}%</text>`;
  }
  for (let s = 0; s <= span; s += step) {
    svg += `<text x="${x(s)}" y="${H - 8}" text-anchor="middle" font-size="11" fill="#667085">${fmt(s)}</text>`;
  }
  rows.forEach((p, i) => {
    const bx = x(p.s) - barW, top = Math.min(y(p.risk), y(0) - 2);  // 2px stub keeps a 0% window visible
    svg += `<rect x="${bx}" y="${top}" width="${barW}" height="${y(0) - top}" rx="2"
      fill="${p.risk > threshold ? RISK_COLORS.bad : RISK_COLORS.ok}"/>`;
    if (p.locked) svg += `<text x="${bx + barW / 2}" y="${top - 4}" text-anchor="middle" font-size="13">🔒</text>`;
    svg += `<rect x="${bx - 1}" y="${T}" width="${barW + 2}" height="${ph}" fill="transparent" data-i="${i}"/>`;
  });
  svg += `<line x1="${L}" x2="${W - R}" y1="${y(threshold)}" y2="${y(threshold)}" stroke="#1d2330" stroke-dasharray="5 4"/>
    <text x="${W - R + 6}" y="${y(threshold) + 4}" font-size="11" fill="#1d2330">threshold</text>
    <line x1="${L}" x2="${W - R}" y1="${y(0)}" y2="${y(0)}" stroke="#98a2b3"/></svg>`;

  const pct = v => v == null ? '—' : Math.round(v * 100) + '%';
  el.innerHTML = `<div class="chart-legend">
      <span><i style="background:${RISK_COLORS.ok}"></i>normal window</span>
      <span><i style="background:${RISK_COLORS.bad}"></i>suspicious (above threshold)</span>
      <span>🔒 session locked (3 suspicious in a row)</span>
      <span class="muted">x: time since session start (m:ss) · gaps = idle</span>
    </div>
    <div class="chart-plot">${svg}<div class="chart-tip" hidden></div></div>
    <details><summary class="muted">Data table</summary><table>
      <thead><tr><th>Time</th><th>Risk</th><th>Typing</th><th>Mouse</th><th>In a row</th><th>Locked</th></tr></thead>
      <tbody>${rows.map(p => `<tr><td>${fmt(p.s)}</td><td>${pct(p.risk)}</td><td>${pct(p.keys)}</td><td>${pct(p.mouse)}</td>
        <td>${p.streak}</td><td>${p.locked ? 'yes' : ''}</td></tr>`).join('')}</tbody></table></details>`;

  const plot = el.querySelector('.chart-plot'), tip = el.querySelector('.chart-tip');
  plot.addEventListener('mousemove', e => {
    const i = e.target.dataset?.i;
    if (i === undefined) { tip.hidden = true; return; }
    const p = rows[i], box = plot.getBoundingClientRect();
    tip.innerHTML = `<b>${fmt(p.s - WINDOW_S)}–${fmt(p.s)}</b><br>Risk <b>${pct(p.risk)}</b>
      <br>Typing ${pct(p.keys)} · Mouse ${pct(p.mouse)}<br>Suspicious in a row: ${p.streak}${p.locked ? '<br>🔒 locked' : ''}`;
    tip.hidden = false;
    tip.style.left = Math.min(e.clientX - box.left + 12, box.width - 170) + 'px';
    tip.style.top = (e.clientY - box.top + 12) + 'px';
  });
  plot.addEventListener('mouseleave', () => { tip.hidden = true; });
}
