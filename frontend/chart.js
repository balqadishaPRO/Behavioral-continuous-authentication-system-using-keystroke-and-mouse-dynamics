const RISK_COLORS = { ok: '#1E1B18', bad: '#FF4F2E' };
const WINDOW_S = 10;

function riskChart(el, points, threshold) {
  // .fill: chart takes the size of its fixed zone (session page), so filling it with data never resizes the page
  const fill = el.classList.contains('fill');
  const W = fill ? Math.max(320, el.clientWidth) : 800, H = fill ? Math.max(140, el.clientHeight - 130) : 180, L = 44, R = 70, T = 22, B = 26;
  const pw = W - L - R, ph = H - T - B;
  if (!points.length) { el.innerHTML = '<p class="muted">No scored windows yet.</p>'; return; }

  const t0 = points[0].t - WINDOW_S;
  const span = Math.max(points.at(-1).t - t0, 60);
  const x = s => L + (s / span) * pw;
  const y = r => T + (1 - r) * ph;
  const barW = Math.max(2, (WINDOW_S / span) * pw - 2);
  const fmt = s => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')}`;

  let streak = 0;
  const rows = points.map(p => ({ ...p, s: p.t - t0, streak: streak = p.risk > threshold ? streak + 1 : 0 }));

  const step = [15, 30, 60, 120, 300, 600, 1800].find(v => span / v <= 8) || 3600;
  let svg = `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Risk per 10 second window over time">`;
  for (const r of [0, 0.25, 0.5, 0.75, 1]) {
    svg += `<line x1="${L}" x2="${W - R}" y1="${y(r)}" y2="${y(r)}" stroke="#D9CCAE"/>
      <text x="${L - 6}" y="${y(r) + 4}" text-anchor="end" font-size="11" fill="#6B6257">${r * 100}%</text>`;
  }
  for (let s = 0; s <= span; s += step) {
    svg += `<text x="${x(s)}" y="${H - 8}" text-anchor="middle" font-size="11" fill="#6B6257">${fmt(s)}</text>`;
  }
  rows.forEach((p, i) => {
    const bx = x(p.s) - barW, top = Math.min(y(p.risk), y(0) - 2);
    svg += `<rect x="${bx}" y="${top}" width="${barW}" height="${y(0) - top}" rx="2"
      fill="${p.risk > threshold ? RISK_COLORS.bad : RISK_COLORS.ok}"/>`;
    if (p.locked) svg += `<text x="${bx + barW / 2}" y="${top - 4}" text-anchor="middle" font-size="13">🔒</text>`;
    svg += `<rect x="${bx - 1}" y="${T}" width="${barW + 2}" height="${ph}" fill="transparent" data-i="${i}"/>`;
  });
  svg += `<line x1="${L}" x2="${W - R}" y1="${y(threshold)}" y2="${y(threshold)}" stroke="#1E1B18" stroke-width="2" stroke-dasharray="5 4"/>
    <text x="${W - R + 6}" y="${y(threshold) + 4}" font-size="11" fill="#1E1B18" font-weight="800">threshold</text>
    <line x1="${L}" x2="${W - R}" y1="${y(0)}" y2="${y(0)}" stroke="#1E1B18" stroke-width="2"/></svg>`;

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
