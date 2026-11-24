// Window returns and window trade metrics computed in the browser (static/app.js).
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync(`${__dirname}/static/app.js`, 'utf8');
function grab(startSig, endSig) {
  const start = source.indexOf(startSig);
  const end = source.indexOf(endSig, start);
  assert(start >= 0 && end > start, `could not extract ${startSig}`);
  return source.slice(start, end);
}
const code = [
  grab('    function periodWindowStart(', '    function selectedWindowLabel('),
  grab('    function periodMetrics(', '    function pointPath('),
  grab('    function portfolioTimeWeightedReturns(', '    function normalizeReturnSeries('),
  grab('    function periodStartDate(', '    function periodFrictions('),
].join('\n');

function run(period, data, customStart = '2026-01-01') {
  const context = { selectedPeriod: period, selectedReturnMode: 'price', customPeriodStart: () => customStart };
  vm.createContext(context);
  vm.runInContext(code, context);
  return {
    window: context.filterByPeriod(data.valuation_series).map(p => p.date),
    totals: context.periodMetrics(data),
  };
}

const point = (date, value, contributions = 1000) => ({
  date, market_value: value, net_contributions: contributions, profit: value - contributions,
  priced_positions: 1, unpriced_positions: 0,
});
const flat = {
  date_range: { end: '2026-11-24' },
  totals: { return_pct: 0, net_contributions: 5000, realized_pl: 300 },
  // Month-end history, no trade in 2026 before February; +10% during January.
  valuation_series: [
    point('2025-11-30', 1000), point('2025-12-31', 1000), point('2026-01-31', 1100),
    point('2026-02-28', 1100), point('2026-11-17', 1100), point('2026-11-24', 1100),
  ],
  series: [
    { date: '2025-11-10', net_contributions: 3000, realized_pl: 300 },
    { date: '2026-02-02', net_contributions: 4000, realized_pl: 300 },
    { date: '2026-03-02', net_contributions: 5000, realized_pl: 300 },
  ],
};

// YTD starts from the 31 December close, so January's gain counts.
let result = run('ytd', flat);
assert.equal(result.window[0], '2025-12-31');
assert.equal(result.totals.return_pct.toFixed(2), '10.00');
assert.equal(result.totals.historical_profit, 100);

// Window trade metrics include the first trade inside the window.
result = run('custom', flat, '2026-01-01');
assert.equal(result.totals.net_contributions, 2000);
assert.equal(result.totals.realized_pl, 0);

// A single trade in the window: its own amount, not the all-time total.
result = run('custom', { ...flat, series: flat.series.slice(0, 2) }, '2026-01-01');
assert.equal(result.totals.net_contributions, 1000);
assert.equal(result.totals.realized_pl, 0);

// All trades inside the window: no base point, everything counts.
result = run('custom', flat, '2025-01-01');
assert.equal(result.totals.net_contributions, 5000);
assert.equal(result.totals.realized_pl, 300);

// No trade inside the window: nothing was contributed in it.
result = run('1w', flat);
assert.equal(result.totals.net_contributions, 0);
assert.deepEqual(result.window, ['2026-11-17', '2026-11-24']);

// A start that falls on a priced day uses that day, not an earlier neighbour.
result = run('custom', flat, '2026-01-31');
assert.equal(result.window[0], '2026-01-31');
assert.equal(result.totals.return_pct.toFixed(2), '0.00');

// The nearer neighbour wins when the start falls between two distant points.
result = run('custom', flat, '2026-02-25');
assert.equal(result.window[0], '2026-02-28');

// "All" keeps the server totals and the full history.
result = run('all', flat);
assert.equal(result.window.length, flat.valuation_series.length);
assert.equal(result.totals.net_contributions, 5000);

console.log('Period windows, base points and window trade metrics passed.');
