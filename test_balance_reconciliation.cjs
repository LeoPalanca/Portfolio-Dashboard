const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

// Calculated rows, top-ups from own accounts and the reconciliation tables, as the
// Income & expenses section renders them.
const source = fs.readFileSync(`${__dirname}/static/app.js`, 'utf8');
const start = source.indexOf('    function expenseKind(');
const end = source.indexOf('    window.toggleCategorySubcategories', start);
assert(start >= 0 && end > start);
const nodes = new Map();
const context = {
  window: {}, Date, console, includeGiroconti: false,
  document: { getElementById: id => {
    if (!nodes.has(id)) nodes.set(id, { innerHTML: '', textContent: '', hidden: false, setAttribute() {} });
    return nodes.get(id);
  } },
  periodStartDate: () => new Date('2026-02-01'),
  selectedWindowLabel: () => 'February onwards',
  money: n => Number(n).toFixed(2),
  percent: n => `${n}%`,
  signedClass: n => n < 0 ? 'negative' : 'positive',
  escapeHtml: s => String(s ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;'),
  jsArg: s => JSON.stringify(String(s ?? '')),
  smartTickFormat: n => String(n),
  selectedExpenseTrendMode: 'monthly',
};
vm.createContext(context);
vm.runInContext(source.slice(start, end), context);
const row = (flow_kind, amount_eur, extra = {}) => ({
  date: '2026-02-10', source: 'bank', merchant: 'Example', flow_kind, category: 'Groceries', amount_eur, ...extra,
});
const rows = [
  row('income', 1000), row('spend', 250),
  row('calculated_expense', 40, { category: 'Calculated expenses', calculated: true }),
  row('calculated_income', 15, { category: 'Calculated income', calculated: true }),
  row('top_up', 300, { source: 'Card' }),
  row('top_up', 120, { source: 'Card', internal: true }),
  row('personal_transfer', 120, { internal: true }),
];

assert.equal(context.expenseKind(rows[2]), 'spend');
assert.equal(context.expenseKind(rows[3]), 'income');
const summary = context.summarizeExpenseRows(rows);
assert.equal(summary.spend, 290);
assert.equal(summary.income, 1015);
assert.equal(summary.calculatedExpenses, 40);
assert.equal(summary.calculatedIncome, 15);
// Matched giroconti stay hidden, yet the money from own accounts counts every top-up.
assert.equal(summary.topups, 300);
assert.equal(summary.topupsAll, 420);
assert.equal(summary.unmatchedTopups, 300);
assert.equal(summary.categories.map(item => item.category).join('|'), 'Groceries|Calculated expenses');
context.includeGiroconti = true;
assert.equal(context.summarizeExpenseRows(rows).unmatchedTopups, 300);
context.includeGiroconti = false;

context.renderExpenses({ expenses: { status: 'available', rows, reconciliation: {
  accounts: [
    { account: 'Bank', message: 'Reconciled to 2026-02-28', latest_balance_eur: 900, latest_balance_date: '2026-02-28',
      manual_balances: [{ id: 'm1', date: '2026-02-28', balance_eur: 900 }] },
    { account: 'Card', message: 'No balance yet — enter the current balance to reconcile', latest_balance_eur: null, manual_balances: [] },
  ],
  intervals: [
    { account: 'Bank', start: '2026-01-31', end: '2026-02-28', opening_eur: 100, closing_eur: 900, recorded_eur: 840, movements: 0, gap_eur: -40, calculated: 'expense', missing: [] },
    { account: 'Bank', start: '2026-02-28', end: '2026-06-30', opening_eur: 900, closing_eur: 950, recorded_eur: 0, movements: 0, gap_eur: 50, calculated: null,
      missing: [{ from: '2026-03-01', to: '2026-05-31' }, { from: '2026-06-30', to: '2026-06-30' }] },
  ],
} } });
const metrics = nodes.get('expense-metrics').innerHTML;
assert(metrics.includes('Money in from your other accounts') && metrics.includes('420.00'));
assert(metrics.includes('Income − expenses (imported accounts)'));
assert.equal(nodes.get('expense-topup-note').textContent, '300.00 came in from accounts that are not imported, so the income that funded it is not counted.');
assert.equal(nodes.get('expense-topup-note').hidden, false);
const accounts = nodes.get('reconciliation-accounts').innerHTML;
assert(accounts.includes('data-balance-edit="m1"') && accounts.includes('data-balance-account="Card"'));
assert(accounts.includes('No balance yet'));
const intervals = nodes.get('reconciliation-intervals').innerHTML;
assert(intervals.includes('Calculated expenses') && intervals.includes('none imported') && intervals.includes('-40.00'));
// A period imported statements do not cover lists its gaps instead of a calculated row.
assert(intervals.includes('Missing statements: 2026-03-01 → 2026-05-31, 2026-06-30'));
assert(!intervals.includes('Calculated income'));
assert(accounts.includes('data-balance-date="2026-02-28"'));

context.renderExpenses({ expenses: { status: 'available', rows: [row('income', 10)] } });
assert.equal(nodes.get('expense-topup-note').hidden, true);
assert(nodes.get('reconciliation-intervals').innerHTML.includes('Two balances'));
console.log('Calculated rows, own-account top-ups and the reconciliation tables passed.');
