const $ = id => document.getElementById(id);
// Safe HTML escaper — used wherever backend strings go into innerHTML
const esc = s => { const d = document.createElement('div'); d.textContent = String(s ?? ''); return d.innerHTML; };
const AUTO_REFRESH_MS = 5 * 60 * 1000;   // 5 minutes
let _lastData = null;
let _nextRefreshAt = 0;

// Thresholds match the backend DECISION_BANDS (85/70/55/40): green ≥70 (engaged),
// yellow ≥55 (selective — the engage line), orange ≥40 (de-risk), red <40 (risk-off).
function scoreColor(s) {
  if (s >= 70) return 'var(--green)';
  if (s >= 55) return 'var(--yellow)';
  if (s >= 40) return 'var(--orange)';
  return 'var(--red)';
}
function colorClass(s) {
  if (s >= 70) return 'c-green';
  if (s >= 55) return 'c-yellow';
  if (s >= 40) return 'c-orange';
  return 'c-red';
}
function tagColor(c) { return ['green','yellow','orange','red','gray'].includes(c) ? c : 'gray'; }
function chgStr(v)   { return (v >= 0 ? '+' : '') + Number(v).toFixed(2) + '%'; }

/* ── FUTURES TAPE ─────────────────────────────────────── */
function fmtFuturePrice(v) {
  if (v == null || Number.isNaN(Number(v))) return '—';
  return Number(v).toLocaleString(undefined, {
    maximumFractionDigits: Number(v) >= 1000 ? 0 : 2
  });
}

function renderFuturesTape(tape) {
  const toneEl = $('futures-tone');
  const avgEl = $('futures-avg');
  const itemsEl = $('futures-items');
  const readEl = $('futures-read');
  if (!toneEl || !avgEl || !itemsEl || !readEl) return;

  const color = tagColor(tape?.tone_color || 'gray');
  const tone = tape?.tone || 'Unavailable';
  const weighted = tape?.weighted_change_pct;
  toneEl.className = `futures-tone ${color}`;
  toneEl.innerHTML = `<span class="futures-dot"></span><span>${esc(tone)}</span>`;
  avgEl.textContent = weighted == null ? 'No read' : `${chgStr(weighted)} weighted`;

  const items = tape?.items || [];
  itemsEl.innerHTML = items.length ? items.map(item => {
    const chg = item.change_pct;
    const chgCls = chg == null ? 'flat' : chg > 0 ? 'up' : chg < 0 ? 'dn' : 'flat';
    const chgText = chg == null ? '—' : chgStr(chg);
    const title = `${item.name || item.symbol || ''} · ${item.source || tape?.source || 'source unavailable'}`;
    return `<div class="future-chip" title="${esc(title)}">
      <div class="future-top">
        <span class="future-sym">${esc(item.symbol || '—')}</span>
        <span class="future-px">${fmtFuturePrice(item.price)}</span>
      </div>
      <div class="future-top">
        <span class="future-name">${esc(item.name || '')}</span>
        <span class="future-chg ${chgCls}">${chgText}</span>
      </div>
    </div>`;
  }).join('') : '<div style="color:var(--muted);font-size:10px;">Futures unavailable</div>';

  const source = tape?.source || 'Futures';
  readEl.innerHTML = `${esc(tape?.read || 'Futures tape unavailable. Use the cash session for confirmation.')}
    <span class="futures-meta"><span>${esc(source)}</span><span>Context only</span><span>Not scored</span></span>`;
}

/* ── HEADER BADGES ──────────────────────────────────────── */
function renderHeader(d) {
  const mkt = d.market_state || {};
  $('mkt-badge').className = 'mkt-badge ' + (mkt.state || 'closed');
  $('mkt-label').textContent = mkt.label || '—';
  const etEl = $('et-time'); if (etEl) etEl.textContent = mkt.et_time ? `${mkt.et_date} · ${mkt.et_time}` : '—';

  const fomc = d.fomc || {};
  $('fomc-badge').className = 'fomc-badge ' + (fomc.color || 'gray');
  if (d.fomc_calendar_stale) {
    $('fomc-badge').innerHTML = `⚠ FOMC calendar outdated <span class="date">update _FOMC_2026_2027 in data.py</span>`;
  } else {
    $('fomc-badge').innerHTML = `${esc(fomc.label || '—')} <span class="date">${esc(fomc.date_pretty || '')}</span>`;
  }

  const dtsEl = $('data-ts'); if (dtsEl) dtsEl.textContent = d.timestamp ? `updated ${d.timestamp}` : '';
  const freshEl = document.getElementById('score-freshness');
  if (freshEl) freshEl.textContent = d.timestamp ? `as of ${d.timestamp}` : '';

  // Econ events row — includes earnings season flag
  const events = d.econ_events || [];
  const visible = events.filter(e => e.days_until <= 14);
  const earn = d.earnings || {};
  const earnBadge = (earn.in_season || earn.days_until <= 14)
    ? `<span class="econ-badge ${esc(earn.color)}">🏦 ${esc(earn.label)} <span class="econ-badge-sub">${esc(earn.detail || '')}</span></span>`
    : '';
  const staleBadge = d.econ_calendar_stale
    ? `<span class="econ-badge orange">⚠ ECON CALENDAR outdated — update _ECON_CALENDAR in data.py</span>`
    : '';
  if (visible.length || earnBadge || staleBadge) {
    $('econ-row').style.display = 'flex';
    $('econ-badges').innerHTML = staleBadge + earnBadge + visible.map(e =>
      `<span class="econ-badge ${esc(e.color)}">${esc(e.type)} · ${esc(e.name)} <span class="econ-badge-sub">${esc(e.urgency)}</span></span>`
    ).join(' ');
  } else {
    $('econ-row').style.display = 'none';
  }

  // Coverage warning
  const cov = d.data_coverage || {};
  const quality = d.data_quality || {};
  if (quality.valid === false) {
    $('coverage-warn').style.display = 'flex';
    const missing = quality.critical_missing?.length
      ? ` Critical missing: ${quality.critical_missing.join(', ')}.`
      : '';
    const histMissing = quality.critical_history_missing?.length
      ? ` Insufficient history: ${quality.critical_history_missing.map(h => `${h.symbol} (${h.found}/${h.required} bars)`).join(', ')}.`
      : '';
    $('coverage-warn').innerHTML = `⚠ ${esc(quality.message || 'Market data unavailable.')} ${esc(cov.fetched ?? 0)}/${esc(cov.requested ?? 0)} symbols fetched.${esc(missing)}${esc(histMissing)}`;
  } else if (cov.failed && cov.failed.length) {
    $('coverage-warn').style.display = 'flex';
    $('coverage-warn').innerHTML = `⚠ Partial data: ${esc(cov.fetched)}/${esc(cov.requested)} symbols fetched. Missing: ${cov.failed.slice(0, 8).map(esc).join(', ')}${cov.failed.length > 8 ? '…' : ''}`;
  } else {
    $('coverage-warn').style.display = 'none';
  }
}

/* ── RADAR CHART ────────────────────────────────────────── */
function buildRadarChart(pillars) {
  const keys = ['volatility', 'trend', 'breadth', 'momentum', 'macro'];
  const labels = ['VOL', 'TREND', 'BREADTH', 'MOM', 'MACRO'];
  const cx = 100, cy = 100, maxR = 62;
  const step = (2 * Math.PI) / keys.length;
  const start = -Math.PI / 2;
  const point = (index, radius) => {
    const angle = start + index * step;
    return [cx + radius * Math.cos(angle), cy + radius * Math.sin(angle)];
  };
  const scores = keys.map(key => Math.max(0, Math.min(100, Number(pillars?.[key]?.score) || 0)));
  const scorePoints = scores.map((score, index) => point(index, maxR * score / 100));
  const accessibleLabel = labels.map((label, index) => `${label} ${scores[index]}`).join(', ');

  let svg = `<svg viewBox="0 0 200 200" role="img" aria-label="Decision driver scores: ${accessibleLabel}">`;
  [25, 50, 75, 100].forEach(percent => {
    const radius = maxR * percent / 100;
    svg += `<circle cx="${cx}" cy="${cy}" r="${radius}" fill="none" stroke="var(--border2)" stroke-width="1"/>`;
  });
  keys.forEach((_, index) => {
    const [x, y] = point(index, maxR);
    svg += `<line x1="${cx}" y1="${cy}" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}" stroke="var(--border2)" stroke-width="1"/>`;
  });
  svg += `<polygon points="${scorePoints.map(coords => coords.map(value => value.toFixed(1)).join(',')).join(' ')}" fill="rgba(59,130,246,.14)" stroke="var(--accent)" stroke-width="1.5"/>`;
  scores.forEach((score, index) => {
    const [x, y] = scorePoints[index];
    const color = scoreColor(score);
    const [labelX, labelY] = point(index, maxR + 20);
    svg += `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="3" fill="${color}"/>`;
    svg += `<text x="${labelX.toFixed(1)}" y="${(labelY - 2).toFixed(1)}" text-anchor="middle" fill="var(--muted2)" font-size="12" font-family="ui-monospace, monospace">${labels[index]}</text>`;
    svg += `<text x="${labelX.toFixed(1)}" y="${(labelY + 11).toFixed(1)}" text-anchor="middle" fill="${color}" font-size="14" font-family="ui-monospace, monospace" font-weight="700">${score}</text>`;
  });
  return svg + '</svg>';
}

function validateDashboardPayload(data) {
  const pillarKeys = ['volatility', 'trend', 'breadth', 'momentum', 'macro'];
  const validScore = value => Number.isFinite(Number(value));
  if (!data || typeof data !== 'object' || !validScore(data.total_score)) return false;
  if (!data.pillars || !pillarKeys.every(key => validScore(data.pillars[key]?.score) && data.pillars[key]?.details)) return false;
  return typeof data.decision === 'string' && typeof data.position_size === 'string';
}

/* ── HERO ───────────────────────────────────────────────── */
function renderHero(d) {
  const col = d.decision_color;
  const s   = d.total_score;
  const invalidData = d.data_quality?.valid === false;

  // Badge: show DATA UNAVAILABLE and grey out everything when feeds are broken
  if (invalidData) {
    $('decision-badge').textContent = 'DATA UNAVAILABLE';
    $('decision-badge').className = 'decision-badge c-muted';
    $('pos-text').textContent = '—';
    $('pos-text').style.color = 'var(--muted)';
  } else {
    $('decision-badge').textContent = d.decision;
    const badgeCls = col === 'green' ? 'c-green' : col === 'yellow' ? 'c-yellow' : col === 'orange' ? 'c-orange' : 'c-red';
    $('decision-badge').className = 'decision-badge ' + badgeCls;
    $('pos-text').textContent = d.position_size;
    $('pos-text').style.color = scoreColor(s);
  }

  // ── Decision context: regime, posture, confidence ──────
  const regime  = d.pillars?.trend?.details?.regime || null;
  const posture = d.action_hint
                || (invalidData ? 'Exposure off — live market data is unavailable'
                : s >= 85 ? 'Full exposure — calm, trending tape, press the bid on A/B setups'
                : s >= 70 ? 'Standard exposure — constructive tape, run your normal game'
                : s >= 55 ? 'Moderate exposure — mixed tape, engage selectively, A+ setups, tight stops'
                : s >= 40 ? 'Reduced exposure — choppy tape, very selective or sit out'
                :           'Defensive — stressed tape, protect capital, no new longs');
  const confLevel = invalidData ? 0 : s >= 85 ? 5 : s >= 70 ? 4 : s >= 55 ? 3 : s >= 40 ? 2 : 1;
  const confColor = invalidData ? 'var(--red)' : s >= 70 ? 'var(--green)' : s >= 55 ? 'var(--yellow)' : s >= 40 ? 'var(--orange)' : 'var(--red)';
  const confSegs  = [1,2,3,4,5].map(i =>
    `<div class="conf-seg" style="background:${i <= confLevel ? confColor : 'var(--border)'}"></div>`
  ).join('');
  const regimeTag = regime
    ? `<span class="tag ${regime.toLowerCase().includes('up') ? 'green' : regime.toLowerCase().includes('down') ? 'red' : 'yellow'}">${esc(regime)}</span>`
    : '';
  const ctx = $('decision-context');
  ctx.style.display = 'flex';
  ctx.innerHTML = `
    ${regime ? `<div class="dc-row"><span class="dc-label">Regime</span>${regimeTag}</div>` : ''}
    <div class="dc-posture">${posture}</div>
    ${volTargetLine(d.vol_target)}
    <div class="dc-row"><span class="dc-label">Confidence</span><div class="confidence-bar">${confSegs}</div></div>
  `;

  const circ = 289;
  const arc = $('score-arc');
  arc.style.strokeDashoffset = circ - (s / 100) * circ;
  arc.style.stroke = scoreColor(s);
  $('score-val').textContent = s;
  $('score-val').style.color = scoreColor(s);
  const radar = $('hero-radar');
  if (radar) radar.innerHTML = buildRadarChart(d.pillars);

  // Score delta badge
  const delta = d.score_delta;
  let deltaHtml = '';
  if (delta !== null && delta !== undefined) {
    const cls = delta > 0 ? 'up' : delta < 0 ? 'dn' : 'flat';
    const sign = delta > 0 ? '+' : '';
    deltaHtml = `<div class="score-delta ${cls}">${sign}${delta} since last snapshot</div>`;
  }
  // Insert delta below the score label if not already there
  const scoreLabel = document.querySelector('.score-label');
  if (scoreLabel) {
    let existing = scoreLabel.nextElementSibling;
    if (existing && existing.classList.contains('score-delta')) existing.remove();
    if (deltaHtml) scoreLabel.insertAdjacentHTML('afterend', deltaHtml);
  }

  // SPY win/loss streak badge
  const streak = d.spy_streak;
  const streakContainer = document.querySelector('.streak-badge-wrap');
  if (streakContainer) {
    if (streak && streak.days >= 2) {
      const emoji = streak.direction === 'up' ? '🟢' : '🔴';
      const label = streak.direction === 'up' ? 'win streak' : 'losing streak';
      streakContainer.innerHTML =
        `<span class="streak-badge streak-${streak.direction}">${emoji} SPY ${streak.days}-day ${label}</span>`;
      streakContainer.style.display = '';
    } else {
      streakContainer.style.display = 'none';
    }
  }

  // Update header score badge
  const headerScore = $('header-score');
  if (headerScore) {
    const invalidData = d.data_quality?.valid === false;
    headerScore.textContent = invalidData ? '— · DATA UNAVAILABLE' : `${s} · ${d.decision}`;
    headerScore.className = 'header-score loaded';
    headerScore.style.color = invalidData ? 'var(--muted)' : scoreColor(s);
  }
}

/* ── PILLARS ────────────────────────────────────────────── */
function tag(label, color) {
  if (!label) return '';
  return `<span class="tag ${tagColor(color)}">${esc(label)}</span>`;
}
function mrow(key, val, tagLabel, tagCol, src) {
  const srcHtml = src ? ` <span class="src-badge">${esc(src)}</span>` : '';
  return `<div class="metric-row">
    <span class="metric-key">${esc(key)}</span>
    <span class="metric-val">${esc(val ?? '')} ${tag(tagLabel, tagCol)}${srcHtml}</span>
  </div>`;
}

function renderPillars(d) {
  const ds = d.data_sources || {};
  const defs = [
    {
      key: 'volatility', icon: '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>', label: 'VOLATILITY',
      primary(p) {
        const v = p.details;
        return [
          mrow('VIX Level',     v.vix_level ?? '—', v.vix_label, v.vix_color, ds.vix),
          mrow('VIX Trend',     chgStr(v.vix_change_pct ?? 0), v.vix_trend, v.vix_trend_color),
          mrow('VIX 1Y %ile',   (v.vix_pctile ?? 0) + 'th', null),
          mrow('VIX3M',         v.vix3m_value ? `${v.vix3m_value}` : '—', v.vix_term_label, v.vix_term_color),
        ].join('');
      },
      detail(p) {
        const v = p.details;
        return [
          mrow('VIX9D/VIX',     v.vix9d_value ? `${v.vix9d_value} (${v.vix9d_ratio}x)` : '—', v.vix9d_label, v.vix9d_color),
          mrow('SKEW',          v.skew_value ? `${v.skew_value}` : '—', v.skew_label, v.skew_color),
          mrow('Flow Sentiment', (v.flow_score ?? '—') + '/100', v.flow_label, v.flow_color),
          `<div class="metric-row"><span class="metric-key" style="font-size:9px;">Flow inputs</span><span class="metric-val" style="font-size:9px;color:var(--muted)">TQQQ ${chgStr(v.tqqq_chg ?? 0)} · SQQQ ${chgStr(v.sqqq_chg ?? 0)} · UVXY ${chgStr(v.uvxy_chg ?? 0)}</span></div>`,
        ].join('');
      },
    },
    {
      key: 'trend', icon: '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></svg>', label: 'TREND',
      primary(p) {
        const v = p.details;
        return [
          mrow('SPY Price',   v.spy_price ? `$${v.spy_price}` : '—', chgStr(v.spy_change_pct ?? 0), v.spy_change_pct >= 0 ? 'green' : 'red'),
          mrow('SPY vs 20d',  v.ma20 ? `$${v.ma20}`   : '—', v.above_20  ? '▲ Healthy'  : '▼ Warning', v.above_20  ? 'green' : 'red'),
          mrow('SPY vs 50d',  v.ma50 ? `$${v.ma50}`   : '—', v.above_50  ? '▲ Strong'   : '▼ Weak',    v.above_50  ? 'green' : 'red'),
          mrow('SPY vs 200d', v.ma200 ? `$${v.ma200}` : '—', v.above_200 ? '▲ Intact'   : '▼ Broken',  v.above_200 ? 'green' : 'red'),
          `<div class="pillar-sep"></div>`,
          mrow('Regime',  '',  v.regime, v.regime_color),
        ].join('');
      },
      detail(p) {
        const v = p.details;
        return [
          mrow('QQQ',  v.qqq_price ? `$${v.qqq_price}` : '—', chgStr(v.qqq_change_pct ?? 0), v.qqq_change_pct >= 0 ? 'green' : 'red'),
          mrow('RSI(14)', v.rsi14 ?? '—', null),
          mrow('ATH Dist', (v.ath_dist >= 0 ? '+' : '') + (v.ath_dist ?? 0) + '%', null),
          mrow('SPY Volume', v.vol_ratio != null ? `${v.vol_ratio}x avg` : '—', v.vol_label, v.vol_color),
          mrow('Mkt Character', v.char_atr_pct != null ? `ATR ${v.char_atr_pct}%` : '—', v.char_label, v.char_color),
          mrow('MACD(12,26,9)', v.macd_line != null ? `${v.macd_line} / Sig ${v.macd_signal}` : '—', v.macd_label, v.macd_color),
        ].join('');
      },
    },
    {
      key: 'breadth', icon: '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>', label: 'BREADTH',
      primary(p) {
        const v = p.details;
        const spct = v.sectors_total ? Math.round(v.sectors_positive / v.sectors_total * 100) : 0;
        const ipct = v.industries_total ? Math.round(v.industries_positive / v.industries_total * 100) : 0;
        return [
          mrow('Sectors +',   `${v.sectors_positive}/${v.sectors_total}`, spct >= 73 ? 'Strong' : spct >= 45 ? 'Mixed' : 'Weak', spct >= 73 ? 'green' : spct >= 45 ? 'yellow' : 'red'),
          mrow('Industries +', `${v.industries_positive}/${v.industries_total}`, ipct >= 67 ? 'Strong' : ipct >= 45 ? 'Mixed' : 'Weak', ipct >= 67 ? 'green' : ipct >= 45 ? 'yellow' : 'red'),
          mrow('RSP',      v.rsp_price ? `$${v.rsp_price}` : '—', chgStr(v.rsp_change_pct ?? 0), v.rsp_change_pct >= 0 ? 'green' : 'red'),
          mrow('RSP vs SPY', chgStr(v.rsp_vs_spy ?? 0), v.rsp_vs_spy > 0 ? 'Equal-Wt Led' : 'Large-Cap Led', v.rsp_vs_spy > 0 ? 'green' : 'orange'),
        ].join('');
      },
      detail(p) {
        const v = p.details;
        return [
          mrow('RSP > 50d',  '', v.rsp_above_50  ? 'Yes' : 'No', v.rsp_above_50  ? 'green' : 'red'),
          mrow('RSP > 200d', '', v.rsp_above_200 ? 'Yes' : 'No', v.rsp_above_200 ? 'green' : 'red'),
          v.pct_sectors_above_200 != null ? mrow('Sectors > 200d', `${v.sectors_above_200}/${v.sectors_above_200_total}`,
            v.pct_sectors_above_200 >= 73 ? 'Broad Bull' : v.pct_sectors_above_200 <= 36 ? 'Structural Weakness' : 'Mixed',
            v.pct_sectors_above_200 >= 73 ? 'green' : v.pct_sectors_above_200 <= 36 ? 'red' : 'yellow') : '',
        ].join('');
      },
    },
    {
      key: 'momentum', icon: '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>', label: 'MOMENTUM',
      primary(p) {
        const v = p.details;
        const chips = (v.sector_rs && v.sector_rs.length)
          ? `<div class="rs-chips">${v.sector_rs.slice(0, 3).map(r => {
              const bg = r.rs_score >= 0 ? 'rgba(0,230,118,0.15)' : 'rgba(255,23,68,0.15)';
              const col = r.rs_score >= 0 ? 'var(--green)' : 'var(--red)';
              return `<span class="rs-chip" style="background:${bg};color:${col}">${esc(r.name)}</span>`;
            }).join('')}</div>` : '';
        return [
          mrow('Participation', '', v.participation ?? '—', v.participation_color),
          mrow('IWM vs SPY',    chgStr(v.iwm_vs_spy ?? 0), v.iwm_vs_spy > 0.3 ? 'Risk-On' : v.iwm_vs_spy < -0.3 ? 'Defensive' : 'Neutral', v.iwm_vs_spy > 0.3 ? 'green' : v.iwm_vs_spy < -0.3 ? 'orange' : 'yellow'),
          mrow('RSP vs SPY',    chgStr(v.rsp_vs_spy ?? 0), v.rsp_outperforming ? 'Equal-Wt Led' : 'Large-Cap Led', v.rsp_outperforming ? 'green' : 'orange'),
          mrow('RS Rotation',  '', v.rs_rotation_label ?? '—', v.rs_rotation_color),
          chips,
        ].join('');
      },
      detail(p) {
        const v = p.details;
        const l = v.leader || {}, lg = v.laggard || {};
        return [
          mrow('Sectors +',    v.sectors_label ?? '—', null, v.sectors_color),
          mrow('Leader',       l.name ?? '—', l.change_pct != null ? chgStr(l.change_pct) : null, 'green'),
          mrow('Laggard',      lg.name ?? '—', lg.change_pct != null ? chgStr(lg.change_pct) : null, 'red'),
          mrow('Growth 3',     v.growth_leaders + '/3', null),
          `<div class="pillar-sep"></div>`,
          ...(v.sector_rs && v.sector_rs.length ? [
            `<div class="metric-row"><span class="metric-key" style="font-size:9px;color:var(--muted)">Sector RS (1M+3M blend)</span></div>`,
            ...v.sector_rs.slice(0, 5).map((r, i) => mrow(
              `${i+1}. ${r.name}`,
              `RS ${r.rs_score > 0 ? '+' : ''}${r.rs_score}`,
              `1M ${r.return_1m > 0 ? '+' : ''}${r.return_1m}%`,
              r.rs_score >= 0 ? 'green' : 'red'
            )),
          ] : []),
        ].join('');
      },
    },
    {
      key: 'macro', icon: '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>', label: 'MACRO',
      primary(p) {
        const v = p.details;
        const sf = d.fear_greed_stock || {}, cf = d.fear_greed_crypto || {};
        return [
          mrow('10Y Yield',    v.tnx_value ? `${v.tnx_value}%` : '—', v.yield_direction, v.yield_color, ds.tnx),
          mrow('Yield Curve', v.curve_spread != null ? `${v.curve_spread > 0 ? '+' : ''}${v.curve_spread}%` : '—', v.curve_label, v.curve_color),
          mrow('DXY',         v.dxy_value ?? '—', v.dxy_label, v.dxy_color),
          mrow('HYG Credit',  v.hyg_price ? `$${v.hyg_price}` : '—', v.hyg_label, v.hyg_color),
          `<div class="pillar-sep"></div>`,
          sf.available ? mrow('Stocks F&G', Math.round(sf.score), sf.rating, fngColor(sf.score)) : mrow('Stocks F&G', '—', null, null),
          cf.available ? mrow('Crypto F&G', Math.round(cf.score), cf.rating, fngColor(cf.score)) : mrow('Crypto F&G', '—', null, null),
        ].join('');
      },
      detail(p) {
        const v = p.details;
        return [
          mrow('10Y MA20',    v.tnx_ma20 ? `${v.tnx_ma20}%` : '—', v.yield_label, null),
          mrow('3M Yield',    v.irx_value ? `${v.irx_value}%` : '—', null, null),
          mrow('DXY MA20',    v.dxy_ma20 ?? '—', null),
          mrow('TLT',         v.tlt_value ? `$${v.tlt_value}` : '—', chgStr(v.tlt_change_pct ?? 0), v.tlt_change_pct >= 0 ? 'green' : 'red'),
          mrow('GLD (Gold)',  v.gld_price ? `$${v.gld_price}` : '—', v.gld_label, v.gld_color),
          mrow('BTC',         v.btc_price ? `$${Number(v.btc_price).toLocaleString()}` : '—', v.btc_label, v.btc_color, ds.btc),
          mrow('BTC Trend',   v.btc_trend ?? '—', v.btc_from_high != null ? `${v.btc_from_high}% from high` : null, v.btc_trend_color),
          `<div class="pillar-sep"></div>`,
          mrow('FOMC',        v.fomc_date ?? '—', v.fomc_label, v.fomc_color),
          mrow('OpEx',        v.opex_date ?? '—', v.opex_label, v.opex_color),
          mrow('Seasonality', v.season_label ?? '—', v.season_bias, v.season_color),
        ].join('');
      },
    },
  ];

  $('pillars-row').innerHTML = defs.map(def => {
    const p = d.pillars[def.key];
    const sc = p.score;
    const c = scoreColor(sc);
    const reasons = (p.reasons || []).map(r => `<div class="why-line">${esc(r)}</div>`).join('');
    const detailId = `pillar-${def.key}-details`;
    return `
      <div class="pillar-card">
        <div class="pillar-head">
          <span class="pillar-name icon-label" style="color:${c}">${def.icon} ${def.label}</span>
          <span class="pillar-score-badge" style="color:${c}">${sc}</span>
        </div>
        <div class="pillar-bar"><div class="pillar-bar-fill" style="width:${sc}%;background:${c}"></div></div>
        ${def.primary(p)}
        <button class="detail-toggle" onclick="toggleDetail(this)" aria-expanded="false" aria-controls="${detailId}">▾ More detail &amp; why</button>
        <div class="detail-rows" id="${detailId}">
          ${def.detail(p)}
          <div class="why-section">
            <div class="why-section-label">Why this score</div>
            ${reasons || '<em>No reasons recorded</em>'}
          </div>
        </div>
      </div>`;
  }).join('');
}

function toggleDetail(el) {
  const body = el.nextElementSibling;
  const open = body.classList.toggle('open');
  el.setAttribute('aria-expanded', open);
  el.innerHTML = (open ? '▴ Less detail' : '▾ More detail & why');
}

/* ── SECTOR + INDUSTRY BARS ────────────────────────────── */
function renderBars(elId, data) {
  const entries = Object.entries(data || {}).sort((a, b) => b[1].change_pct - a[1].change_pct);
  if (!entries.length) { $(elId).innerHTML = '<div style="color:var(--muted);font-size:10px;">No data</div>'; return; }
  const maxAbs = Math.max(...entries.map(([, v]) => Math.abs(v.change_pct)), 0.5);
  $(elId).innerHTML = entries.map(([, v]) => {
    const w = Math.round(Math.abs(v.change_pct) / maxAbs * 100);
    const bg = v.change_pct >= 0 ? 'rgba(0,230,118,0.25)' : 'rgba(255,23,68,0.25)';
    const c  = 'var(--text)';
    return `<div class="sector-row">
      <span class="sector-name">${esc(v.name)}</span>
      <div class="sector-bar-wrap">
        <div class="sector-bar" style="width:${w}%;background:${bg}">
          <span class="sector-pct" style="color:${c}">${chgStr(v.change_pct)}</span>
        </div>
      </div>
    </div>`;
  }).join('');
}

/* ── WATCHLIST HEALTH ─────────────────────────────────── */
let _watchlistData = null;
let _watchlistView = 'a_plus';

function watchColor(score) {
  return score >= 75 ? 'var(--green)' : score >= 60 ? 'var(--yellow)' : score >= 45 ? 'var(--orange)' : 'var(--red)';
}

function renderWatchRows(rows, emptyText, limit = null) {
  if (!rows || !rows.length) {
    return `<div style="color:var(--muted);font-size:10px;">${esc(emptyText)}</div>`;
  }
  const shown = limit ? rows.slice(0, limit) : rows;
  return shown.map(r => {
    const chg = r.change_pct;
    const chgCls = chg == null ? 'flat' : chg > 0 ? 'up' : chg < 0 ? 'dn' : 'flat';
    const chgTxt = chg == null ? '—' : (chg > 0 ? '+' : '') + chg.toFixed(2) + '%';
    const priceTxt = r.price != null ? '$' + r.price.toLocaleString('en-US', {maximumFractionDigits: 2}) : '—';
    const why = esc(r.why || r.label || '');
    return `<div class="watch-row">
      <div class="watch-sym">${esc(r.symbol)}</div>
      <div class="watch-state ${esc(r.entry_color || 'gray')}">${esc(r.entry_state || 'Watch')}</div>
      <div class="watch-price">${priceTxt}</div>
      <div class="watch-chg ${chgCls}">${chgTxt}</div>
      <div class="watch-note" title="${why}">${why}</div>
      <div class="watch-score" style="color:${watchColor(r.score)}">${r.score}</div>
    </div>`;
  }).join('');
}

function selectWatchlistView(view) {
  _watchlistView = view;
  if (_watchlistData) renderWatchlistHealth(_watchlistData);
}

function renderWatchlistHealth(w, selectedView = _watchlistView) {
  _watchlistData = w;
  const el = $('watchlist-health');
  const counts = w.tradable_counts || w.counts || {};
  $('watchlist-meta').textContent = `${w.name || 'Watchlist'} · ${w.scanned || 0} stock/ETF scanned`;
  const skipped = (w.skipped || []).length;
  const views = w.watch_views || {};
  const viewLabels = {
    a_plus:      'Strong Trend',
    pullback:    'Pullback',
    bear_regime: 'Wait (Bear)',
    extended:    'Extended',
    broken:      'Broken',
    neutral:     'Neutral',
    unavailable: 'No Data',
  };
  const stats = [
    ['a_plus',   'Strong Trend', counts.a_plus   || 0, 'var(--green)'],
    ['pullback',  'Pullback',    counts.pullback  || 0, 'var(--yellow)'],
    ...(counts.bear_regime ? [['bear_regime', 'Wait (Bear)', counts.bear_regime, 'var(--red)']] : []),
    ['extended',  'Extended',   counts.extended  || 0, 'var(--orange)'],
    ['broken',    'Broken',     counts.broken    || 0, 'var(--red)'],
  ];
  if (counts.neutral) stats.push(['neutral', 'Neutral', counts.neutral, 'var(--muted2)']);
  if (counts.unavailable) stats.push(['unavailable', 'No Data', counts.unavailable, 'var(--muted)']);
  const selectedRows = views[selectedView] || views.a_plus || [];
  const selectedLabel = viewLabels[selectedView] || 'A+ Trend';

  el.innerHTML = `
    <div class="watch-summary">
      ${stats.map(([key, label, num, color]) => `<button class="watch-stat ${selectedView === key ? 'active' : ''}" onclick="selectWatchlistView('${key}')">
        <div class="num" style="color:${color}">${num}</div>
        <div class="lbl">${label}</div>
      </button>`).join('')}
    </div>
    <div>
      <div class="watch-selected-head">
        <span>${esc(selectedLabel)}</span>
        <span>${selectedRows.length} symbol${selectedRows.length === 1 ? '' : 's'}</span>
      </div>
      <div class="watch-filter-list">
        ${renderWatchRows(selectedRows, 'No symbols in this bucket')}
      </div>
    </div>
    ${skipped ? `<div style="color:var(--muted);font-size:9px;line-height:1.5;">Skipped ${skipped} TradingView-only symbol(s): ${(w.skipped || []).slice(0, 4).map(s => esc(s.tv_symbol)).join(', ')}${skipped > 4 ? '…' : ''}</div>` : ''}
  `;
}

async function loadWatchlistHealth() {
  try {
    const sel = $('watchlist-select');
    const file = sel ? sel.value : '';
    const url = '/api/watchlist-health' + (file ? `?file=${encodeURIComponent(file)}` : '');
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    renderWatchlistHealth(data);
  } catch(e) {
    $('watchlist-health').innerHTML = `<div style="color:var(--red);font-size:10px;">Watchlist unavailable: ${esc(e.message)}</div>`;
  }
}

async function initWatchlistDropdown() {
  try {
    const res = await fetch('/api/watchlists');
    if (!res.ok) return;
    const { files, default: def } = await res.json();
    const sel = $('watchlist-select');
    if (!sel || !files || files.length <= 1) {
      // Hide dropdown when only one file (or none)
      if (sel) sel.style.display = 'none';
      return;
    }
    sel.innerHTML = files.map(f =>
      `<option value="${esc(f)}"${f === def ? ' selected' : ''}>${esc(f.replace(/\.txt$/i, ''))}</option>`
    ).join('');
  } catch { /* dropdown stays hidden */ }
}

function onWatchlistChange() { loadWatchlistHealth(); }

/* ── CUSTOM WEIGHTS (localStorage; what-if only) ──────── */
const DEFAULT_WEIGHTS = { volatility: 15, trend: 30, breadth: 25, momentum: 20, macro: 10 };
const WEIGHT_KEYS = ['volatility', 'trend', 'breadth', 'momentum', 'macro'];
function loadWeights() {
  try {
    const stored = JSON.parse(localStorage.getItem('pillarWeights')) || {};
    return { ...DEFAULT_WEIGHTS, ...stored };
  }
  catch { return { ...DEFAULT_WEIGHTS }; }
}
function saveWeightsLS(w) { localStorage.setItem('pillarWeights', JSON.stringify(w)); }
function isDefaultWeights(w) { return WEIGHT_KEYS.every(k => Number(w[k]) === DEFAULT_WEIGHTS[k]); }

const FALLBACK_DECISION_BANDS = [
  { min: 85, decision: 'RISK-ON', color: 'green', position: 'FULL EXPOSURE' },
  { min: 70, decision: 'CONSTRUCTIVE', color: 'green', position: 'STANDARD EXPOSURE' },
  { min: 55, decision: 'SELECTIVE', color: 'yellow', position: 'MODERATE EXPOSURE' },
  { min: 40, decision: 'DE-RISK', color: 'orange', position: 'REDUCED EXPOSURE' },
  { min: 0, decision: 'RISK-OFF', color: 'red', position: 'DEFENSIVE / FLAT' }
];

function decisionForScore(total, bands = FALLBACK_DECISION_BANDS) {
  const activeBands = Array.isArray(bands) && bands.length ? bands : FALLBACK_DECISION_BANDS;
  const orderedBands = [...activeBands].sort((a, b) => b.min - a.min);
  const band = orderedBands.find(b => total >= b.min) || orderedBands[orderedBands.length - 1];
  return {
    decision: band.decision,
    decision_color: band.color,
    position_size: band.position
  };
}

// Evidence-backed exposure dial (see docs/backtest-report.md): the no-pillar
// vol-target baseline that beat the score-timing rule. Pure HTML-string
// renderer so it is unit-testable; returns '' to hide the line when the
// payload field is null or malformed.
function volTargetLine(volTarget) {
  if (!volTarget || typeof volTarget.exposure_pct !== 'number') return '';
  return `<div class="dc-row" id="vol-target-line"><span class="dc-label">Vol-target</span>` +
    `<span>~${Math.round(volTarget.exposure_pct)}% exposure — no-pillar baseline that beat the score in the 2005–2026 backtest</span></div>`;
}

function buildWeightScenario(data) {
  const w = loadWeights();
  if (data.data_quality?.valid === false) {
    return { ...data, _weights: w, _customWeights: !isDefaultWeights(w) };
  }

  const p = data.pillars;
  let total = Math.round(
    p.volatility.score * w.volatility / 100 +
    p.trend.score      * w.trend      / 100 +
    p.breadth.score    * w.breadth    / 100 +
    p.momentum.score   * w.momentum   / 100 +
    p.macro.score      * w.macro      / 100
  );

  if (data.safety_max_score !== null && data.safety_max_score !== undefined) {
    total = Math.min(total, data.safety_max_score);
  }

  const verdict = decisionForScore(total, data.decision_bands);
  return { ...data, total_score: total, ...verdict, _weights: w, _customWeights: !isDefaultWeights(w) };
}

/* ── SETTINGS DRAWER ───────────────────────────────────── */
let _settingsReturnFocus = null;

function toggleSettings() {
  const overlay = $('settings-overlay');
  const isOpen = overlay.classList.toggle('open');
  overlay.setAttribute('aria-hidden', isOpen ? 'false' : 'true');
  if (isOpen) {
    _settingsReturnFocus = document.activeElement;
    const w = loadWeights();
    ['v','tr','br','mo','ma'].forEach((k, i) => {
      const key = ['volatility','trend','breadth','momentum','macro'][i];
      $(`ws-${k}`).value = w[key];
      $(`wlbl-${k}`).textContent = w[key] + '%';
    });
    requestAnimationFrame(() => overlay.querySelector('.settings-close')?.focus());
  } else if (_settingsReturnFocus?.focus) {
    _settingsReturnFocus.focus();
    _settingsReturnFocus = null;
  }
}
function closeSettingsOnOverlay(e) { if (e.target === $('settings-overlay')) toggleSettings(); }

function onWeightChange() {
  const keys = [['v','volatility'],['tr','trend'],['br','breadth'],['mo','momentum'],['ma','macro']];
  const sum = keys.reduce((s, [k]) => s + parseInt($(`ws-${k}`).value), 0);
  keys.forEach(([k]) => $(`wlbl-${k}`).textContent = $(`ws-${k}`).value + '%');
  $('weight-sum-warn').style.display = sum !== 100 ? 'block' : 'none';
}
function applyWeights() {
  const keys = [['v','volatility'],['tr','trend'],['br','breadth'],['mo','momentum'],['ma','macro']];
  const sum = keys.reduce((s, [k]) => s + parseInt($(`ws-${k}`).value), 0);
  if (sum !== 100) return;
  const w = {};
  keys.forEach(([k, full]) => { w[full] = parseInt($(`ws-${k}`).value); });
  saveWeightsLS(w);
  if (_lastData) {
    renderWeights(buildWeightScenario(_lastData));
  }
  toggleSettings();
}
function resetWeights() {
  saveWeightsLS({ ...DEFAULT_WEIGHTS });
  ['v','tr','br','mo','ma'].forEach((k, i) => {
    const key = ['volatility','trend','breadth','momentum','macro'][i];
    $(`ws-${k}`).value = DEFAULT_WEIGHTS[key];
    $(`wlbl-${k}`).textContent = DEFAULT_WEIGHTS[key] + '%';
  });
  $('weight-sum-warn').style.display = 'none';
  if (_lastData) {
    renderWeights(buildWeightScenario(_lastData));
  }
}

/* ── THEME ─────────────────────────────────────────────── */
function toggleTheme() {
  const isLight = document.body.classList.toggle('light-theme');
  localStorage.setItem('theme', isLight ? 'light' : 'dark');
  updateThemeButton(isLight);
}
function updateThemeButton(isLight) {
  const btn = $('theme-btn');
  if (!btn) return;
  btn.textContent = isLight ? 'Use dark theme' : 'Use light theme';
  btn.setAttribute('aria-label', btn.textContent);
  const drawerBtn = $('theme-drawer-btn');
  if (drawerBtn) drawerBtn.textContent = btn.textContent;
}
function initTheme() {
  const isLight = localStorage.getItem('theme') === 'light';
  document.body.classList.toggle('light-theme', isLight);
  updateThemeButton(isLight);
}

/* ── EXPORT / COPY ─────────────────────────────────────── */
function copySnapshot() {
  if (!_lastData) return;
  const d = _lastData;
  const scenario = buildWeightScenario(_lastData);
  const p = d.pillars;
  const now = new Date().toLocaleString();
  const lines = [
    `=== Should I Trade? — ${now} ===`,
    `Decision: ${d.decision}  |  Score: ${d.total_score}/100  |  Size: ${d.position_size}`,
    ...(scenario._customWeights ? [
      `Custom-weight what-if: ${scenario.decision}  |  Score: ${scenario.total_score}/100  |  Size: ${scenario.position_size}`,
    ] : []),
    ``,
    `Pillars:`,
    `  Volatility : ${p.volatility.score}/100`,
    `  Trend      : ${p.trend.score}/100`,
    `  Breadth    : ${p.breadth.score}/100`,
    `  Momentum   : ${p.momentum.score}/100`,
    `  Macro      : ${p.macro.score}/100`,
    ``,
  ];
  const rt = document.querySelectorAll('.persona-card');
  if (rt.length) {
    lines.push('Roundtable:');
    rt.forEach(card => {
      const name = card.querySelector('.persona-name')?.textContent?.trim() || '';
      const verdict = card.querySelector('.persona-verdict')?.textContent?.trim() || '';
      if (name) lines.push(`  ${name}: ${verdict}`);
    });
  }
  navigator.clipboard.writeText(lines.join('\n')).then(() => {
    const btn = document.querySelector('button[onclick="copySnapshot()"]');
    if (btn) {
      const previous = btn.innerHTML;
      btn.textContent = 'Copied';
      setTimeout(() => { btn.innerHTML = previous; }, 1500);
    }
  });
}

/* ── WEIGHTS ───────────────────────────────────────────── */
function renderWeights(d) {
  const names = { volatility: 'Volatility', trend: 'Trend', breadth: 'Breadth', momentum: 'Momentum', macro: 'Macro' };
  const weights = d._weights || loadWeights();

  $('score-weights').innerHTML = WEIGHT_KEYS.map(k => {
    const sc = d.pillars[k].score;
    const w = weights[k];
    const c = scoreColor(sc);
    return `<div class="weight-row">
      <span class="weight-name">${names[k]}</span>
      <div class="weight-bar-wrap"><div class="weight-bar" style="width:${sc}%;background:${c}"></div></div>
      <div class="weight-right">
        <span class="weight-score" style="color:${c}">${sc}</span>
        <span class="weight-pct">· ${w}%</span>
      </div>
    </div>`;
  }).join('');

  const label = $('weight-total-label');
  if (label) label.textContent = d._customWeights ? 'WHAT-IF SCORE' : 'OFFICIAL SCORE';
  const note = $('weight-scenario-note');
  if (note) note.style.display = d._customWeights ? 'block' : 'none';
  $('total-score-bottom').textContent = `${d.total_score}/100`;
  $('total-score-bottom').style.color = scoreColor(d.total_score);
}

/* ── SCORE SPARKLINE ───────────────────────────────────── */
const SPARK_LINES = { total: true, v: false, tr: false, br: false, mo: false, ma: false };
const SPARK_COLORS = { total: '#e0e8f0', v: '#00b0ff', tr: '#00e676', br: '#ffd740', mo: '#ff9100', ma: '#7c4dff' };
let _sparkHistory = [];

function toggleSparkLine(key, el) {
  SPARK_LINES[key] = !SPARK_LINES[key];
  el.classList.toggle('dimmed', !SPARK_LINES[key]);
  el.setAttribute('aria-pressed', SPARK_LINES[key] ? 'true' : 'false');
  drawSparkline();
}

function drawSparkline() {
  const svg = $('sparkline');
  const history = _sparkHistory;
  if (!history || history.length < 2) {
    svg.innerHTML = '<text x="100" y="22" text-anchor="middle" font-size="9" fill="#5a7080">Collecting data…</text>';
    return;
  }
  const W = 400, H = 60;
  const n = history.length;
  const allVals = [];
  Object.keys(SPARK_LINES).forEach(k => { if (SPARK_LINES[k]) allVals.push(...history.map(h => h[k] ?? h.total)); });
  const min = Math.min(...allVals, 30);
  const max = Math.max(...allVals, 90);
  const xOf = i => (i / (n - 1)) * W;
  const yOf = v => H - ((v - min) / Math.max(1, max - min)) * (H - 4) - 2;
  let svgContent = '';
  Object.entries(SPARK_LINES).forEach(([key, visible]) => {
    if (!visible) return;
    const vals = history.map(h => h[key] ?? h.total);
    const pts = vals.map((v, i) => `${xOf(i).toFixed(1)},${yOf(v).toFixed(1)}`).join(' ');
    const isTotal = key === 'total';
    const last = vals[vals.length - 1];
    const col = isTotal ? (last >= 80 ? 'var(--green)' : last >= 60 ? 'var(--yellow)' : 'var(--red)') : SPARK_COLORS[key];
    svgContent += `<polyline points="${pts}" fill="none" stroke="${col}" stroke-width="${isTotal ? 1.6 : 1}" stroke-dasharray="${isTotal ? 'none' : '3,2'}" opacity="${isTotal ? 1 : 0.75}"/>`;
    if (isTotal) {
      const lx = xOf(n - 1).toFixed(1);
      const ly = yOf(last).toFixed(1);
      svgContent += `<circle cx="${lx}" cy="${ly}" r="2.2" fill="${col}"/>`;
    }
  });
  svg.innerHTML = svgContent;
  $('spark-range').textContent = `${history[0].ts}→${history[history.length-1].ts} · ${n} pts`;
}

async function renderSparkline() {
  try {
    const res = await fetch('/api/history-scores');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const { history } = await res.json();
    _sparkHistory = history || [];
    const svg = $('sparkline');
    if (!_sparkHistory.length) {
      svg.innerHTML = '<text x="100" y="22" text-anchor="middle" font-size="9" fill="#5a7080">Collecting data…</text>';
      $('spark-range').textContent = '—';
      return;
    }
    drawSparkline();
  } catch {
    $('sparkline').innerHTML = '';
  }
}

/* ── COLLAPSIBLE SECTIONS ──────────────────────────────── */
const _SECTION_DEFAULTS = { roundtable: false, watchlist: false };

function _sectionExpanded(id) {
  try { const v = localStorage.getItem(`section_${id}`); return v === null ? _SECTION_DEFAULTS[id] : v === 'true'; }
  catch { return _SECTION_DEFAULTS[id]; }
}

function toggleSection(id) {
  const body = document.getElementById(`section-body-${id}`);
  const btn  = document.getElementById(`section-toggle-${id}`);
  if (!body || !btn) return;
  const nowOpen = body.classList.toggle('section-open');
  btn.setAttribute('aria-expanded', String(nowOpen));
  btn.querySelector('.toggle-chevron').style.transform = nowOpen ? 'rotate(90deg)' : '';
  try { localStorage.setItem(`section_${id}`, String(nowOpen)); } catch {}
  if (nowOpen && id === 'roundtable' && !document.querySelector('.persona-card')) runRoundtable(true);
  if (nowOpen && id === 'watchlist' && !_watchlistData) loadWatchlistHealth();
}

function _initSection(id) {
  const body = document.getElementById(`section-body-${id}`);
  const btn  = document.getElementById(`section-toggle-${id}`);
  if (!body || !btn) return;
  const open = _sectionExpanded(id);
  if (open) body.classList.add('section-open');
  btn.setAttribute('aria-expanded', String(open));
  btn.querySelector('.toggle-chevron').style.transform = open ? 'rotate(90deg)' : '';
}

/* ── ROUNDTABLE ────────────────────────────────────────── */
// SVG icons used in roundtable buttons (match initial HTML renders in should-i-trade-v5.html)
const _BTN_PLAY_SVG = '<svg width="9" height="9" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" style="vertical-align:-1px;margin-right:3px"><polygon points="5 3 19 12 5 21 5 3"/></svg>';
const _BTN_STAR_SVG = '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" style="vertical-align:-1px;margin-right:3px"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>';

async function runRoundtable(auto=false, useAi=false) {
  const btn    = useAi ? $('rt-ai-btn') : $('rt-btn');
  const altBtn = useAi ? $('rt-btn')    : $('rt-ai-btn');
  if (btn)    btn.disabled    = true;
  if (altBtn) altBtn.disabled = true;
  if (btn) btn.innerHTML = useAi
    ? `${_BTN_STAR_SVG}Consulting AI desk…`
    : (auto ? `${_BTN_PLAY_SVG}Rule-based read` : `${_BTN_PLAY_SVG}Refreshing…`);
  try {
    const url = useAi ? '/api/analysis?ai=1' : '/api/analysis';
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    if (useAi && data.ai_used === false) _showToast('AI quota exhausted — showing rule-based analysis. Resets at midnight.', 'warn');
    else if (useAi && data.ai_used)      _showToast('AI analysis complete', 'ok');
    renderRoundtable(data.personas || []);
  } catch(e) {
    $('roundtable-grid').innerHTML = `<div style="grid-column:1/-1;color:var(--red);padding:14px;">Desk unavailable: ${esc(e.message)}</div>`;
  } finally {
    if (btn)    { btn.disabled = false; btn.innerHTML = useAi ? `${_BTN_STAR_SVG}Ask AI desk again` : `${_BTN_PLAY_SVG}Refresh read`; }
    if (altBtn) { altBtn.disabled = false; }
  }
}

function renderRoundtable(personas) {
  const AVATAR_SVG = {
    '📊': '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="8" y1="3" x2="8" y2="7"/><rect x="5" y="7" width="6" height="7"/><line x1="8" y1="14" x2="8" y2="19"/><line x1="16" y1="2" x2="16" y2="8"/><rect x="13" y="8" width="6" height="6"/><line x1="16" y1="14" x2="16" y2="21"/></svg>',
    '🌐': '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>',
    '🛡':  '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>',
    '🔄': '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>',
    '🎯': '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/></svg>',
  };
  const POINT_SVG = {
    '✅':  `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="var(--green)"   stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><polyline points="9 12 11 14 15 10"/></svg>`,
    '⚠️': `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="var(--yellow)"  stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`,
    '🔴': `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="var(--red)"     stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>`,
    '⚪':  `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="var(--muted)"  stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><line x1="8" y1="12" x2="16" y2="12"/></svg>`,
    '🎯': `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="var(--accent)"  stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/></svg>`,
    '⛔': `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="var(--red)"     stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><path d="M4.93 4.93l14.14 14.14"/></svg>`,
    '⚡': `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="var(--accent)"  stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>`,
  };
  $('roundtable-grid').innerHTML = personas.map((p, i) => {
    const stanceCol = p.stance_color || 'gray';
    const isHead = p.persona === 'The Desk Head';
    const bg = `rgba(${stanceCol === 'green' ? '0,230,118' : stanceCol === 'yellow' ? '255,215,64' : stanceCol === 'orange' ? '255,145,0' : stanceCol === 'red' ? '255,23,68' : '90,112,128'}, 0.15)`;
    const fg = `var(--${stanceCol === 'gray' ? 'muted' : stanceCol})`;
    const pts = (p.points || []).map(pt => `
      <div class="persona-point"><span class="icon">${POINT_SVG[pt.icon] || esc(pt.icon)}</span><span>${esc(pt.text)}</span></div>`).join('');
    const aiBadge = p.ai_powered
      ? ` <span class="ai-badge" aria-label="AI-generated, ${esc(p.latency_ms || '?')}ms total roundtable"><svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" style="vertical-align:-1px;margin-right:2px"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>AI</span>`
      : '';
    return `
      <div class="persona-card ${isHead ? 'desk-head' : ''}" data-i="${i}">
        <div class="persona-header">
          <div class="persona-id">
            <div class="persona-name">${AVATAR_SVG[p.avatar] || esc(p.avatar)} ${esc(p.persona)}${aiBadge}</div>
            <div class="persona-role">${esc(p.role)}</div>
          </div>
          <span class="persona-stance" style="background:${bg};color:${fg}">${esc(p.stance)}</span>
        </div>
        <div class="persona-read">"${esc(p.read)}"</div>
        <div class="persona-points">${pts}</div>
        <div class="persona-verdict">${esc(p.verdict)}</div>
      </div>`;
  }).join('');

}

/* ── FEAR & GREED (inline color helper, used in macro rows) ── */
function fngColor(score) {
  if (score <= 25) return '#ff1744';
  if (score <= 45) return '#ff9100';
  if (score <= 55) return '#ffd740';
  if (score <= 75) return '#69f0ae';
  return '#00e676';
}


/* ── OVERRIDE BANNER + CONFLICTS ───────────────────────── */
function renderConflicts(d) {
  // Override banner
  const overrides = d.override_reasons || [];
  const ob = $('override-banner');
  if (overrides.length) {
    ob.style.display = 'flex';
    ob.innerHTML = overrides.map(r => `<span>${esc(r)}</span>`).join('');
  } else {
    ob.style.display = 'none';
  }

  // Signal conflict cards
  const conflicts = d.conflicts || [];
  const cr = $('conflicts-row');
  if (!conflicts.length) { cr.style.display = 'none'; return; }
  cr.style.display = 'flex';
  const icons = { warning: '⚠️', caution: '🔶', info: 'ℹ️' };
  cr.innerHTML = `
    <div style="font-size:9px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;color:var(--muted);margin-bottom:2px;">⚡ SIGNAL CONFLICTS</div>
    ${conflicts.map(c => `
      <div class="conflict-card ${esc(c.severity)}">
        <div class="conflict-icon">${icons[c.severity] || '⚠️'}</div>
        <div class="conflict-body">
          <div class="conflict-title">${esc(c.title)}</div>
          <div class="conflict-detail">${esc(c.detail)}</div>
        </div>
      </div>`).join('')}`;
}

/* ── MAIN LOAD ─────────────────────────────────────────── */
async function load(isManual = false) {
  const isFirst = !_lastData;
  if (isFirst) {
    $('loading').style.display = 'flex';
    $('content').style.display = 'none';
  } else {
    // Background refresh: show subtle indicator, keep dashboard fully interactive
    $('refresh-dot').classList.add('active');
  }
  try {
    const res = await fetch('/api/dashboard');
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    const raw = await res.json();
    if (raw.error) throw new Error(raw.error);
    if (!validateDashboardPayload(raw)) throw new Error('Invalid dashboard payload');
    _lastData = raw;

    const weightScenario = buildWeightScenario(raw);

    // Batch all DOM mutations in one animation frame to avoid layout thrashing
    requestAnimationFrame(() => {
      renderHeader(raw);
      renderHero(raw);
      renderFuturesTape(raw.futures_tape);
      renderPillars(raw);
      renderConflicts(raw);
      renderBars('sector-bars',   raw.pillars.breadth.details.sector_data);
      renderBars('industry-bars', raw.pillars.breadth.details.industry_data);
      renderWeights(weightScenario);
      // Show/hide sparkline paused indicator based on data quality
      const paused = $('spark-paused');
      if (paused) paused.style.display = raw.data_quality?.valid === false ? 'inline' : 'none';
      if (isFirst) {
        $('loading').style.display = 'none';
        $('content').style.display = 'block';
        _initSection('roundtable');
        _initSection('watchlist');
      }
      // Stale-while-revalidate: keep pulse active while server refreshes in background.
      if (raw.stale) {
        $('refresh-dot').classList.add('active');
        const cdBgEl = $('countdown'); if (cdBgEl) cdBgEl.textContent = 'refreshing in background…';
      } else {
        $('refresh-dot').classList.remove('active');
      }
    });

    renderSparkline();
    if ((isManual || isFirst) && _sectionExpanded('watchlist')) loadWatchlistHealth();
    _nextRefreshAt = raw.stale ? 0 : Date.now() + AUTO_REFRESH_MS;

    // Fire alert if score zone changed since last load
    _maybeAlert(raw.total_score, raw.decision);

    if ((isManual || isFirst) && _sectionExpanded('roundtable')) {
      setTimeout(() => runRoundtable(true), 400);
    }
  } catch(e) {
    console.error('Dashboard load failed:', e);
    $('refresh-dot').classList.remove('active');
    if (isFirst) {
      $('loading').innerHTML = `<div style="color:var(--red);font-size:11px;text-align:center;padding:20px;">
        We could not load current market data.<br><button class="btn" style="margin-top:12px" onclick="load(true)">Retry</button></div>`;
    } else {
      // Background refresh failed — keep stale data visible, retry on next cycle
      _nextRefreshAt = Date.now() + AUTO_REFRESH_MS;
    }
  }
}

/* ── AUTO-REFRESH + COUNTDOWN ──────────────────────────── */
function tickCountdown() {
  const cdEl = $('countdown');
  if (!_nextRefreshAt) { if (cdEl) cdEl.textContent = ''; return; }
  const left = Math.max(0, _nextRefreshAt - Date.now());
  if (left === 0) {
    _nextRefreshAt = 0;
    if (cdEl) cdEl.textContent = 'refreshing…';
    load(false);
    return;
  }
  const m = Math.floor(left / 60000);
  const s = Math.floor((left % 60000) / 1000);
  if (cdEl) cdEl.textContent = `next refresh in ${m}:${s.toString().padStart(2, '0')}`;
}
setInterval(tickCountdown, 1000);

/* ── SCORE ZONE ALERTS ─────────────────────────────────────── */
// Maps a score to one of 5 named zones. Fires a desktop notification only
// when the zone changes (not on every score tick), to avoid alert fatigue.
let _alertsEnabled = false;
let _lastAlertZone = null;

function _scoreZone(score) {
  if (score === null || score === undefined) return null;
  if (score >= 85) return 'RISK-ON';
  if (score >= 70) return 'CONSTRUCTIVE';
  if (score >= 55) return 'SELECTIVE';
  if (score >= 40) return 'DE-RISK';
  return 'RISK-OFF';
}

function _updateAlertBtn() {
  const btn = $('alert-btn');
  if (!btn) return;
  btn.style.opacity = _alertsEnabled ? '1' : '0.45';
  btn.title = _alertsEnabled ? 'Alerts ON — click to disable' : 'Score zone change notifications (click to enable)';
  btn.textContent = `Score alerts: ${_alertsEnabled ? 'on' : 'off'}`;
  btn.setAttribute('aria-pressed', _alertsEnabled ? 'true' : 'false');
}

async function toggleAlerts() {
  if (!('Notification' in window)) {
    alert('Desktop notifications are not supported in this browser.');
    return;
  }
  if (!_alertsEnabled) {
    const perm = await Notification.requestPermission();
    if (perm !== 'granted') {
      alert('Notification permission denied. Enable it in browser settings.');
      return;
    }
    _alertsEnabled = true;
  } else {
    _alertsEnabled = false;
  }
  _updateAlertBtn();
}

function _maybeAlert(score, decision) {
  if (!_alertsEnabled) return;
  const zone = _scoreZone(score);
  if (!zone || zone === _lastAlertZone) return;
  const prev = _lastAlertZone;
  _lastAlertZone = zone;
  if (prev === null) return;   // suppress on first load — no "change" yet
  const emoji = zone === 'RISK-ON' ? '🟢' : zone === 'CONSTRUCTIVE' ? '🟩' :
                zone === 'SELECTIVE'    ? '🟡' : zone === 'DE-RISK'  ? '🟠' : '🔴';
  const iconSvg = encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><text y="26" font-size="28">${emoji}</text></svg>`
  );
  new Notification(`Should I Trade? → ${zone}`, {
    body: `Score ${score} • ${decision || zone}\nWas: ${prev}`,
    icon: `data:image/svg+xml,${iconSvg}`,
    tag:  'sit-score-alert',  // collapses duplicate rapid flips
  });
}

/* ── SERVER-SENT EVENTS ────────────────────────────────── */
// The server pushes a "dashboard" event immediately after each cache refresh.
// On receiving it we reload (unless a manual refresh is already in flight).
// Falls back gracefully to the tickCountdown polling if SSE closes or is unsupported.
let _sseSource = null;
let _sseRetryMs = 5000;

function connectSSE() {
  if (!window.EventSource) return;   // browser doesn't support SSE
  _sseSource = new EventSource('/api/stream');

  _sseSource.addEventListener('dashboard', (e) => {
    try {
      const msg = JSON.parse(e.data || '{}');
      // Eagerly update our zone baseline from server-known previous score
      if (_lastAlertZone === null && msg.previous_score != null) {
        _lastAlertZone = _scoreZone(msg.previous_score);
      }
    } catch {}
    // Only trigger if not already mid-refresh and countdown isn't imminent (< 3s)
    const left = _nextRefreshAt ? Math.max(0, _nextRefreshAt - Date.now()) : Infinity;
    if (left > 3000) load(false);
  });

  _sseSource.onopen = () => { _sseRetryMs = 5000; };

  _sseSource.onerror = () => {
    _sseSource.close();
    _sseSource = null;
    // Exponential back-off, cap at 60s
    setTimeout(connectSSE, _sseRetryMs);
    _sseRetryMs = Math.min(_sseRetryMs * 2, 60000);
  };
}

/* ── TOAST ─────────────────────────────────────────────── */
function _showToast(msg, type='ok') {
  let t = $('ai-toast');
  if (!t) {
    t = document.createElement('div');
    t.id = 'ai-toast';
    document.body.appendChild(t);
  }
  t.setAttribute('role', type === 'warn' ? 'alert' : 'status');
  t.setAttribute('aria-live', type === 'warn' ? 'assertive' : 'polite');
  t.className = 'ai-toast ' + (type === 'warn' ? 'ai-toast-warn' : 'ai-toast-ok');
  t.textContent = msg;
  t.style.opacity = '1';
  clearTimeout(t._timer);
  t._timer = setTimeout(() => { t.style.opacity = '0'; }, type === 'warn' ? 7000 : 4000);
}

/* ── KICKOFF ───────────────────────────────────────────── */
if (!globalThis.__TESTING__) {
  // Expose functions used by HTML inline event handlers (onclick=, oninput=, etc.)
  // Required because ES modules don't leak to global scope.
  window.copySnapshot           = copySnapshot;
  window.toggleSection          = toggleSection;
  window.toggleAlerts           = toggleAlerts;
  window.toggleTheme            = toggleTheme;
  window.toggleSettings         = toggleSettings;
  window.load                   = load;
  window.toggleSparkLine        = toggleSparkLine;
  window.onWatchlistChange      = onWatchlistChange;
  window.runRoundtable          = runRoundtable;
  window.closeSettingsOnOverlay = closeSettingsOnOverlay;
  window.onWeightChange         = onWeightChange;
  window.applyWeights           = applyWeights;
  window.resetWeights           = resetWeights;
  window.toggleDetail           = toggleDetail;
  window.selectWatchlistView    = selectWatchlistView;

  initTheme();
  initWatchlistDropdown();
  connectSSE();

  document.addEventListener('keydown', e => {
    const settingsOpen = $('settings-overlay').classList.contains('open');
    if (settingsOpen && e.key === 'Tab') {
      const focusable = [...$('settings-overlay').querySelectorAll(
        'button:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'
      )];
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last?.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first?.focus();
      }
      return;
    }
    if (e.key === 'Escape' && settingsOpen) {
      toggleSettings();
      return;
    }
  });

  load(true);
}

// ── Exports for unit testing ───────────────────────────────────────────────
export {
  scoreColor,
  colorClass,
  decisionForScore,
  chgStr,
  FALLBACK_DECISION_BANDS,
  DEFAULT_WEIGHTS,
  buildWeightScenario,
  buildRadarChart,
  validateDashboardPayload,
  isDefaultWeights,
  volTargetLine,
};
