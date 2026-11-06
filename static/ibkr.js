/* Read-only requests. Never submit or approve orders. */
'use strict';
const $ = id => document.getElementById(id);
let pending = false;
const number = value => Number.isFinite(value) ? value.toLocaleString(undefined, {maximumFractionDigits: 2}) : 'Unknown';
const when = value => value ? new Date(value).toLocaleString() : 'Unavailable';
function render(data) {
  pending = data.running;
  $('ibkr-refresh').disabled = pending;
  $('ibkr-status').textContent = data.error || (pending ? 'Checking broker cash and reference prices…' :
    data.snapshot ? (data.snapshot_stale ? 'Snapshot is older than 30 minutes. Request a fresh check.' : 'Snapshot ready. Orders remain disabled.') :
    'Enter your account suffix to request a fresh read-only snapshot.');
  if (data.analysis && data.analysis.report) {
    $('ibkr-analysis').textContent = data.analysis.report;
    const age = Date.now() - new Date(data.analysis.completed_at).getTime();
    $('ibkr-analysis-time').textContent = `${data.analysis.model} · ${when(data.analysis.completed_at)} · ${age > 1800000 ? 'Older than 30 minutes · ' : ''}Manual review required`;
  }
  const s = data.snapshot;
  if (!s) return;
  $('ibkr-results').hidden = false;
  $('ibkr-cash').textContent = `${number(s.cash_budget_base)} ${s.base_currency}`;
  $('ibkr-equity').textContent = `${number(s.equity_base)} ${s.base_currency}`;
  const known = s.rows.filter(r => r.whole_shares_with_cash !== null);
  $('ibkr-count').textContent = `${known.filter(r => r.whole_shares_with_cash > 0).length} / ${s.rows.length}`;
  $('ibkr-time').textContent = `${s.account_masked} · Broker snapshot ${when(s.broker_captured_at)} · Universe ${s.universe_date} · ${s.rows.length - known.length} unknown`;
  const rows = [...s.rows].sort((a, b) => (a.change_pct ?? Infinity) - (b.change_pct ?? Infinity));
  $('ibkr-rows').replaceChildren(...rows.map(r => {
    const row = document.createElement('tr');
    [r.symbol, number(r.price_usd), r.change_pct == null ? 'Unknown' : `${number(r.change_pct)}%`,
      r.whole_shares_with_cash == null ? 'Unknown / stale' : r.whole_shares_with_cash ? r.whole_shares_with_cash : 'Above cash budget',
      when(r.price_time ? r.price_time * 1000 : null)].forEach(value => {
      const cell = document.createElement('td'); cell.textContent = value; row.append(cell);
    });
    return row;
  }));
}
async function poll() {
  try {
    const response = await fetch('/api/ibkr', {cache: 'no-store'});
    if (!response.ok) throw new Error('Could not read monitor status.');
    render(await response.json());
  } catch (error) { $('ibkr-status').textContent = error.message; }
  if (pending) setTimeout(poll, 1500);
}
$('ibkr-form').addEventListener('submit', async event => {
  event.preventDefault();
  $('ibkr-refresh').disabled = true;
  try {
    const response = await fetch('/api/ibkr/refresh', {method: 'POST', headers: {
      'Content-Type': 'application/json', 'X-IBKR-Token': document.querySelector('meta[name="ibkr-token"]').content},
    body: JSON.stringify({account_suffix: $('ibkr-account').value, port: Number($('ibkr-port').value)})});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Refresh could not start.');
    pending = true; await poll();
  } catch (error) { $('ibkr-status').textContent = error.message; $('ibkr-refresh').disabled = false; }
});
poll();
