// Window figures shown beside each other agree on their span (static/app.js).
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

function metrics(period, data, mode = 'price', customStart = '2026-01-01') {
  const context = { selectedPeriod: period, selectedReturnMode: mode, customPeriodStart: () => customStart };
  vm.createContext(context);
  vm.runInContext(code, context);
  return context.periodMetrics(data);
}

const point = (date, value, contributions, extra = {}) => ({
  date, market_value: value, net_contributions: contributions, profit: value - contributions,
  priced_positions: 1, unpriced_positions: 0, ...extra,
});
const days = (from, to) => {
  const out = [];
  for (let d = new Date(`${from}T00:00:00Z`); d <= new Date(`${to}T00:00:00Z`); d.setUTCDate(d.getUTCDate() + 1)) {
    out.push(d.toISOString().slice(0, 10));
  }
  return out;
};

// 1,000 held, 1,000 more bought on 17 November, flat market. The 1W window runs from
// the 17 November close, which already holds the purchase: nothing moved in the week.
const startDayTrade = {
  date_range: { end: '2026-11-17' },
  totals: { return_pct: 0, net_contributions: 2000, realized_pl: 0 },
  valuation_series: days('2026-11-10', '2026-11-24').map(day => point(day, day < '2026-11-17' ? 1000 : 2000, day < '2026-11-17' ? 1000 : 2000)),
  series: [
    { date: '2026-11-10', net_contributions: 1000, realized_pl: 0 },
    { date: '2026-11-17', net_contributions: 2000, realized_pl: 0 },
  ],
};
let totals = metrics('1w', startDayTrade);
assert.equal(totals.net_contributions, 0, 'a trade on the window base day is already in the base value');
assert.equal(totals.historical_profit, 0);
assert.equal(totals.return_pct, 0);
assert.equal(totals.return_basis, 'time_weighted');

// A trade the day after the base point is inside the window.
const nextDay = {
  ...startDayTrade,
  valuation_series: days('2026-11-10', '2026-11-24').map(day => point(day, day < '2026-11-18' ? 1000 : 2000, day < '2026-11-18' ? 1000 : 2000)),
  series: [
    { date: '2026-11-10', net_contributions: 1000, realized_pl: 0 },
    { date: '2026-11-18', net_contributions: 2000, realized_pl: 50 },
  ],
};
totals = metrics('1w', nextDay);
assert.equal(totals.net_contributions, 1000);
assert.equal(totals.realized_pl, 50);

// A window that opens before the first valuation point starts from nothing.
totals = metrics('custom', startDayTrade, 'price', '2026-01-01');
assert.equal(totals.net_contributions, 2000);

// Total mode: the cash accounts are in the value, so their deposits are in the
// contributions too, as on the headline chart's invested line.
const withCash = {
  date_range: { end: '2026-11-24' },
  totals: {
    return_pct: 0, total_return_pct: 0, net_contributions: 1000, total_net_contributions: 31000,
    market_value: 1000, total_market_value: 31000, realized_pl: 0,
  },
  valuation_series: days('2026-11-10', '2026-11-24').map(day => {
    const cash = day >= '2026-11-20' ? 30000 : 0;
    return point(day, 1000, 1000, {
      total_market_value: 1000 + cash, total_net_contributions: 1000 + cash, total_profit: 0,
    });
  }),
  series: [{ date: '2026-11-01', net_contributions: 1000, realized_pl: 0 }],
};
totals = metrics('1w', withCash, 'total');
assert.equal(totals.net_contributions, 30000);
assert.equal(totals.return_pct, 0);
totals = metrics('all', withCash, 'total');
assert.equal(totals.net_contributions, 31000);
// Price mode keeps the trade-based figure.
assert.equal(metrics('1w', withCash, 'price').net_contributions, 0);

// With fewer than two points in the window the figure is the simple return since the
// first trade, and it is marked as such.
const sparse = {
  date_range: { end: '2026-11-24' },
  totals: { return_pct: 12.5, net_contributions: 1000, realized_pl: 0 },
  valuation_series: [point('2026-10-01', 1000, 1000), point('2026-11-24', 1125, 1000)],
  series: [{ date: '2026-10-01', net_contributions: 1000, realized_pl: 0 }],
};
totals = metrics('1w', sparse);
assert.equal(totals.return_basis, 'since_start');
assert.equal(totals.return_pct, 12.5);

// The headline sentence names each figure's span.
const ledeCode = grab('    let ledeTotals = null;', '    // Beside the headline:');
function lede(period, totalsIn) {
  const elements = {};
  const element = id => (elements[id] ||= { id, hidden: true, textContent: '', innerHTML: '', className: '' });
  const pct = new Intl.NumberFormat('en-IE', { maximumFractionDigits: 2, minimumFractionDigits: 2 });
  const euroWhole = new Intl.NumberFormat('en-IE', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 });
  const context = {
    selectedPeriod: period, selectedReturnMode: 'price', pct,
    moneyWhole: value => euroWhole.format(Number(value)),
    escapeHtml: value => String(value),
    signedClass: value => (Number(value) > 0 ? 'positive' : Number(value) < 0 ? 'negative' : ''),
    selectedWindowLabel: () => 'Window',
    document: { getElementById: element },
  };
  vm.createContext(context);
  vm.runInContext(ledeCode, context);
  context.renderLede(totalsIn, null);
  return elements['lede-text'].innerHTML.replace(/<[^>]+>/g, '');
}
const base = { market_value: 1125, open_cost_basis: 1000, unrealized_pl: 125 };
let sentence = lede('1w', { ...base, return_pct: 0.5, return_basis: 'time_weighted' });
assert.match(sentence, /^Over the last week, investments gained 0\.50% time-weighted\./);
assert.match(sentence, /cost €1,000 and carry an unrealized gain of €125 since purchase\.$/);
sentence = lede('1w', { ...base, return_pct: 12.5, return_basis: 'since_start' });
assert.match(sentence, /^Since the first trade, investments gained 12\.50% on net contributions\./);

console.log('Window contributions, Total-mode contributions and return labels passed.');
