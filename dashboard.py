"""Renders a self-contained HTML dashboard.

The data is embedded directly in the file rather than fetched, so the page works
when opened straight off disk with no local server and no file:// CORS problems.

Scraped titles are untrusted text, so everything interpolated into markup goes
through an escape helper rather than straight into innerHTML.
"""

import json

import config
import sites

TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PC Hardware Deals</title>
<style>
  :root {
    --bg: #f6f6f4; --panel: #ffffff; --text: #1b1b19; --muted: #6d6d66;
    --border: #e4e4de; --drop: #15803d; --drop-bg: #eaf6ee;
    --warn: #b45309; --warn-bg: #fdf3e3; --accent: #1e40af; --spark: #9a9a92;
    --field: #ffffff; --offer: #6d28d9; --offer-bg: #f2ecfd;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #17171a; --panel: #1f1f23; --text: #ececea; --muted: #9b9b95;
      --border: #32323a; --drop: #4ade80; --drop-bg: #16301f;
      --warn: #fbbf24; --warn-bg: #332611; --accent: #93b4ff; --spark: #6a6a72;
      --field: #26262c; --offer: #c4b5fd; --offer-bg: #2a2140;
    }
  }
  * { box-sizing: border-box; }
  /* An author `display` rule outranks the UA stylesheet's [hidden] rule, so
     without this the hidden views stay on screen when switching tabs. */
  [hidden] { display: none !important; }
  body {
    margin: 0; background: var(--bg); color: var(--text);
    font: 14px/1.5 -apple-system, "Segoe UI", Roboto, sans-serif; padding: 22px;
  }
  .wrap { max-width: 1500px; margin: 0 auto; }
  h1 { font-size: 20px; margin: 0 0 4px; letter-spacing: -0.01em; }
  .stats { color: var(--muted); font-size: 13px; margin-bottom: 16px; }
  .stats b { color: var(--text); font-weight: 600; }

  .tabs { display: flex; gap: 6px; margin-bottom: 14px; }
  .sitetabs { margin-bottom: 10px; }
  .sitetabs .tab { font-size: 15px; font-weight: 600; padding: 9px 22px; }
  .sitetabs .tab[aria-selected="true"] {
    background: var(--accent); border-color: var(--accent); color: #fff;
  }
  .tab {
    border: 1px solid var(--border); background: var(--panel); color: var(--text);
    padding: 7px 14px; border-radius: 8px; cursor: pointer; font-size: 13.5px;
  }
  .tab[aria-selected="true"] { background: var(--text); color: var(--bg); border-color: var(--text); }

  .controls {
    background: var(--panel); border: 1px solid var(--border); border-radius: 12px;
    padding: 12px 14px; margin-bottom: 16px;
  }
  .ctl-row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
  .ctl-row + .ctl-row { margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--border); }
  label.f { display: inline-flex; align-items: center; gap: 5px; font-size: 12.5px; color: var(--muted); }
  input, select {
    padding: 6px 9px; border-radius: 7px; border: 1px solid var(--border);
    background: var(--field); color: var(--text); font-size: 13px; font-family: inherit;
  }
  input[type="search"] { flex: 1; min-width: 180px; }
  input.num { width: 84px; }
  .chip {
    border: 1px solid var(--border); background: var(--panel); color: var(--text);
    padding: 5px 11px; border-radius: 999px; cursor: pointer; font-size: 12.5px;
  }
  .chip[aria-pressed="true"] { background: var(--text); color: var(--bg); border-color: var(--text); }
  .chip .n { opacity: .55; margin-left: 4px; }
  .offer-tag {
    background: var(--offer-bg); color: var(--offer); font-weight: 600;
    padding: 3px 9px; border-radius: 6px; font-size: 12px;
  }
  button.link {
    background: none; border: none; color: var(--accent); cursor: pointer;
    font-size: 12.5px; padding: 4px 6px; font-family: inherit;
  }

  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; align-items: start; }
  @media (max-width: 1100px) { .grid { grid-template-columns: 1fr; } }
  .panel { background: var(--panel); border: 1px solid var(--border); border-radius: 12px; overflow: hidden; }
  .panel > h2 { font-size: 15px; margin: 0; padding: 14px 16px 6px; }
  .panel > .sub {
    color: var(--muted); font-size: 12.5px; padding: 0 16px 12px;
    border-bottom: 1px solid var(--border); margin: 0;
  }
  .row { display: flex; gap: 12px; padding: 12px 16px; border-bottom: 1px solid var(--border); align-items: flex-start; }
  .row:last-child { border-bottom: none; }
  .row img { width: 48px; height: 48px; object-fit: contain; flex: none; border-radius: 6px; }
  .info { flex: 1; min-width: 0; }
  .title {
    display: block; color: var(--text); text-decoration: none; font-weight: 500;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap; margin-bottom: 3px;
  }
  .title:hover { color: var(--accent); text-decoration: underline; }
  .meta { color: var(--muted); font-size: 12.5px; }
  .price { font-weight: 650; font-size: 15px; }
  .was { color: var(--muted); text-decoration: line-through; margin-left: 6px; font-size: 12.5px; }
  .eff { color: var(--offer); font-weight: 650; margin-left: 6px; font-size: 13.5px; }
  .num-cell { flex: none; text-align: right; min-width: 96px; }
  .badge { display: inline-block; padding: 2px 7px; border-radius: 6px; font-size: 12px; font-weight: 600; }
  .badge.drop { background: var(--drop-bg); color: var(--drop); }
  .badge.warn { background: var(--warn-bg); color: var(--warn); }
  .tag { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: .04em; }
  .low { color: var(--drop); font-size: 12px; font-weight: 600; }
  .stale { font-size: 11px; color: var(--warn); font-weight: 600; }
  .empty { padding: 28px 16px; color: var(--muted); }
  .empty b { color: var(--text); }
  .more { width: 100%; padding: 11px; background: none; border: none; border-top: 1px solid var(--border); color: var(--accent); cursor: pointer; font-size: 13px; }
  svg.spark { display: block; margin-top: 4px; }

  .tablewrap { overflow-x: auto; }
  table { border-collapse: collapse; width: 100%; font-size: 13px; }
  th, td { padding: 9px 12px; text-align: left; border-bottom: 1px solid var(--border); white-space: nowrap; }
  th { font-size: 11.5px; text-transform: uppercase; letter-spacing: .04em; color: var(--muted); font-weight: 600; }
  td.r, th.r { text-align: right; }
  td.name { white-space: normal; min-width: 280px; max-width: 460px; }
  tr.is-stale td { opacity: .55; }
  .per-tb { color: var(--accent); font-weight: 600; }
  .best { display: inline-flex; flex-wrap: wrap; gap: 4px 14px; }
  .best a { color: var(--text); }
</style>
</head>
<body>
<div class="wrap">
  <h1>PC Hardware Deals</h1>
  <div class="tabs sitetabs" id="siteTabs" role="tablist"></div>
  <div class="stats" id="stats"></div>

  <div class="tabs" role="tablist">
    <button class="tab" id="tab-deals" role="tab">Deals</button>
    <button class="tab" id="tab-tracked" role="tab">Tracked items</button>
  </div>

  <div class="controls">
    <div class="ctl-row">
      <input type="search" id="q" placeholder="Filter by name, e.g. 9800X3D, 32GB, OLED">
      <label class="f">Sort
        <select id="sort">
          <option value="default">Panel default</option>
          <option value="price_asc">Price: low to high</option>
          <option value="price_desc">Price: high to low</option>
          <option value="drop_pct">Real drop %</option>
          <option value="drop_abs">Real drop &#8377;</option>
          <option value="badge_pct">Badge discount %</option>
          <option value="recent">Recently seen</option>
          <option value="per_tb">Storage &#8377; per TB</option>
          <option value="target_total">Storage total for target</option>
        </select>
      </label>
      <label class="f">&#8377; min <input class="num" type="number" id="minPrice" min="0" step="500"></label>
      <label class="f">&#8377; max <input class="num" type="number" id="maxPrice" min="0" step="500"></label>
      <label class="f">Min off % <input class="num" type="number" id="minOff" min="0" max="99"></label>
      <label class="f"><input type="checkbox" id="hideSus"> Hide inflated MRP</label>
      <label class="f"><input type="checkbox" id="showStale"> Show stale</label>
      <button class="link" id="reset">Reset</button>
    </div>
    <div class="ctl-row">
      <span class="offer-tag">Bank / coupon offer</span>
      <label class="f">% off <input class="num" type="number" id="offerPct" min="0" max="90" step="1"></label>
      <label class="f">capped at &#8377; <input class="num" type="number" id="offerCap" min="0" step="100"></label>
      <label class="f">plus flat &#8377; <input class="num" type="number" id="offerFlat" min="0" step="100"></label>
      <span class="meta" id="offerNote"></span>
    </div>
    <div class="ctl-row" id="storageRow">
      <span class="offer-tag">Storage</span>
      <label class="f">Target <input class="num" type="number" id="target" min="0" step="any"></label>
      <select id="targetUnit" aria-label="Target unit"><option>TB</option><option>GB</option></select>
      <span class="meta best" id="storageNote"></span>
    </div>
    <div class="ctl-row" id="chips"></div>
  </div>

  <div id="view-deals" class="grid">
    <section class="panel">
      <h2>Real price drops</h2>
      <p class="sub">Measured against this tracker's own recorded history. This is the trustworthy signal.</p>
      <div id="drops"></div>
    </section>
    <section class="panel">
      <h2 id="badgeTitle">Badge discounts</h2>
      <p class="sub" id="badgeSub"></p>
      <div id="badges"></div>
    </section>
  </div>

  <div id="view-tracked" hidden>
    <section class="panel">
      <h2>Everything being tracked</h2>
      <p class="sub" id="trackedSub"></p>
      <div class="tablewrap"><table>
        <thead><tr>
          <th>Product</th><th>Category</th><th class="r">Price</th>
          <th class="r" id="thEff">After offer</th>
          <th class="r" id="thPerTb">&#8377; / TB</th><th class="r" id="thTarget">For target</th>
          <th class="r">Badge</th>
          <th class="r">Last drop</th><th class="r">Lowest seen</th>
          <th class="r">Obs</th><th>Tracked since</th><th>Last seen</th>
        </tr></thead>
        <tbody id="trackedBody"></tbody>
      </table></div>
      <div id="trackedMore"></div>
    </section>
  </div>
</div>

<script type="application/json" id="payload">__PAYLOAD__</script>
<script>
const DATA = JSON.parse(document.getElementById('payload').textContent);
const rows = DATA.rows, stats = DATA.stats, cats = DATA.categories;
const siteLabels = DATA.sites;
const siteKeys = Object.keys(siteLabels);

const DEFAULTS = {
  site: siteKeys[0], view: 'deals', cat: 'all', q: '', sort: 'default',
  minPrice: '', maxPrice: '', minOff: '',
  offerPct: '', offerCap: '', offerFlat: '',
  target: '', targetUnit: 'TB',
  hideSus: false, showStale: false
};
const KEY = 'flipkart-deal-tracker/settings';
let state = Object.assign({}, DEFAULTS);
try {
  const saved = localStorage.getItem(KEY);
  if (saved) state = Object.assign(state, JSON.parse(saved));
} catch (e) { /* private window, blocked storage - defaults are fine */ }
// A remembered site may no longer exist if it was removed from ENABLED_SITES.
if (!siteLabels[state.site]) state.site = siteKeys[0];

let limits = { drops: 40, badges: 40, tracked: 60 };

const save = () => {
  try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {}
};

const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g,
  c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const inr = (n) => '₹' + (n == null ? '-' : Math.round(n).toLocaleString('en-IN'));
const num = (v) => (v === '' || v == null || isNaN(parseFloat(v))) ? null : parseFloat(v);
const day = (iso) => iso ? new Date(iso).toLocaleDateString('en-IN',
  { day: '2-digit', month: 'short' }) : '-';

const offerActive = () => (num(state.offerPct) > 0) || (num(state.offerFlat) > 0);

function effective(r) {
  let off = 0;
  const pct = num(state.offerPct), cap = num(state.offerCap), flat = num(state.offerFlat);
  if (pct > 0) {
    off = r.price * pct / 100;
    if (cap > 0) off = Math.min(off, cap);      // bank offers are capped
  }
  if (flat > 0) off += flat;
  return Math.max(0, Math.round(r.price - off));
}
const shownPrice = (r) => offerActive() ? effective(r) : r.price;

// Storage maths, in decimal units as drives are sold (1 TB = 1000 GB), so a
// "1000 GB" and a "1 TB" listing compare equal. A 4 TB target from 128 GB
// sticks needs 32 of them. Prices follow the offer fields, so per-TB and
// totals reflect what you would actually pay.
const STORAGE = new Set(DATA.storage_categories);
const isStorage = (r) => STORAGE.has(r.category) && r.capacity_gb > 0;
const perTb = (r) => isStorage(r) ? shownPrice(r) / (r.capacity_gb / 1000) : null;
const targetGb = () => {
  const t = num(state.target);
  return t > 0 ? t * (state.targetUnit === 'GB' ? 1 : 1000) : null;
};
// The small tolerance keeps float noise from buying one drive too many.
const unitsFor = (r) => isStorage(r) && targetGb()
  ? Math.max(1, Math.ceil(targetGb() / r.capacity_gb - 1e-9)) : null;
const targetTotal = (r) => unitsFor(r) == null ? null : unitsFor(r) * shownPrice(r);
const fmtCap = (gb) => gb >= 1000 ? +(gb / 1000).toFixed(2) + ' TB' : +gb.toFixed(0) + ' GB';
const targetLabel = () => fmtCap(targetGb());
// Ascending sort with non-storage rows (null) always at the bottom.
const nullsLast = (f) => (a, b) => {
  const x = f(a), y = f(b);
  if (x == null || y == null) return (x == null) - (y == null);
  return x - y;
};

function passes(r, ignoreCat) {
  // Retailers are mutually exclusive: the selected tab is the only one shown.
  if (r.source !== state.site) return false;
  if (r.stale && !state.showStale) return false;
  if (!ignoreCat && state.cat !== 'all' && r.category !== state.cat) return false;
  if (state.q && !r.title.toLowerCase().includes(state.q)) return false;
  if (state.hideSus && r.suspicious_mrp) return false;
  const lo = num(state.minPrice), hi = num(state.maxPrice), off = num(state.minOff);
  const p = shownPrice(r);
  if (lo != null && p < lo) return false;
  if (hi != null && p > hi) return false;
  if (off != null && Math.max(r.badge_pct || 0, r.drop_pct || 0) < off) return false;
  return true;
}

const SORTS = {
  price_asc:  (a, b) => shownPrice(a) - shownPrice(b),
  price_desc: (a, b) => shownPrice(b) - shownPrice(a),
  drop_pct:   (a, b) => (b.drop_pct || 0) - (a.drop_pct || 0),
  drop_abs:   (a, b) => (b.drop_abs || 0) - (a.drop_abs || 0),
  badge_pct:  (a, b) => (b.badge_pct || 0) - (a.badge_pct || 0),
  recent:     (a, b) => String(b.last_seen).localeCompare(String(a.last_seen)),
  per_tb:     nullsLast(perTb),
  // Without a target this is the same ranking as per TB.
  target_total: (a, b) => targetGb() ? nullsLast(targetTotal)(a, b) : nullsLast(perTb)(a, b)
};

function sorted(list, fallbackKey) {
  const cmp = SORTS[state.sort] || SORTS[fallbackKey];
  return list.slice().sort(cmp);
}

function sparkline(points) {
  if (!points || points.length < 3) return '';
  const w = 90, h = 20, min = Math.min(...points), max = Math.max(...points);
  const span = max - min || 1;
  const d = points.map((p, i) =>
    `${(i / (points.length - 1) * w).toFixed(1)},${(h - (p - min) / span * h).toFixed(1)}`).join(' ');
  return `<svg class="spark" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" aria-hidden="true">
    <polyline points="${d}" fill="none" stroke="var(--spark)" stroke-width="1.5"
      stroke-linejoin="round" stroke-linecap="round"/></svg>`;
}

function priceLine(r, mode) {
  const was = mode === 'drop'
    ? (r.prev_price ? `<span class="was">${inr(r.prev_price)}</span>` : '')
    : (r.mrp ? `<span class="was">${inr(r.mrp)}</span>` : '');
  const eff = offerActive()
    ? `<span class="eff">&rarr; ${inr(effective(r))}</span>` : '';
  return `<span class="price">${inr(r.price)}</span>${was}${eff}`;
}

function storageLine(r) {
  if (!isStorage(r)) return '';
  const n = unitsFor(r);
  return `<div class="meta"><span class="per-tb">${inr(perTb(r))}/TB</span>
    &middot; ${fmtCap(r.capacity_gb)}
    ${n != null ? ` &middot; ${n} &times; = <b>${inr(targetTotal(r))}</b> for ${targetLabel()}` : ''}</div>`;
}

function rowHtml(r, mode) {
  const img = r.image ? `<img src="${esc(r.image)}" alt="" loading="lazy">` : '';
  const right = mode === 'drop'
    ? `<div class="badge drop">-${r.drop_pct}%</div>
       <div class="meta" style="margin-top:3px">${inr(r.drop_abs)} off</div>`
    : `<div class="badge ${r.suspicious_mrp ? 'warn' : 'drop'}">${r.badge_pct}%</div>
       ${r.suspicious_mrp ? '<div class="meta" style="margin-top:3px">check MRP</div>' : ''}`;

  return `<div class="row">
    ${img}
    <div class="info">
      <a class="title" href="${esc(r.url)}" target="_blank" rel="noopener"
         title="${esc(r.title)}">${esc(r.title)}</a>
      <div>${priceLine(r, mode)}
        ${r.is_low && mode === 'drop' ? '<span class="low">lowest seen</span>' : ''}
        ${r.stale ? '<span class="stale">stale</span>' : ''}</div>
      ${storageLine(r)}
      <div class="meta"><span class="tag">${esc(cats[r.category] || r.category)}</span>
        ${r.rating ? ' &middot; ' + r.rating + '★' : ''}
        ${mode === 'drop' ? ' &middot; ' + r.observations + ' observations' : ''}</div>
      ${mode === 'drop' ? sparkline(r.spark) : ''}
    </div>
    <div class="num-cell">${right}</div>
  </div>`;
}

function renderPanel(el, list, mode, key, emptyHtml) {
  if (!list.length) { el.innerHTML = emptyHtml; return; }
  const shown = list.slice(0, limits[key]);
  el.innerHTML = shown.map(r => rowHtml(r, mode)).join('') +
    (list.length > shown.length
      ? `<button class="more">Show ${Math.min(40, list.length - shown.length)} more of ${list.length}</button>`
      : '');
  const btn = el.querySelector('.more');
  if (btn) btn.onclick = () => { limits[key] += 40; render(); };
}

function renderTracked(list) {
  const shown = list.slice(0, limits.tracked);
  document.getElementById('thEff').hidden = !offerActive();
  const showTb = list.some(isStorage), showTarget = showTb && targetGb() != null;
  document.getElementById('thPerTb').hidden = !showTb;
  const thT = document.getElementById('thTarget');
  thT.hidden = !showTarget;
  if (showTarget) thT.textContent = `For ${targetLabel()}`;
  document.getElementById('trackedBody').innerHTML = shown.map(r => `
    <tr class="${r.stale ? 'is-stale' : ''}">
      <td class="name"><a class="title" href="${esc(r.url)}" target="_blank"
          rel="noopener" title="${esc(r.title)}">${esc(r.title)}</a></td>
      <td><span class="tag">${esc(cats[r.category] || r.category)}</span></td>
      <td class="r">${inr(r.price)}</td>
      ${offerActive() ? `<td class="r eff">${inr(effective(r))}</td>` : '<td class="r" hidden></td>'}
      <td class="r per-tb" ${showTb ? '' : 'hidden'}>${isStorage(r) ? inr(perTb(r)) : '-'}</td>
      <td class="r" ${showTarget ? '' : 'hidden'}>${unitsFor(r) != null
          ? `${unitsFor(r)} &times; = ${inr(targetTotal(r))}` : '-'}</td>
      <td class="r">${r.badge_pct != null
          ? `<span class="badge ${r.suspicious_mrp ? 'warn' : 'drop'}">${r.badge_pct}%</span>` : '-'}</td>
      <td class="r">${r.drop_pct != null
          ? `<span class="badge drop">-${r.drop_pct}%</span>` : '-'}</td>
      <td class="r">${inr(r.window_min)}${r.is_low ? ' <span class="low">now</span>' : ''}</td>
      <td class="r">${r.observations}</td>
      <td>${day(r.first_seen)}</td>
      <td>${day(r.last_seen)}${r.stale ? ' <span class="stale">stale</span>' : ''}</td>
    </tr>`).join('');

  document.getElementById('trackedMore').innerHTML = list.length > shown.length
    ? `<button class="more">Show ${Math.min(60, list.length - shown.length)} more of ${list.length}</button>` : '';
  const btn = document.querySelector('#trackedMore .more');
  if (btn) btn.onclick = () => { limits.tracked += 60; render(); };

  const siteRows = rows.filter(r => r.source === state.site);
  const staleCount = siteRows.filter(r => r.stale).length;
  document.getElementById('trackedSub').textContent =
    `${list.length} of ${siteRows.length} tracked ${siteLabels[state.site]} products shown. `
    + `${staleCount} have not been seen in the last ${stats.stale_after_hours} hours`
    + `${state.showStale ? '' : ' and are hidden'}.`;
}

function paintSiteTabs() {
  const el = document.getElementById('siteTabs');
  el.innerHTML = '';
  for (const key of siteKeys) {
    const n = rows.filter(r => r.source === key && (!r.stale || state.showStale)).length;
    const b = document.createElement('button');
    b.className = 'tab';
    b.setAttribute('role', 'tab');
    b.setAttribute('aria-selected', key === state.site);
    b.innerHTML = esc(siteLabels[key]) + ` <span class="n">${n}</span>`;
    b.onclick = () => {
      state.site = key;
      state.cat = 'all';                 // categories differ in size per site
      limits = { drops: 40, badges: 40, tracked: 60 };
      save(); render();
    };
    el.appendChild(b);
  }
}

function paintChips() {
  const base = rows.filter(r => passes(r, true));
  const counts = {};
  for (const r of base) counts[r.category] = (counts[r.category] || 0) + 1;

  const mk = (key, label, n) => {
    const b = document.createElement('button');
    b.className = 'chip';
    b.innerHTML = esc(label) + (n != null ? ` <span class="n">${n}</span>` : '');
    b.setAttribute('aria-pressed', key === state.cat);
    b.onclick = () => { state.cat = key; limits = { drops: 40, badges: 40, tracked: 60 }; save(); render(); };
    return b;
  };
  const el = document.getElementById('chips');
  el.innerHTML = '';
  el.appendChild(mk('all', 'All', base.length));
  for (const [k, label] of Object.entries(cats)) el.appendChild(mk(k, label, counts[k] || 0));
}

// Cheapest SSD vs cheapest HDD under the current filters, whichever category
// chip is selected, so the two can be compared side by side.
function paintStorage() {
  const row = document.getElementById('storageRow');
  row.hidden = state.cat !== 'all' && !STORAGE.has(state.cat);
  if (row.hidden) return;
  const base = rows.filter(r => passes(r, true) && isStorage(r));
  const key = targetGb() ? targetTotal : perTb;
  const parts = [];
  for (const c of STORAGE) {
    const best = base.filter(r => r.category === c).sort(nullsLast(key))[0];
    if (!best) continue;
    const name = esc((cats[c] || c).replace(/\s*\(.*\)$/, ''));
    parts.push(`<span>Cheapest ${name}: <span class="per-tb">${inr(perTb(best))}/TB</span>`
      + (targetGb() ? ` (${unitsFor(best)} &times; = <b>${inr(targetTotal(best))}</b>)` : '')
      + ` &middot; <a href="${esc(best.url)}" target="_blank" rel="noopener"
          title="${esc(best.title)}">${esc(best.title.slice(0, 40))}&hellip;</a></span>`);
  }
  document.getElementById('storageNote').innerHTML = parts.length
    ? parts.join('') : 'No storage listings match these filters.';
}

function render() {
  document.getElementById('tab-deals').setAttribute('aria-selected', state.view === 'deals');
  document.getElementById('tab-tracked').setAttribute('aria-selected', state.view === 'tracked');
  document.getElementById('view-deals').hidden = state.view !== 'deals';
  document.getElementById('view-tracked').hidden = state.view !== 'tracked';

  const pct = num(state.offerPct), cap = num(state.offerCap), flat = num(state.offerFlat);
  document.getElementById('offerNote').textContent = offerActive()
    ? `Showing effective price: ${pct > 0 ? pct + '% off' : ''}`
      + `${pct > 0 && cap > 0 ? ' capped at ' + inr(cap) : ''}`
      + `${flat > 0 ? (pct > 0 ? ', plus ' : '') + inr(flat) + ' flat' : ''}.`
    : 'Set an offer to see what each item actually costs you.';

  paintSiteTabs();
  paintChips();
  paintStorage();

  const siteRows = rows.filter(r => r.source === state.site);
  const siteName = siteLabels[state.site];
  const trackedObs = siteRows.reduce((sum, r) => sum + r.observations, 0);
  document.getElementById('stats').innerHTML =
    `<b>${siteRows.length}</b> ${esc(siteName)} products tracked across ` +
    `<b>${Object.keys(cats).length}</b> categories &middot; ` +
    `<b>${trackedObs}</b> price observations &middot; <b>${stats.runs}</b> runs &middot; ` +
    `tracking for <b>${stats.days_tracking}</b> day${stats.days_tracking === 1 ? '' : 's'} &middot; ` +
    `updated ${new Date(stats.generated).toLocaleString('en-IN')}`;

  document.getElementById('badgeTitle').textContent = `${siteName} badge discounts`;
  document.getElementById('badgeSub').textContent =
    `What ${siteName} claims off its own listed MRP. Treat flagged rows with suspicion.`;

  const v = rows.filter(r => passes(r, false));

  // A retailer with nothing stored needs a different message from one whose
  // filters simply matched nothing.
  const noSiteData = siteRows.length === 0;
  const noDataHtml = `<div class="empty"><b>No ${esc(siteName)} data yet.</b><br>
    Nothing has been scraped for this retailer. Run:<br>
    <code>python run.py --sites ${esc(state.site)}</code></div>`;

  if (state.view === 'tracked') {
    if (noSiteData) {
      document.getElementById('trackedBody').innerHTML =
        `<tr><td colspan="12">${noDataHtml}</td></tr>`;
      document.getElementById('trackedMore').innerHTML = '';
      document.getElementById('trackedSub').textContent =
        `Nothing tracked for ${siteName} yet.`;
      return;
    }
    renderTracked(sorted(v, 'price_asc'));
    return;
  }

  const drops = sorted(v.filter(r => r.drop_pct != null), 'drop_pct');
  const badges = sorted(v.filter(r => r.badge_pct != null), 'badge_pct');

  renderPanel(document.getElementById('drops'), drops, 'drop', 'drops',
    noSiteData ? noDataHtml : `<div class="empty"><b>No recorded drops yet.</b><br>
     This panel fills in as the scheduled scrapes build up history &mdash; it compares each
     price against what this tracker saw before, so it needs at least two runs that catch an
     actual change. You have <b>${stats.runs}</b> run${stats.runs === 1 ? '' : 's'} over
     <b>${stats.days_tracking}</b> day${stats.days_tracking === 1 ? '' : 's'} so far.
     Expect it to get useful after about a week.</div>`);

  renderPanel(document.getElementById('badges'), badges, 'badge', 'badges',
    noSiteData ? noDataHtml
      : `<div class="empty">No listings with a discount badge match these filters.</div>`);
}

function bind(id, prop, kind) {
  const el = document.getElementById(id);
  if (kind === 'check') {
    el.checked = !!state[prop];
    el.onchange = () => { state[prop] = el.checked; limits = { drops: 40, badges: 40, tracked: 60 }; save(); render(); };
  } else {
    el.value = state[prop];
    const handler = () => {
      state[prop] = kind === 'lower' ? el.value.toLowerCase().trim() : el.value;
      limits = { drops: 40, badges: 40, tracked: 60 };
      save(); render();
    };
    el.oninput = handler;
    if (el.tagName === 'SELECT') el.onchange = handler;
  }
}

bind('q', 'q', 'lower');
bind('sort', 'sort');
bind('minPrice', 'minPrice');
bind('maxPrice', 'maxPrice');
bind('minOff', 'minOff');
bind('offerPct', 'offerPct');
bind('offerCap', 'offerCap');
bind('offerFlat', 'offerFlat');
bind('target', 'target');
bind('targetUnit', 'targetUnit');
bind('hideSus', 'hideSus', 'check');
bind('showStale', 'showStale', 'check');

document.getElementById('tab-deals').onclick = () => { state.view = 'deals'; save(); render(); };
document.getElementById('tab-tracked').onclick = () => { state.view = 'tracked'; save(); render(); };
document.getElementById('reset').onclick = () => {
  // Reset clears filters but stays on the retailer you are looking at.
  state = Object.assign({}, DEFAULTS, { site: state.site });
  save();
  for (const [id, prop] of [['q','q'],['sort','sort'],['minPrice','minPrice'],
      ['maxPrice','maxPrice'],['minOff','minOff'],['offerPct','offerPct'],
      ['offerCap','offerCap'],['offerFlat','offerFlat'],
      ['target','target'],['targetUnit','targetUnit']]) {
    document.getElementById(id).value = DEFAULTS[prop];
  }
  document.getElementById('hideSus').checked = false;
  document.getElementById('showStale').checked = false;
  limits = { drops: 40, badges: 40, tracked: 60 };
  render();
};

render();
</script>
</body>
</html>
"""


def render(rows: list[dict], stats: dict, out_path=None) -> str:
    out_path = out_path or config.DASHBOARD_PATH
    categories = {k: v["label"] for k, v in config.CATEGORIES.items()}
    storage = [k for k, v in config.CATEGORIES.items() if config.is_storage(v)]
    stats = dict(stats, stale_after_hours=config.STALE_AFTER_HOURS)

    # Enabled sites first, then any other retailer still present in stored data
    # so its history stays reachable after being removed from ENABLED_SITES.
    present = sorted({r.get("source") or "flipkart" for r in rows})
    keys = list(dict.fromkeys(list(config.ENABLED_SITES) + present))
    site_labels = {k: sites.SITES.get(k, {}).get("label", k.title()) for k in keys}

    payload = json.dumps(
        {"rows": rows, "stats": stats, "categories": categories,
         "sites": site_labels, "storage_categories": storage},
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("</", "<\\/")

    html = TEMPLATE.replace("__PAYLOAD__", payload)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    return str(out_path)
