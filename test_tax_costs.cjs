// Taxes & costs in the browser (static/app.js): withheld vs estimated, after-tax value.
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
  grab('    function periodStartDate(', '    function renderFrictions('),
].join('\n');

function frictions(mode, data) {
  const context = { selectedPeriod: 'all', selectedReturnMode: mode, customPeriodStart: () => '2026-01-01' };
  vm.createContext(context);
  vm.runInContext(code, context);
  return context.periodFrictions(data);
}

const data = {
  date_range: { end: '2026-11-24' },
  totals: { market_value: 10000, total_market_value: 10500 },
  valuation_series: [],
  series: [],
  frictions: {
    status: 'available',
    estimated_exit_tax_eur: 286,
    rows: [
      { date: '2026-03-02', broker: 'Fineco', type: 'tax', estimated: true, amount_eur: 130 },
      { date: '2026-03-02', broker: 'Fineco', type: 'dividend_tax', estimated: true, amount_eur: 26 },
      { date: '2026-03-02', broker: 'Trade Republic', type: 'tax', estimated: false, amount_eur: 50 },
      { date: '2026-03-09', broker: 'Trade Republic', type: 'tax', estimated: false, amount_eur: -4 },
      { date: '2026-03-02', broker: 'Trade Republic', type: 'cost', estimated: false, amount_eur: 5 },
    ],
  },
};

let result = frictions('price', data);
assert.equal(result.total_taxes_eur, 202);
assert.equal(result.estimated_taxes_eur, 156);
assert.equal(result.withheld_taxes_eur, 46);
assert.equal(result.total_drag_eur, 207);
// After-tax value: market value minus the estimated tax on open gains, not minus past fees.
assert.equal(result.net_liquidation_eur, 9714);

// Total mode uses the same definition on the total value.
result = frictions('total', data);
assert.equal(result.net_liquidation_eur, 10214);

console.log('Taxes & costs split and after-tax value passed.');
