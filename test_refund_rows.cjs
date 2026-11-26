const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

// A refund (a merchant's money back, the family account paying back) is money in
// that lowers spending: shown positive, summed as negative spending. Synthetic rows.
const source = fs.readFileSync(`${__dirname}/static/app.js`, 'utf8');
const start = source.indexOf('    function expenseKind(');
const end = source.indexOf('    // Card statements spell one shop many ways', start);
assert(start >= 0 && end > start);
const context = {};
vm.createContext(context);
vm.runInContext(source.slice(start, end), context);
const row = (flow_kind, amount_eur, native_amount, category = 'Family account') => ({ flow_kind, amount_eur, native_amount, category });
assert.equal(context.expenseSignedAmount(row('refund', 30, 30)), 30);
assert.equal(context.expenseSignedAmount(row('spend', 100, -100)), -100);
assert.equal(context.expenseSignedAmount(row('credit', 12, 12, 'Money received')), 12);
const options = fs.readFileSync(`${__dirname}/static/personal-ledger.js`, 'utf8');
assert(options.includes('["refund","Refund of an expense"]'));
console.log('Refund rows passed.');
