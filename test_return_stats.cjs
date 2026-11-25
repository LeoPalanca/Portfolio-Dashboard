// Risk statistics and daily-return histograms computed in the browser (static/app.js).
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
  grab('    function dailyReturnSummary(', '    function statsForSelectedWindow('),
  grab('    function quantile(', '    function distributionMeta('),
  grab('    function returnDistributionDomain(', '    function renderHistogramSvg('),
].join('\n');
const context = { ANNUAL_RISK_FREE_RATE: 0.0252, MIN_ANNUALISED_DAYS: 60, XEON_RISK_FREE_COVERAGE: 0.8 };
vm.createContext(context);
vm.runInContext(code, context);
const close = (actual, expected, message) => assert(Math.abs(actual - expected) < 1e-9, `${message}: ${actual} != ${expected}`);
const mean = values => values.reduce((sum, value) => sum + value, 0) / values.length;
const sampleStd = values => {
  const avg = mean(values);
  return Math.sqrt(values.reduce((sum, value) => sum + (value - avg) ** 2, 0) / (values.length - 1));
};

// Sample (n-1) variance: [1%, -1%, 2%, 0%] has mean 0.5% and variance 0.0005 / 3.
let summary = context.dailyReturnSummary([0.01, -0.01, 0.02, 0]);
close(summary.daily_variance_pct, 0.0005 / 3 * 10000, 'sample variance');
close(summary.daily_volatility_pct, Math.sqrt(0.0005 / 3) * 100, 'sample volatility');

// A calm week: daily figures stay, annualised ones need 60 returns.
const week = [0.003, 0.001, 0.002, 0.0025, 0.0015];
summary = context.dailyReturnSummary(week, week.map(value => value - 0.0001));
assert.equal(summary.sample_too_small, true);
assert.equal(summary.annualized_volatility_pct, null);
assert.equal(summary.sharpe_ratio, null);
close(summary.mean_daily_return_pct, 0.2, 'mean of a short window');
close(summary.best_daily_return_pct, 0.3, 'best day');
close(summary.worst_daily_return_pct, 0.1, 'worst day');

// Sharpe: excess over XEON on the same rows; XEON itself has none.
const xeon = Array.from({ length: 80 }, (_, i) => 0.0001 + 0.00002 * ((i % 5) - 2));
const portfolio = Array.from({ length: 80 }, (_, i) => 0.001 * (i % 2 ? 1 : -0.5));
const rows = portfolio.map((value, i) => ({ total_return: value, msci_return: value, xeon_return: xeon[i] }));
let stats = context.calculateReturnStats(rows, 'total_return');
const excess = portfolio.map((value, i) => value - xeon[i]);
assert.equal(stats.risk_free.source, 'xeon');
close(stats.portfolio.sharpe_ratio, mean(excess) / sampleStd(excess) * Math.sqrt(252), 'XEON excess Sharpe');
assert.equal(stats.xeon.sharpe_ratio, null);
assert.notEqual(stats.xeon.annualized_volatility_pct, null);

// Without XEON quotes the configured rate stands in (2.52% a year = 0.01% a day).
stats = context.calculateReturnStats(portfolio.map(value => ({ total_return: value, xeon_return: null })), 'total_return');
assert.equal(stats.risk_free.source, 'fixed');
const fixedExcess = portfolio.map(value => value - 0.0001);
close(stats.portfolio.sharpe_ratio, mean(fixedExcess) / sampleStd(fixedExcess) * Math.sqrt(252), 'fixed-rate Sharpe');

// No MSCI rows in the window: no MSCI figures rather than zeros.
assert.equal(stats.msci.mean_daily_return_pct, null);

// Histogram: one crash day does not set the scale, it lands in the overflow bin.
const calm = Array.from({ length: 200 }, (_, i) => ((i % 21) - 10) / 1000);  // within +-1%
const domain = context.returnDistributionDomain([...calm, -0.12], calm);
assert(domain.max < 2 && domain.min === -domain.max, `robust range: ${JSON.stringify(domain)}`);
const histogram = context.histogramForReturns([...calm, -0.12], domain, 18);
assert.equal(histogram.counts.length, 20);
assert.equal(histogram.counts[0], 1, 'crash day in the low overflow bin');
assert.equal(histogram.counts[19], 0);
close(histogram.shares.reduce((sum, share) => sum + share, 0), 100, 'shares add up to 100%');

// Shares, not counts: half as many days with the same shape draws the same bars.
const fewer = context.histogramForReturns(calm.filter((_, i) => i % 2 === 0), domain, 18);
const more = context.histogramForReturns(calm, domain, 18);
assert(Math.max(...fewer.shares.map((share, i) => Math.abs(share - more.shares[i]))) < 1.5, 'similar shares');
assert.equal(context.histogramScaleMax(fewer, more) % 5, 0);

console.log('Return statistics, XEON Sharpe, small samples and histogram scaling passed.');
