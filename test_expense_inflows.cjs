const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

// Money back from an investment and money received (credits), as the Income &
// expenses section sums and shows them. Synthetic rows only.
const source = fs.readFileSync(`${__dirname}/static/app.js`, 'utf8');
const start = source.indexOf('    function expenseKind(');
const end = source.indexOf('    window.toggleCategorySubcategories', start);
assert(start >= 0 && end > start);
const nodes = new Map();
const context = {
  window: {}, Date, console, Intl, includeGiroconti: false,
  document: { getElementById: id => {
    if (!nodes.has(id)) nodes.set(id, { innerHTML: '', textContent: '', hidden: false, setAttribute() {} });
    return nodes.get(id);
  } },
  periodStartDate: () => new Date('2026-02-01'),
  selectedWindowLabel: () => 'February onwards',
  money: n => Number(n).toFixed(2),
  percent: n => `${n}%`,
  signedClass: n => n < 0 ? 'negative' : 'positive',
  escapeHtml: s => String(s ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;'),
  jsArg: s => JSON.stringify(String(s ?? '')),
  smartTickFormat: n => String(n),
  selectedExpenseTrendMode: 'monthly',
};
vm.createContext(context);
vm.runInContext(source.slice(start, end), context);
const row = (flow_kind, amount_eur, native_amount, extra = {}) => ({
  date: '2026-02-10', source: 'bank', merchant: 'Example', flow_kind, category: 'Example', amount_eur, native_amount, ...extra,
});
const rows = [
  row('income', 1000, 1000), row('spend', 400, -400), row('credit', 150, 150),
  row('investment', 200, -200), row('investment', 500, 500),
];
const summary = context.summarizeExpenseRows(rows);
assert.equal(summary.investments, -300);
assert.equal(summary.income, 1000);
assert.equal(summary.spend, 400);
assert.equal(summary.balance, 600);
assert.equal(summary.balanceWithCredits, 750);
assert.equal(context.expenseSignedAmount(rows[4]), 500);
assert.equal(context.expenseSignedAmount(rows[3]), -200);
assert.equal(context.expenseSignedAmount(rows[2]), 150);
context.renderExpenses({ expenses: { status: 'available', rows } });
const metrics = nodes.get('expense-metrics').innerHTML;
assert(metrics.includes('Income + money received − expenses'));
assert(metrics.includes('750.00'));
// A foreign sub-account's reconciliation is shown in its own currency.
context.renderReconciliation({
  accounts: [{ account: 'Revolut · Example (CHF)', currency: 'CHF', message: 'Reconciled', latest_balance_eur: 14, latest_balance_date: '2026-03-07' }],
  intervals: [{ account: 'Revolut · Example (CHF)', currency: 'CHF', start: '2026-03-05', end: '2026-03-07', opening_eur: 0, closing_eur: 14, recorded_eur: 14, movements: 2, gap_eur: 0, missing: [] }],
});
assert(nodes.get('reconciliation-accounts').innerHTML.includes('CHF'));
assert(nodes.get('reconciliation-intervals').innerHTML.includes('CHF'));
console.log('Investment inflows, money received and foreign-currency reconciliation passed.');
