/* Research and explicitly confirmed manual orders. Model content never runs as code. */
'use strict';
const $ = id => document.getElementById(id);
let pending = false, snapshot = null, activeFilter = 'all', lastReport = '';
let volatilityRows = {};
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
function renderReport(text, target = $('ibkr-analysis')) {
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
  target.replaceChildren(fragment);
}
function renderEvidence(evidence, coverage = $('ibkr-evidence-coverage'), sources = $('ibkr-evidence-sources'), sourceList = $('ibkr-source-list')) {
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
  sourceList.replaceChildren(list);
  sources.hidden = !sourceList.childNodes.length;
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
    (sort === 'volatility' ? (volatilityRows[b.symbol]?.vol20_pct ?? -Infinity) - (volatilityRows[a.symbol]?.vol20_pct ?? -Infinity) : sort === 'price' ? (a.price_usd ?? Infinity) - (b.price_usd ?? Infinity) :
      (a.change_pct ?? Infinity) - (b.change_pct ?? Infinity)) || a.symbol.localeCompare(b.symbol));
  $('ibkr-visible-count').textContent = `${rows.length} of ${snapshot.rows.length} stocks`;
  if (!rows.length) {
    const tr = el('tr'), td = el('td', 'No stocks match. Try another ticker or filter.', 'ibkr-table-empty');
    td.colSpan = 7; tr.append(td); $('ibkr-rows').replaceChildren(tr); return;
  }
  $('ibkr-rows').replaceChildren(...rows.map(row => {
    const tr = el('tr');
    const symbol = el('td'); symbol.append(el('strong', row.symbol, 'ibkr-ticker')); tr.append(symbol);
    tr.append(el('td', number(row.price_usd), 'ibkr-price'));
    const direction = finite(row.change_pct) ? (row.change_pct < 0 ? 'negative' : row.change_pct > 0 ? 'positive' : 'flat') : 'unknown';
    const move = finite(row.change_pct) ? `${row.change_pct > 0 ? '+' : ''}${number(row.change_pct)}%` : '—';
    tr.append(el('td', move, `ibkr-move is-${direction}`));
    const vol = volatilityRows[row.symbol] || {};
    const volatility = el('td', finite(vol.vol20_pct) ? `${number(vol.vol20_pct)}%` : '—', 'ibkr-price');
    volatility.title = `Annualized historical volatility · completed bars through ${vol.as_of || 'unknown'}`;
    const sigma = el('td', finite(vol.last_close_sigma) ? `${number(vol.last_close_sigma)}σ` : '—', 'ibkr-price-time');
    sigma.title = `Last completed session shock vs its prior 20 sessions · ${vol.as_of || 'unknown'} · not an intraday probability`;
    tr.append(volatility, sigma);
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
  if (data.analysis) {
    $('ibkr-model-label').textContent = data.analysis.model_status === 'unavailable' ? 'AI unavailable' : String(data.analysis.model || '').includes('deepseek') ? 'DeepSeek Flash · fallback' : 'Big Pickle';
  }
  if (data.analysis && typeof data.analysis.report === 'string' && data.analysis.report) {
    if (data.analysis.report !== lastReport) { renderReport(data.analysis.report); lastReport = data.analysis.report; }
    const age = Date.now() - new Date(data.analysis.completed_at).getTime();
    $('ibkr-analysis-time').textContent = `${when(data.analysis.completed_at)} · ${data.analysis.market_session === 'closed' ? 'Market closed · closing data · ' : ''}${age > 1800000 ? 'Older than 30 minutes' : 'Latest report'} · Manual review`;
    if (data.analysis.completed_at !== lastEvidenceTimestamp) {
      renderEvidence(data.analysis.evidence); lastEvidenceTimestamp = data.analysis.completed_at;
    }
  }
  const scan = data.analysis?.evidence?.volatility_scan;
  if (scan?.rows) {
    volatilityRows = Object.fromEntries(scan.rows.map(row => [row.symbol, row]));
    $('ibkr-volatility-meta').textContent = `Volatility coverage ${scan.available}/${scan.universe_count} · 20/60/252 completed sessions · annualized historical estimates`;
  }
  const s = data.snapshot || (scan?.rows?.length ? {rows:scan.rows, base_currency:'', cash_budget_base:null,
    equity_base:null, account_masked:'Cash check unavailable', broker_captured_at:null, universe_date:'research universe'} : null);
  if (!s || !Array.isArray(s.rows)) return;
  snapshot = s;
  $('ibkr-cash').textContent = `${number(s.cash_budget_base)} ${s.base_currency}`;
  $('ibkr-equity').textContent = `${number(s.equity_base)} ${s.base_currency}`;
  const affordable = s.rows.filter(fits).length;
  const cashKnown = s.rows.some(row => finite(row.whole_shares_with_cash));
  $('ibkr-count').replaceChildren(document.createTextNode(`${cashKnown ? affordable : '—'} `), el('small', `/ ${s.rows.length}`));
  $('ibkr-all-count').textContent = s.rows.length;
  $('ibkr-fit-count').textContent = cashKnown ? affordable : '—';
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

// Explicit manual actions are separate from research/model output.
const deskToken = document.querySelector('meta[name="ibkr-token"]').content;
async function deskRequest(operation, body) {
  const response = await fetch('/api/ibkr/desk/' + operation, body === undefined ? {} : {
    method: 'POST', headers: {'Content-Type': 'application/json', 'X-IBKR-Token': deskToken}, body: JSON.stringify(body)
  });
  const result = await response.json();
  if (!response.ok || result.error) throw new Error(result.error || 'Request failed');
  return result;
}
let analysisBusy = false, chatHistory = [], chatSymbol = '', orderPreview = null, previewExpiry;
function analysisButtons(busy) {
  analysisBusy = busy;
  $('ibkr-run-analysis').disabled = busy;
  $('ibkr-chat-send').disabled = busy;
}
async function runAnalysis(symbol = '', question = '') {
  if (analysisBusy) return;
  const status = $(symbol ? 'ibkr-chat-status' : 'ibkr-job-status');
  analysisButtons(true);
  status.textContent = 'Collecting evidence and asking the agent… This can take several minutes.';
  try {
    if (symbol !== chatSymbol) { chatHistory = []; chatSymbol = symbol; $('ibkr-chat-messages').replaceChildren(); }
    const started = await deskRequest('research/start', {symbol, question, history: symbol ? chatHistory.slice(-8) : []});
    // Jobs continue server-side even if this page closes.
    let result;
    for (let attempt = 0; attempt < 800; attempt++) {
      await new Promise(resolve => setTimeout(resolve, 2000));
      const job = await deskRequest('research/jobs/' + started.job_id);
      if (job.state === 'complete') { result = job.result; break; }
      if (job.state === 'failed' || job.state === 'unknown') throw new Error(job.error || 'Analysis unavailable');
      status.textContent = job.state === 'queued' ? 'Queued behind another analysis…' : 'Analyzing fresh evidence…';
    }
    if (!result) throw new Error('Analysis is taking longer than expected. Check the scheduled report before retrying.');
    status.textContent = `${result.model || 'Statistics only — AI unavailable'} · ${when(result.completed_at)}`;
    if (symbol) {
      const user = el('p', `${symbol} · ${question}`, 'ibkr-chat-question');
      const answer = el('div', undefined, 'ibkr-research');
      renderReport(result.report, answer);
      const coverage = el('p', undefined, 'ibkr-evidence-coverage');
      const sources = el('details', undefined, 'ibkr-evidence-sources');
      const sourceList = el('div');
      sources.append(el('summary', 'Sources for this answer'), sourceList);
      renderEvidence(result.evidence, coverage, sources, sourceList);
      $('ibkr-chat-messages').append(user, answer, coverage, sources);
      chatHistory.push({role: 'user', content: question}, {role: 'assistant', content: result.report.slice(0, 4000)});
    } else { lastReport = ''; await poll(); }
  } catch (error) { status.textContent = error.message; }
  finally { analysisButtons(false); }
}
$('ibkr-run-analysis').addEventListener('click', () => runAnalysis());
$('ibkr-chat-form').addEventListener('submit', event => {
  event.preventDefault();
  const symbol = $('ibkr-chat-symbol').value.trim().toUpperCase();
  if (!/^[A-Z][A-Z0-9.-]{0,14}$/.test(symbol)) { $('ibkr-chat-status').textContent = 'Enter a stock ticker.'; return; }
  runAnalysis(symbol, $('ibkr-chat-question').value.trim());
});
function clearPreview() {
  orderPreview = null;
  clearTimeout(previewExpiry);
  $('ibkr-order-review').hidden = true;
  $('ibkr-order-agree').checked = false;
  $('ibkr-order-confirm').disabled = true;
}
$('ibkr-order-form').addEventListener('input', clearPreview);
$('ibkr-order-agree').addEventListener('change', () => {
  $('ibkr-order-confirm').disabled = !orderPreview || !$('ibkr-order-agree').checked;
});
async function loadOrderStatus() {
  try {
    const state = await deskRequest('orders/status');
    const intent = state.intent;
    $('ibkr-order-status').textContent = intent ? `${intent.symbol}: ${intent.state}. Review buy and profit orders in IBKR before another purchase.` :
      state.execution_enabled ? 'Manual execution enabled. Preview required. Autonomous entries disabled.' : 'Execution disabled. Gateway remains read-only until activation.';
    $('ibkr-order-preview').disabled = !state.execution_enabled || !!intent;
  } catch (error) { $('ibkr-order-status').textContent = error.message; $('ibkr-order-preview').disabled = true; }
}
$('ibkr-order-form').addEventListener('submit', async event => {
  event.preventDefault(); clearPreview();
  $('ibkr-order-preview').disabled = true;
  $('ibkr-order-status').textContent = 'Checking broker quote, settled cash, existing orders and commission…';
  try {
    const result = await deskRequest('orders/preview', {
      symbol: $('ibkr-order-symbol').value.trim().toUpperCase(),
      quantity: Number($('ibkr-order-quantity').value), limit_price: Number($('ibkr-order-limit').value)
    });
    orderPreview = result;
    const details = document.createDocumentFragment();
    for (const [label, value] of [
      ['Account', result.account_masked], ['Buy', `${result.quantity} ${result.symbol} · DAY limit $${number(result.limit_price)}`],
      ['Broker bid / ask', `$${number(result.bid)} / $${number(result.ask)}`], ['Cost reserve', `$${number(result.commission_reserve_usd)}`],
      ['Profit sell', `GTC limit $${number(result.take_profit_price)} · ${result.target_basis}`], ['Losses', 'Hold for now · no automatic stop-loss']
    ]) { details.append(el('dt', label), el('dd', value)); }
    $('ibkr-order-details').replaceChildren(details);
    $('ibkr-order-review').hidden = false;
    $('ibkr-order-status').textContent = 'Preview valid for 60 seconds. No order submitted.';
    previewExpiry = setTimeout(() => { clearPreview(); $('ibkr-order-status').textContent = 'Preview expired. Request a fresh preview.'; }, Math.max(0, result.expires_at * 1000 - Date.now()));
  } catch (error) { $('ibkr-order-status').textContent = error.message; }
  finally { $('ibkr-order-preview').disabled = false; }
});
$('ibkr-order-confirm').addEventListener('click', async () => {
  if (!orderPreview || !$('ibkr-order-agree').checked) return;
  const token = orderPreview.preview_token;
  clearPreview(); $('ibkr-order-preview').disabled = true;
  $('ibkr-order-status').textContent = 'Submitting confirmed order. Do not retry; check IBKR if the connection drops.';
  try {
    const result = await deskRequest('orders/submit', {preview_token: token, confirm: 'BUY'});
    $('ibkr-order-status').textContent = `${result.state} · Buy: ${result.buy_status}; profit sell: ${result.profit_status}. Confirm fills and any partial fills in IBKR.`;
  } catch (error) { $('ibkr-order-status').textContent = error.message; }
  await loadOrderStatus();
});
loadOrderStatus();
