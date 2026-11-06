/* Read-only research workspace. All broker/model content is rendered as text. */
'use strict';
const $ = id => document.getElementById(id);
let pending = false, snapshot = null, activeFilter = 'all', lastReport = '';
let pollTimer, lastEvidenceTimestamp = null, autoRefreshRequested = false;
const finite = value => typeof value === 'number' && Number.isFinite(value);
const number = value => finite(value) ? value.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2}) : '—';
const when = value => value && Number.isFinite(new Date(value).getTime()) ? new Date(value).toLocaleString(undefined, {month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'}) : 'Unavailable';
const fits = row => finite(row.whole_shares_with_cash) && row.whole_shares_with_cash > 0;
function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function inline(parent, text) {
  for (const chunk of text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g)) {
    if (chunk.startsWith('**') && chunk.endsWith('**')) parent.append(el('strong', chunk.slice(2, -2)));
    else if (chunk.startsWith('`') && chunk.endsWith('`')) parent.append(el('code', chunk.slice(1, -1)));
    else parent.append(document.createTextNode(chunk));
  }
}
function renderReport(text) {
  const fragment = document.createDocumentFragment();
  let list = null, table = null;
  for (const raw of text.split('\n')) {
    const line = raw.trim();
    if (!line) { list = null; table = null; continue; }
    if (/^\|?[\s:|-]+\|[\s:|-]*$/.test(line)) continue;
    if (line.startsWith('|') && line.endsWith('|')) {
      if (!table) { table = el('table'); fragment.append(table); }
      const row = el('tr');
      for (const cell of line.slice(1, -1).split('|')) { const td = el('td'); inline(td, cell.trim()); row.append(td); }
      table.append(row); continue;
    }
    table = null;
    const bullet = line.match(/^(?:[-*]|\d+\.)\s+(.+)/);
    if (bullet) {
      if (!list) { list = el('ul'); fragment.append(list); }
      const item = el('li'); inline(item, bullet[1]); list.append(item); continue;
    }
    list = null;
    const heading = line.match(/^#{1,6}\s+(.+)/);
    const node = el(heading ? 'h3' : 'p'); inline(node, heading ? heading[1] : line); fragment.append(node);
  }
  $('ibkr-analysis').replaceChildren(fragment);
}
function renderEvidence(evidence) {
  const coverage = $('ibkr-evidence-coverage');
  const sources = $('ibkr-evidence-sources');
  if (!evidence || !evidence.coverage) { coverage.hidden = true; sources.hidden = true; return; }
  const c = evidence.coverage;
  coverage.hidden = false;
  coverage.textContent = `Deep checks · ${c.stocks} stocks · News ${c.news_symbols}/${c.stocks} · History ${c.histories}/${c.stocks} · Analyst coverage ${c.analysts}/${c.stocks}${evidence.status === 'unavailable' ? ' · Evidence unavailable' : ''}`;
  const list = document.createDocumentFragment();
  for (const stock of evidence.stocks || []) {
    const history = stock.history || {}, analysts = stock.analysts || {};
    const title = el('strong', stock.symbol);
    const item = el('div', undefined, 'ibkr-source-item'); item.append(title);
    item.append(el('p', `History: ${history.status || 'unavailable'}${history.last_bar_date ? ` · through ${history.last_bar_date}` : ''}. Analysts: ${analysts.status || 'unavailable'} · retrieved ${when(analysts.retrieved_at)}. Individual rating/target dates may be unknown.`));
    list.append(item);
  }
  for (const news of evidence.news?.items || []) {
    let url;
    try { url = new URL(news.link); } catch (_) { continue; }
    if (!['http:', 'https:'].includes(url.protocol)) continue;
    const item = el('div', undefined, 'ibkr-source-item');
    const link = el('a', `${news.id} · ${news.symbol} · ${news.title}`);
    link.href = url.href; link.target = '_blank'; link.rel = 'noopener noreferrer';
    item.append(link, el('p', `${news.source} · ${news.published || 'Publication date unavailable'} · Headline only`));
    list.append(item);
  }
  $('ibkr-source-list').replaceChildren(list);
  sources.hidden = !$('ibkr-source-list').childNodes.length;
}
function renderRows() {
  if (!snapshot || !Array.isArray(snapshot.rows)) return;
  const query = $('ibkr-search').value.trim().toUpperCase();
  const sort = $('ibkr-sort').value;
  const rows = snapshot.rows.filter(row =>
    (!query || String(row.symbol).toUpperCase().includes(query)) &&
    (activeFilter !== 'affordable' || fits(row)) &&
    (activeFilter !== 'falling' || (finite(row.change_pct) && row.change_pct < 0)));
  rows.sort((a, b) => sort === 'ticker' ? a.symbol.localeCompare(b.symbol) :
    (sort === 'price' ? (a.price_usd ?? Infinity) - (b.price_usd ?? Infinity) :
      (a.change_pct ?? Infinity) - (b.change_pct ?? Infinity)) || a.symbol.localeCompare(b.symbol));
  $('ibkr-visible-count').textContent = `${rows.length} of ${snapshot.rows.length} stocks`;
  if (!rows.length) {
    const tr = el('tr'), td = el('td', 'No stocks match. Try another ticker or filter.', 'ibkr-table-empty');
    td.colSpan = 5; tr.append(td); $('ibkr-rows').replaceChildren(tr); return;
  }
  $('ibkr-rows').replaceChildren(...rows.map(row => {
    const tr = el('tr');
    const symbol = el('td'); symbol.append(el('strong', row.symbol, 'ibkr-ticker')); tr.append(symbol);
    tr.append(el('td', number(row.price_usd), 'ibkr-price'));
    const direction = finite(row.change_pct) ? (row.change_pct < 0 ? 'negative' : row.change_pct > 0 ? 'positive' : 'flat') : 'unknown';
    const move = finite(row.change_pct) ? `${row.change_pct > 0 ? '+' : ''}${number(row.change_pct)}%` : '—';
    tr.append(el('td', move, `ibkr-move is-${direction}`));
    const quantity = el('td');
    quantity.append(el('span', !finite(row.whole_shares_with_cash) ? 'Unknown' : fits(row) ? `${row.whole_shares_with_cash} ${row.whole_shares_with_cash === 1 ? 'share' : 'shares'}` : 'Above budget', `ibkr-quantity ${fits(row) ? 'is-fit' : 'is-muted'}`));
    tr.append(quantity, el('td', when(row.price_time ? row.price_time * 1000 : null), 'ibkr-price-time'));
    return tr;
  }));
}
function render(data) {
  pending = Boolean(data.running);
  $('ibkr-refresh').disabled = pending;
  $('ibkr-refresh').classList.toggle('is-loading', pending);
  $('ibkr-refresh').querySelector('span').textContent = pending ? 'Refreshing…' : 'Refresh snapshot';
  const status = $('ibkr-status');
  status.classList.toggle('is-error', Boolean(data.error));
  status.classList.toggle('is-stale', Boolean(data.snapshot_stale && data.snapshot));
  status.textContent = data.error || (pending ? 'Reading cash and reference prices. Your previous snapshot stays visible.' :
    data.snapshot ? (data.snapshot_stale ? 'Snapshot older than 30 minutes. Refresh before reviewing affordability.' : 'Snapshot ready. Prices are references, not executable quotes.') :
    'Loading your saved IBKR connection…');
  if (data.analysis && typeof data.analysis.report === 'string' && data.analysis.report) {
    if (data.analysis.report !== lastReport) { renderReport(data.analysis.report); lastReport = data.analysis.report; }
    const age = Date.now() - new Date(data.analysis.completed_at).getTime();
    $('ibkr-analysis-time').textContent = `${when(data.analysis.completed_at)} · ${age > 1800000 ? 'Older than 30 minutes' : 'Latest report'} · Manual review`;
    if (data.analysis.completed_at !== lastEvidenceTimestamp) {
      renderEvidence(data.analysis.evidence); lastEvidenceTimestamp = data.analysis.completed_at;
    }
  }
  const s = data.snapshot;
  if (!s || !Array.isArray(s.rows)) return;
  snapshot = s;
  $('ibkr-cash').textContent = `${number(s.cash_budget_base)} ${s.base_currency}`;
  $('ibkr-equity').textContent = `${number(s.equity_base)} ${s.base_currency}`;
  const affordable = s.rows.filter(fits).length;
  $('ibkr-count').replaceChildren(document.createTextNode(`${affordable} `), el('small', `/ ${s.rows.length}`));
  $('ibkr-all-count').textContent = s.rows.length;
  $('ibkr-fit-count').textContent = affordable;
  $('ibkr-time').textContent = `${s.account_masked} · ${when(s.broker_captured_at)}`;
  $('ibkr-universe-date').textContent = `Universe · ${s.universe_date}`;
  $('ibkr-account-label').textContent = s.account_masked;

  const up = s.rows.filter(r => finite(r.change_pct) && r.change_pct > 0).length;
  const down = s.rows.filter(r => finite(r.change_pct) && r.change_pct < 0).length;
  const flat = s.rows.filter(r => r.change_pct === 0).length;
  const unknown = s.rows.length - up - down - flat;
  $('ibkr-breadth-label').textContent = `${up} up · ${down} down · ${flat} flat${unknown ? ` · ${unknown} unknown` : ''}`;
  $('ibkr-breadth-bar').replaceChildren(...[['positive', up], ['negative', down], ['flat', flat], ['unknown', unknown]].filter(([, n]) => n).map(([type, n]) => {
    const segment = el('span', undefined, `is-${type}`); segment.style.flexGrow = n; return segment;
  }));
  renderRows();
}
async function poll() {
  clearTimeout(pollTimer);
  try {
    const response = await fetch('/api/ibkr', {cache: 'no-store'});
    if (!response.ok) throw new Error('Could not read monitor status. Try refreshing the page.');
    const data = await response.json();
    render(data);
    if (!data.snapshot && !data.running && !data.error && !autoRefreshRequested) {
      autoRefreshRequested = true; await refreshSnapshot(); return;
    }
  } catch (error) { $('ibkr-status').textContent = error.message; $('ibkr-status').classList.add('is-error'); }
  pollTimer = setTimeout(poll, pending ? 1500 : 60000);
}
async function refreshSnapshot() {
  $('ibkr-refresh').disabled = true;
  try {
    const response = await fetch('/api/ibkr/refresh', {method: 'POST', headers: {
      'Content-Type': 'application/json', 'X-IBKR-Token': document.querySelector('meta[name="ibkr-token"]').content},
    body: JSON.stringify({})});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Refresh could not start.');
    pending = true; await poll();
  } catch (error) { $('ibkr-status').textContent = error.message; $('ibkr-status').classList.add('is-error'); $('ibkr-refresh').disabled = false; }
}
$('ibkr-refresh').addEventListener('click', refreshSnapshot);
document.querySelectorAll('[data-filter]').forEach(button => button.addEventListener('click', () => {
  activeFilter = button.dataset.filter;
  document.querySelectorAll('[data-filter]').forEach(item => item.setAttribute('aria-pressed', String(item === button)));
  renderRows();
}));
$('ibkr-search').addEventListener('input', renderRows);
$('ibkr-sort').addEventListener('change', renderRows);
$('ibkr-theme').addEventListener('click', () => {
  const current = document.documentElement.dataset.theme || (matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
  const theme = current === 'light' ? 'dark' : 'light';
  document.documentElement.dataset.theme = theme;
  try { localStorage.setItem('theme', theme); } catch (_) {}
});
poll();
