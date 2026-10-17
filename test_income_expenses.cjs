const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync(`${__dirname}/static/app.js`, 'utf8');
const start = source.indexOf('    function expenseKind(');
const end = source.indexOf('    window.toggleCategorySubcategories', start);
assert(start >= 0 && end > start);
const nodes = new Map();
const context = {
  window: {}, Date, console,
  document: { getElementById: id => {
    if (!nodes.has(id)) nodes.set(id, { innerHTML: '', textContent: '', setAttribute() {} });
    return nodes.get(id);
  } },
  periodStartDate: () => new Date('2026-02-01'),
  selectedWindowLabel: () => 'February onwards',
  money: n => Number(n).toFixed(2),
  percent: n => `${n}%`,
  signedClass: n => n < 0 ? 'negative' : 'positive',
  escapeHtml: s => String(s).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;'),
  smartTickFormat: n => String(n),
  selectedExpenseTrendMode: 'monthly',
};
vm.createContext(context);
vm.runInContext(source.slice(start, end), context);
const row = (flow_kind, amount_eur, extra = {}) => ({
  date: '2026-02-10', source: 'bank', merchant: 'Example', flow_kind,
  category: flow_kind === 'spend' ? 'Groceries' : flow_kind,
  amount_eur, ...extra,
});
const data = { expenses: { status: 'available', rows: [
  row('income', 1000, { merchant: '<Employer>' }),
  row('spend', 250), row('investment', 500), row('personal_transfer', 200), row('credit', 50),
  row('income', 9999, { date: '2026-01-01' }),
] } };
const filtered = context.periodExpenses(data);
assert.equal(filtered.income, 1000);
assert.equal(filtered.spend, 250);
assert.equal(filtered.balance, 750);
assert.equal(filtered.incomeRows.length, 1);
assert.equal(filtered.categories.length, 1);
assert.equal(filtered.categories[0].share, 100);
assert.equal(filtered.merchants[0].amount, 250);
assert.equal(filtered.months[0].outflow, 250);
assert.equal(filtered.months[0].net, -750);
context.renderExpenses(data);
assert(nodes.get('income-rows').innerHTML.includes('&lt;Employer&gt;'));
assert(!nodes.get('income-rows').innerHTML.includes('9999'));
assert(nodes.get('expense-metrics').innerHTML.includes('750.00'));
assert(nodes.get('expense-trend').innerHTML.includes('expenses 250.00 | balance 750.00'));
context.selectedExpenseTrendMode = 'cumulative';
context.renderExpenses(data);
assert(nodes.get('expense-trend').innerHTML.includes('cumulative balance: 750.00'));
const negative = context.summarizeExpenseRows([row('income', 10), row('spend', 20)]);
assert.equal(negative.balance, -10);
context.renderExpenseTrend(negative.months);
assert(nodes.get('expense-trend').innerHTML.includes('cumulative balance: -10.00'));
assert(!nodes.get('expense-trend').innerHTML.includes('NaN'));
context.renderExpenses({ expenses: { status: 'available', rows: [row('income', 100)] } });
assert(nodes.get('income-rows').innerHTML.includes('100.00'));
context.renderExpenses({ expenses: { status: 'empty', rows: [] } });
assert(nodes.get('income-rows').innerHTML.includes('No income transactions'));
assert(!nodes.get('income-rows').innerHTML.includes('100.00'));
console.log('Income/expense filtering, balance, separation, rendering, and charts passed.');
