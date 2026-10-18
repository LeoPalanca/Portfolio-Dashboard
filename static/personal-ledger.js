(() => {
  const node = id => document.getElementById(id);
  const escape = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"}[c]));
  let owner, data = {}, onChange, sequence = 0;
  const amount = value => new Intl.NumberFormat(undefined, {style:"currency", currency:"EUR"}).format(value);
  const options = selected => (data.categories || []).map(category => `<option ${category === selected ? "selected" : ""}>${escape(category)}</option>`).join("");
  function dialog(title, content) {
    node("personal-ledger-title").textContent = title;
    node("personal-ledger-editor").innerHTML = content;
    node("personal-ledger-error").textContent = "";
    node("personal-ledger-dialog").showModal();
  }
  function renderCash() {
    const cash = data.cash_ledger || {};
    node("cash-ledger-balance").textContent = cash.balance == null ? "Set an opening balance to track cash" : `Cash balance: ${amount(cash.balance)} · Opening: ${amount(cash.opening_balance)}`;
    node("cash-ledger-rows").innerHTML = (data.cash_rows || []).slice().reverse().map(row => `<tr>
      <td>${escape(row.date)}</td><td>${escape(row.merchant)}</td><td>${escape(row.category)}</td>
      <td>${amount(row.native_amount)}</td><td><button type="button" data-cash-edit="${escape(row.cash_id)}">Edit</button> <button type="button" data-cash-delete="${escape(row.cash_id)}">Delete</button></td></tr>`).join("") || '<tr><td colspan="5">No manual cash entries yet</td></tr>';
  }
  async function write(payload) {
    const savedOwner = owner;
    const res = await fetch("/api/expenses", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({...payload, portfolio_id:savedOwner})});
    const result = await res.json();
    if (!res.ok) throw Error(result.error || "Could not save ledger change");
    if (owner !== savedOwner) return;
    data = result; onChange(result); renderCash();
    node("personal-ledger-status").textContent = "Saved";
  }
  window.personalLedger = {
    async load(person, callback) {
      const request = ++sequence;
      if (owner !== person) {data = {}; node("personal-ledger-dialog").close();}
      owner = person; onChange = callback;
      node("personal-ledger-status").textContent = "Loading ledger…";
      try {
        const res = await fetch(`/api/expenses?person=${encodeURIComponent(person)}`);
        const result = await res.json();
        if (request !== sequence) return;
        if (!res.ok) throw Error(result.error || "Could not load cash ledger");
        data = result; callback(result); renderCash();
        node("personal-ledger-status").textContent = "";
      } catch (error) {
        if (request === sequence) node("personal-ledger-status").textContent = error.message;
      }
    }
  };
  window.openCashEntry = (id = null) => {
    if (!data.categories) return;
    const row = (data.cash_rows || []).find(item => item.cash_id === id) || {};
    const today = new Date();
    const localDate = `${today.getFullYear()}-${String(today.getMonth()+1).padStart(2,"0")}-${String(today.getDate()).padStart(2,"0")}`;
    dialog(id ? "Edit cash entry" : "Add cash entry", `<form id="cash-entry-form" class="personal-ledger-form">
      <label>Date<input name="date" type="date" required max="${localDate}" value="${escape(row.date || localDate)}"></label>
      <label>Direction<select name="flow_kind"><option value="spend">Expense</option><option value="income" ${row.flow_kind === "income" ? "selected" : ""}>Income</option><option value="transfer_in" ${row.cash_direction === "transfer_in" ? "selected" : ""}>Cash transfer in (not income)</option><option value="transfer_out" ${row.cash_direction === "transfer_out" ? "selected" : ""}>Cash transfer out (not expense)</option></select></label>
      <label>Amount EUR<input name="amount" type="number" min="0.01" step="0.01" required value="${escape(row.amount_eur || "")}"></label>
      <label>Merchant / payee<input name="merchant" required maxlength="500" value="${escape(row.merchant)}"></label>
      <label>Category<select name="category">${options(row.category || "Uncategorized")}</select></label>
      <label>Subcategory<input name="subcategory" maxlength="500" value="${escape(row.subcategory)}"></label>
      <label class="personal-ledger-wide">Description<input name="description" maxlength="500" value="${escape(row.description)}"></label>
      <button type="submit">Save cash entry</button></form>`);
    node("cash-entry-form").onsubmit = async event => {
      event.preventDefault(); const button = event.submitter || event.target.querySelector('[type="submit"]'); button.disabled = true;
      try {await write({...Object.fromEntries(new FormData(event.target)), action:"save_cash", id}); node("personal-ledger-dialog").close();}
      catch (error) {node("personal-ledger-error").textContent = error.message;}
      finally {button.disabled = false;}
    };
  };
  window.openCashOpeningBalance = () => {
    if (!data.categories) return;
    dialog("Cash opening balance", `<p class="subtle">Cash held before the first manual entry. This is not income.</p><form id="cash-opening-form" class="personal-ledger-form"><label>Opening EUR<input name="amount" type="number" min="0" max="1000000000" step="0.01" required value="${escape(data.cash_ledger?.opening_balance ?? "")}"></label><button type="submit">Save opening balance</button></form>`);
    node("cash-opening-form").onsubmit = async event => {
      event.preventDefault(); const button = event.submitter || event.target.querySelector('[type="submit"]'); button.disabled = true;
      try {await write({action:"opening_balance", amount:new FormData(event.target).get("amount")}); node("personal-ledger-dialog").close();}
      catch (error) {node("personal-ledger-error").textContent = error.message;}
      finally {button.disabled = false;}
    };
  };
  function openCategory(id) {
    const row = (data.rows || []).find(item => item.movement_id === id);
    if (!row) return;
    dialog("Set transaction category", `<p>${escape(row.merchant)} · ${escape(row.source_label)} · ${escape(row.date)}</p>
      <form id="category-entry-form" class="personal-ledger-form">
      <label>Category<select name="category">${options(row.category)}</select></label>
      <label>Subcategory<input name="subcategory" maxlength="500" value="${escape(row.subcategory)}"></label>
      <label class="personal-ledger-wide personal-ledger-check"><input name="learn" type="checkbox" checked>Use for the same merchant, source and direction</label>
      <label class="personal-ledger-wide personal-ledger-check"><input name="include_past" type="checkbox" checked>Also apply to matching past transactions (individual overrides stay unchanged)</label>
      <p class="subtle personal-ledger-wide">Direction stays unchanged: a category edit cannot turn an expense into income.</p>
      <button type="submit">Save category</button></form>`);
    node("category-entry-form").onsubmit = async event => {
      event.preventDefault(); const button = event.submitter || event.target.querySelector('[type="submit"]'); button.disabled = true;
      const form = new FormData(event.target);
      try {await write({action:"category", movement_id:id, category:form.get("category"), subcategory:form.get("subcategory"), learn:form.has("learn"), include_past:form.has("include_past")}); node("personal-ledger-dialog").close();}
      catch (error) {node("personal-ledger-error").textContent = error.message;}
      finally {button.disabled = false;}
    };
  }
  window.openCategoryRules = () => {
    dialog("Category rules", `<p class="subtle">Rules match exact merchant names after ignoring capitalization and repeated spaces, within the same source and direction. Individual transaction overrides take priority. Removing a rule restores imported categories except individual overrides.</p>
      <div class="table-wrap"><table><thead><tr><th>Source / direction</th><th>Merchant</th><th>Category</th><th>Scope</th><th></th></tr></thead><tbody>${(data.rules || []).map((rule, index) => `<tr><td>${escape(rule.source)} / ${escape(rule.flow_kind)}</td><td>${escape(rule.merchant)}</td><td>${escape(rule.category)}${rule.subcategory ? ` / ${escape(rule.subcategory)}` : ""}</td><td>${rule.after_id ? "Future imports" : "Past and future"}</td><td><button type="button" data-rule-delete="${index}">Remove</button></td></tr>`).join("") || '<tr><td colspan="5">No learned rules yet</td></tr>'}</tbody></table></div>`);
  };
  document.addEventListener("click", async event => {
    const button = event.target.closest("button");
    if (!button) return;
    if (button.dataset.categoryEdit) return openCategory(Number(button.dataset.categoryEdit));
    if (button.dataset.cashEdit) return window.openCashEntry(button.dataset.cashEdit);
    try {
      if (button.dataset.cashDelete && confirm("Delete this manual cash entry?")) {
        button.disabled = true; await write({action:"delete_cash", id:button.dataset.cashDelete});
      }
      if (button.dataset.ruleDelete !== undefined && confirm("Remove this category rule?")) {
        button.disabled = true; const rule = data.rules[Number(button.dataset.ruleDelete)];
        await write({action:"delete_rule", ...rule}); window.openCategoryRules();
      }
    } catch (error) {
      node("personal-ledger-status").textContent = error.message;
      node("personal-ledger-error").textContent = error.message;
    } finally {button.disabled = false;}
  });
})();
