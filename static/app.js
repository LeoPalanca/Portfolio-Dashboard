    /* ─── Info Modals & Popups ─── */
    window.showAssetInfoPopup = function(type, event) {
      if (event) {
        event.preventDefault();
        event.stopPropagation();
      }
      if (type === 'europension') {
        const title = "Mediolanum Europension TaxBenefit Previdenza";
        const content = `
          <p class="mb-3"><strong>What it is:</strong> A private individual pension plan (<em>PIP - Piano Individuale Pensionistico</em>) offered by Banca Mediolanum.</p>
          <p class="mb-3"><strong>Tax Advantage:</strong> Annual contributions are fully deductible from taxable income up to a maximum of <strong>€5.164,57</strong>. At a 43% marginal tax bracket, this yields an immediate <strong>+75.4% return</strong> (saving €2.220 in taxes on a €2.943 net outlay).</p>
          <div style="background: color-mix(in srgb, var(--warning) 8%, transparent); border-left: 3px solid var(--warning); padding: 12px; margin-bottom: 16px; border-radius: 4px; font-size: 13px; color: var(--text-secondary);">
            <strong class="c-warning">Management Fee Drag Compounding Impact:</strong>
            <p class="stack-tight">Traditional PIPs have an annual management cost (ISC) of <strong>~2.0%</strong>. A low-cost alternative Open Pension Fund (FPA) like <em>Amundi SecondaPensione</em> has a fee of only <strong>~0.8%</strong>.</p>
            <p class="stack-tight">Over a 15-year period on €5.164 annual contributions:</p>
            <ul style="margin: 6px 0 0 16px; padding: 0;">
              <li><strong>Standard FPA (~0.8% fee)</strong>: yields <strong>~€120.000</strong> net payout</li>
              <li><strong>Traditional PIP (~2.0% fee)</strong>: yields <strong>~€108.000</strong> net payout</li>
            </ul>
            <p style="margin-top: 6px; margin-bottom: 0; font-weight: 500; color: var(--text-primary);">Transferring this policy to a low-cost FPA saves ~€12.000 in lost fees while fully preserving the tax deduction!</p>
          </div>
        `;
        showInfoModal(title, content);
      } else if (type === 'mystyle') {
        const title = "Managed Product Fee Analysis";
        const content = `
          <p class="mb-3"><strong>What it is:</strong> A multi-fund insurance wrapper can combine product-level charges with the costs of its underlying funds.</p>
          <p class="mb-3"><strong>Why compare fees:</strong> Small annual cost differences compound over long holding periods. Use the calculator with the fees and capital from your own documents.</p>
          <div style="background: color-mix(in srgb, var(--negative) 8%, transparent); border-left: 3px solid var(--negative); padding: 12px; margin-bottom: 16px; border-radius: 4px; font-size: 13px; color: var(--text-secondary);">
            <strong class="c-negative">Illustrative comparison only</strong>
            <p class="stack-tight">The calculator does not include taxes, trading costs, guarantees, insurance benefits, or changes in future returns. It is not investment advice.</p>
          </div>
          <p class="mb-0">Actual statement charges belong in the private portfolio configuration and appear in the dashboard's Frictions section.</p>
        `;
        showInfoModal(title, content);
      }
    };
    
    window.showInfoModal = function(title, html) {
      const modal = document.getElementById("info-modal");
      document.getElementById("modal-title").innerHTML = title;
      document.getElementById("modal-content").innerHTML = html;
      modal.style.display = "flex";
      // Force reflow
      modal.offsetHeight;
      modal.style.opacity = "1";
    };
    
    window.closeInfoModal = function() {
      const modal = document.getElementById("info-modal");
      modal.style.opacity = "0";
      modal.addEventListener("transitionend", function handler() {
        if (modal.style.opacity === "0") {
          modal.style.display = "none";
        }
        modal.removeEventListener("transitionend", handler);
      }, { once: true });
    };

    /* ─── Collapsible section toggle ─── */
    function toggleSection(header) {
      const targetId = header.dataset.collapse;
      const content = document.getElementById(targetId);
      if (!content) return;
      const isExpanded = content.classList.contains('expanded');
      if (isExpanded) {
        content.style.maxHeight = content.scrollHeight + 'px';
        requestAnimationFrame(() => {
          content.style.maxHeight = '0';
          content.classList.remove('expanded');
        });
        header.classList.remove('expanded');
      } else {
        content.classList.add('expanded');
        content.style.maxHeight = content.scrollHeight + 'px';
        header.classList.add('expanded');
        content.addEventListener('transitionend', function handler() {
          content.style.maxHeight = '';
          content.removeEventListener('transitionend', handler);
          scheduleChartResize();
        });
        requestAnimationFrame(scheduleChartResize);
      }
    }
    function sectionIconSvg(name) {
      const icons = {
        value: `<svg viewBox="0 0 24 24"><path d="M4 18V6"/><path d="M4 16l5-5 4 3 7-8"/><path d="M15 6h5v5"/></svg>`,
        flow: `<svg viewBox="0 0 24 24"><path d="M4 7h11a4 4 0 0 1 0 8H8"/><path d="M8 11l-4 4 4 4"/><path d="M17 4l3 3-3 3"/></svg>`,
        holdings: `<svg viewBox="0 0 24 24"><path d="M5 7h14"/><path d="M5 12h14"/><path d="M5 17h14"/><path d="M9 7v10"/></svg>`,
        calculator: `<svg viewBox="0 0 24 24"><rect x="5" y="3" width="14" height="18" rx="2"/><path d="M8 7h8"/><path d="M8 11h2"/><path d="M14 11h2"/><path d="M8 15h2"/><path d="M14 15h2"/></svg>`,
        layers: `<svg viewBox="0 0 24 24"><path d="M12 3l8 4-8 4-8-4 8-4Z"/><path d="M4 12l8 4 8-4"/><path d="M4 17l8 4 8-4"/></svg>`,
        watch: `<svg viewBox="0 0 24 24"><path d="M12 5l2.2 4.5 5 .7-3.6 3.5.8 5-4.4-2.3-4.4 2.3.8-5-3.6-3.5 5-.7L12 5Z"/></svg>`,
        news: `<svg viewBox="0 0 24 24"><path d="M4 6h14v12H4z"/><path d="M18 9h2v9a2 2 0 0 1-2 2"/><path d="M7 9h8"/><path d="M7 13h8"/><path d="M7 17h5"/></svg>`,
        distribution: `<svg viewBox="0 0 24 24"><path d="M12 3v18"/><path d="M12 12l8-5"/><path d="M12 12l8 5"/><circle cx="12" cy="12" r="2"/><circle cx="20" cy="7" r="2"/><circle cx="20" cy="17" r="2"/><circle cx="4" cy="12" r="2"/></svg>`,
        income: `<svg viewBox="0 0 24 24"><path d="M12 3v18"/><path d="M16 7.5a4 4 0 0 0-4-2c-2 0-3.5 1-3.5 2.6 0 3.8 7 1.8 7 5.8 0 1.8-1.6 3.1-3.8 3.1a5.2 5.2 0 0 1-4.2-2"/></svg>`,
        cash: `<svg viewBox="0 0 24 24"><rect x="4" y="7" width="16" height="10" rx="2"/><circle cx="12" cy="12" r="2"/><path d="M7 10v4"/><path d="M17 10v4"/></svg>`,
        contribution: `<svg viewBox="0 0 24 24"><path d="M12 4v16"/><path d="M8 8l4-4 4 4"/><path d="M4 16h16"/></svg>`,
        risk: `<svg viewBox="0 0 24 24"><path d="M12 3l9 16H3L12 3Z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>`,
        stats: `<svg viewBox="0 0 24 24"><path d="M5 19V5"/><path d="M5 19h14"/><path d="M8 16v-4"/><path d="M12 16V8"/><path d="M16 16v-6"/></svg>`,
        coverage: `<svg viewBox="0 0 24 24"><path d="M12 3l7 3v5c0 4.5-2.8 8-7 10-4.2-2-7-5.5-7-10V6l7-3Z"/><path d="M8.5 12l2.2 2.2L15.8 9"/></svg>`,
        todo: `<svg viewBox="0 0 24 24"><path d="M5 6h14"/><path d="M5 12h14"/><path d="M5 18h9"/><path d="M16 17l2 2 4-4"/></svg>`,
        panel: `<svg viewBox="0 0 24 24"><rect x="4" y="5" width="16" height="14" rx="2"/><path d="M4 10h16"/></svg>`
      };
      return icons[name] || icons.panel;
    }
    function initializeSectionIdentity() {
      const accents = {
        blue: ["var(--accent)", "color-mix(in srgb, var(--accent) 9%, transparent)"],
        teal: ["var(--series-teal)", "color-mix(in srgb, var(--series-teal) 8%, transparent)"],
        green: ["var(--positive)", "color-mix(in srgb, var(--positive) 8%, transparent)"],
        amber: ["var(--warning)", "color-mix(in srgb, var(--warning) 8%, transparent)"],
        violet: ["var(--series-violet)", "color-mix(in srgb, var(--series-violet) 8%, transparent)"],
        red: ["var(--negative)", "color-mix(in srgb, var(--negative) 7%, transparent)"],
        slate: ["var(--text-muted)", "color-mix(in srgb, var(--text-muted) 6%, transparent)"]
      };
      const config = {
        "Portfolio Value": { tier: "primary", accent: "blue", icon: "value" },
        "Cash Flow Evolution": { tier: "core", accent: "teal", icon: "flow" },
        "Current Holdings": { tier: "core", accent: "green", icon: "holdings" },
        "MyStyle Fee Drag Calculator": { tier: "risk", accent: "amber", icon: "calculator" },
        "MyStyle Portfolio Breakdown": { tier: "risk", accent: "amber", icon: "layers" },
        "Watchlist": { tier: "support", accent: "violet", icon: "watch" },
        "Stock News": { tier: "support", accent: "slate", icon: "news" },
        "Portfolio Distribution": { tier: "core", accent: "violet", icon: "distribution" },
        "Dividends": { tier: "support", accent: "green", icon: "income" },
        "Cash Account Interest": { tier: "support", accent: "teal", icon: "cash" },
        "Net Contributions": { tier: "support", accent: "blue", icon: "contribution" },
        "Taxes & Costs": { tier: "risk", accent: "amber", icon: "risk" },
        "Portfolio Statistics": { tier: "core", accent: "blue", icon: "stats" },
        "Pricing Coverage": { tier: "system", accent: "slate", icon: "coverage" },
        "Suggested Actions & To-Dos": { tier: "risk", accent: "amber", icon: "todo" }
      };

      document.querySelectorAll(".section-head[data-collapse]").forEach(header => {
        const title = header.querySelector("h2")?.textContent?.trim() || "";
        const item = config[title] || { tier: "support", accent: "slate", icon: "panel" };
        const section = header.closest("section");
        if (!section) return;
        const [accent, accentSoft] = accents[item.accent] || accents.slate;
        section.classList.add(`section-${item.tier}`);
        section.style.setProperty("--section-accent", accent);
        section.style.setProperty("--section-accent-soft", accentSoft);

        const left = header.querySelector(".section-head-left");
        const heading = left?.querySelector("h2");
        if (!left || !heading || left.querySelector(".section-icon")) return;
        const icon = document.createElement("span");
        icon.className = "section-icon";
        icon.setAttribute("aria-hidden", "true");
        icon.innerHTML = sectionIconSvg(item.icon);
        left.insertBefore(icon, heading);
      });
    }
    function initializeSectionWrapButtons() {
      document.querySelectorAll(".section-content[id]").forEach(content => {
        if (content.querySelector(".section-wrap-up")) return;
        const header = [...document.querySelectorAll(".section-head[data-collapse]")]
          .find(item => item.dataset.collapse === content.id);
        if (!header) return;

        const sectionTitle = header.querySelector("h2")?.textContent?.trim() || "section";
        const wrap = document.createElement("div");
        wrap.className = "section-wrap-up";
        wrap.innerHTML = `
          <button type="button" class="section-wrap-button" aria-label="Collapse ${escapeHtml(sectionTitle)}">
            <span class="section-wrap-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24"><path d="M6 15l6-6 6 6"/></svg>
            </span>
            <span>Wrap up</span>
          </button>
        `;
        wrap.querySelector("button").addEventListener("click", event => {
          event.preventDefault();
          event.stopPropagation();
          if (content.classList.contains("expanded")) {
            event.currentTarget.blur();
            toggleSection(header);
          }
        });
        content.appendChild(wrap);
      });
    }
    let dashboardData = null;
    let rankingsData = null;
    let rankingsSort = { key: "common", direction: "desc" };
    let selectedExpenseTrendMode = "monthly";
    const APP_CONFIG = JSON.parse(
      document.getElementById("app-config").textContent
    );
    const PRIMARY_PORTFOLIO_ID = APP_CONFIG.primaryPortfolioId;
    const SINCE_2024_PORTFOLIO_IDS = new Set(APP_CONFIG.since2024PortfolioIds);
    const APP_VERSION = APP_CONFIG.appVersion;
    const importModal = document.getElementById("import-modal");
    const importForm = document.getElementById("import-form");
    const importFile = document.getElementById("import-file");
    const importFileName = document.getElementById("import-file-name");
    const importDropzone = document.getElementById("import-dropzone");
    const importStatus = document.getElementById("import-status");
    const importSubmit = document.getElementById("import-submit");
    let selectedPerson = PRIMARY_PORTFOLIO_ID;
    let selectedPeriod = SINCE_2024_PORTFOLIO_IDS.has(PRIMARY_PORTFOLIO_ID) ? "since24" : "all";
    let selectedBerkshireMode = "stock";
    let selectedProxyMode = "on";
    let selectedLiveMode = "all";
    let selectedReturnMode = "price";
    let chartResizeTimer = null;
    let sortState = { key: "market_value_eur", direction: "desc" };
    let variationMode = "pct";
    let selectedBroker = "all";
    let showAllHoldings = false;
    let showClosed = false;
    let activeMoversPeriod = null;
    let selectedDistributionSource = "";
    let loadRequestId = 0;
    let redrawTimer = null;

    function openImportDialog(firstRun = false) {
      document.getElementById("import-title").textContent = firstRun ? "Welcome — import your first statement" : "Import your statements";
      document.getElementById("import-intro").textContent = firstRun
        ? "Start with any supported broker or bank export. It stays on this computer and is normalized into a private SQLite ledger."
        : "Upload the platform’s native export format. Files stay on this computer and are normalized into the local SQLite movement ledger.";
      importStatus.textContent = "";
      importStatus.className = "import-status";
      importModal.classList.add("open");
      window.setTimeout(() => importFile.focus(), 80);
    }

    function closeImportDialog() {
      importModal.classList.remove("open");
    }

    function updateSelectedImportFile() {
      importFileName.textContent = importFile.files.length ? importFile.files[0].name : "No file selected";
    }

    async function checkImportOnboarding() {
      try {
        const response = await fetch("/api/imports/status");
        const status = await response.json();
        if (response.ok && !status.ready && status.imports === 0) openImportDialog(true);
      } catch (error) {
        console.warn("Import status unavailable:", error);
      }
    }

    document.getElementById("import-data").addEventListener("click", () => openImportDialog(false));
    document.getElementById("import-close").addEventListener("click", closeImportDialog);
    importModal.addEventListener("click", event => { if (event.target === importModal) closeImportDialog(); });
    importFile.addEventListener("change", updateSelectedImportFile);
    ["dragenter", "dragover"].forEach(name => importDropzone.addEventListener(name, event => {
      event.preventDefault();
      importDropzone.classList.add("dragging");
    }));
    ["dragleave", "drop"].forEach(name => importDropzone.addEventListener(name, event => {
      event.preventDefault();
      importDropzone.classList.remove("dragging");
    }));
    importDropzone.addEventListener("drop", event => {
      if (event.dataTransfer.files.length) {
        importFile.files = event.dataTransfer.files;
        updateSelectedImportFile();
      }
    });
    document.addEventListener("keydown", event => {
      if (event.key === "Escape" && importModal.classList.contains("open")) closeImportDialog();
    });
    importForm.addEventListener("submit", async event => {
      event.preventDefault();
      if (!importFile.files.length) return;
      const form = new FormData(importForm);
      importSubmit.disabled = true;
      importSubmit.textContent = "Importing…";
      importStatus.className = "import-status";
      importStatus.textContent = "Validating, archiving, and normalizing the statement…";
      try {
        const response = await fetch("/api/imports", { method: "POST", body: form });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "The statement could not be imported.");
        importStatus.className = "import-status success";
        importStatus.textContent = result.duplicate
          ? `Already imported as ${result.source_label}. No duplicate rows were added.`
          : `${result.source_label}: ${result.movements} new movement${result.movements === 1 ? "" : "s"} stored${result.duplicates ? `, ${result.duplicates} duplicate${result.duplicates === 1 ? "" : "s"} skipped` : ""}.`;
        importForm.reset();
        updateSelectedImportFile();
        window.setTimeout(() => {
          closeImportDialog();
          load(false, "Loading imported data");
        }, 900);
      } catch (error) {
        importStatus.className = "import-status error";
        importStatus.textContent = error.message;
      } finally {
        importSubmit.disabled = false;
        importSubmit.textContent = "Import statement";
      }
    });

    function setRefreshLabel(label) {
      const status = document.getElementById("refresh-status");
      if (status) status.textContent = label || "Updating dashboard";
    }
    function setDashboardBusy(isBusy, label = "Updating dashboard") {
      window.clearTimeout(redrawTimer);
      document.body.classList.remove("dashboard-redrawing");
      setRefreshLabel(label);
      document.body.classList.toggle("dashboard-refreshing", isBusy);
    }
    function withRedrawVeil(label, renderFn) {
      if (document.body.classList.contains("dashboard-refreshing")) {
        renderFn();
        return;
      }
      window.clearTimeout(redrawTimer);
      setRefreshLabel(label);
      document.body.classList.add("dashboard-redrawing");
      requestAnimationFrame(() => {
        renderFn();
        redrawTimer = window.setTimeout(() => {
          document.body.classList.remove("dashboard-redrawing");
        }, 240);
      });
    }
    function resetHoldingsView() {
      showAllHoldings = false;
      showClosed = false;
    }

    function toggleVariationMode() {
      variationMode = variationMode === "pct" ? "amount" : "pct";
      if (dashboardData) {
        renderMetrics(periodMetrics(dashboardData));
        renderMoversPanel();
      }
    }
    const cashVisibility = {
      invested: true,
      net_contributions: true,
      open_cost_basis: true,
      proceeds: true,
      realized_pl: true
    };
    const returnVisibility = {
      return_pct: true,
      msci_return_pct: false,
      xeon_return_pct: false,
      inflation_return_pct: false,
      weighted_score: false,
      freq_score: false
    };
    let showTransactions = true;
    let showAllTransactions = false;
    const returnDefs = [
      ["return_pct", "Return %", "series-return"],
      ["msci_return_pct", "MSCI World %", "series-msci"],
      ["xeon_return_pct", "XEON (Cash) %", "series-xeon"],
      ["inflation_return_pct", "Inflation %", "series-inflation"],
      ["weighted_score", "Area > MSCI %", "series-weighted"],
      ["freq_score", "Time > MSCI %", "series-freq"]
    ];
    const metricDefs = [
      ["market_value", "Market value"],
      ["return_pct", "Return"],
      ["open_cost_basis", "Open cost"],
      ["unrealized_pl", "Unrealized P/L"],
      ["realized_pl", "Realized P/L"],
      ["net_contributions", "Net contributions"]
    ];
    const chartDefs = [
      ["invested", "Invested", "series-invested"],
      ["net_contributions", "Net contributions", "series-net"],
      ["open_cost_basis", "Open cost basis", "series-cost"],
      ["proceeds", "Proceeds", "series-proceeds"],
      ["realized_pl", "Realized P/L", "series-realized"]
    ];
    const euro = new Intl.NumberFormat("en-IE", { style: "currency", currency: "EUR" });
    const euroWhole = new Intl.NumberFormat("en-IE", { style: "currency", currency: "EUR", maximumFractionDigits: 0 });
    const num = new Intl.NumberFormat("en-IE", { maximumFractionDigits: 4 });
    const pct = new Intl.NumberFormat("en-IE", { maximumFractionDigits: 2, minimumFractionDigits: 2 });

    function money(value) {
      if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
      return euro.format(Number(value));
    }
    function moneyWhole(value) {
      if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
      return euroWhole.format(Number(value));
    }
    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>"']/g, char => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
      }[char]));
    }
    function percent(value) {
      if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
      return `${pct.format(Number(value))}%`;
    }
    function signedClass(value) {
      const n = Number(value || 0);
      if (n > 0) return "positive";
      if (n < 0) return "negative";
      return "";
    }
    function renderMetrics(totals) {
      const v = totals.variations || {
        "1d": { pct: 0.0, amount: 0.0 },
        "1w": { pct: 0.0, amount: 0.0 },
        "1m": { pct: 0.0, amount: 0.0 }
      };

      const marketValueHtml = `
        <div class="metric">
          <span>Market value</span>
          <strong>${moneyWhole(totals.market_value)}</strong>
        </div>
      `;

      const variationHtml = ["1d", "1w", "1m"].map(period => {
        const val = v[period] || { pct: 0.0, amount: 0.0 };
        const displayVal = variationMode === "pct" 
          ? `${val.pct >= 0 ? "+" : ""}${pct.format(val.pct)}%` 
          : `${val.amount >= 0 ? "+" : ""}${moneyWhole(val.amount)}`;
        const colorClass = signedClass(val.amount);
        const hasMsci = val.msci_pct !== null && val.msci_pct !== undefined && Number.isFinite(Number(val.msci_pct));
        const hasVsMsci = val.vs_msci_pct !== null && val.vs_msci_pct !== undefined && Number.isFinite(Number(val.vs_msci_pct));
        const msciVal = hasMsci ? Number(val.msci_pct) : null;
        const vsMsciVal = hasVsMsci ? Number(val.vs_msci_pct) : null;
        const msciText = hasMsci ? `${msciVal >= 0 ? "+" : ""}${pct.format(msciVal)}%` : "-";
        const vsMsciText = hasVsMsci ? `${vsMsciVal >= 0 ? "+" : ""}${pct.format(vsMsciVal)} pp` : "-";
        const msciClass = signedClass(msciVal);
        const vsMsciClass = signedClass(vsMsciVal);
        const activeClass = activeMoversPeriod === period ? "active" : "";
        return `
          <div class="metric clickable" onclick="toggleVariationMode()" title="Click to toggle % / €">
            <div class="metric-label-row">
              <span>${period.toUpperCase()} Var</span>
              <button type="button" class="metric-plus ${activeClass}" onclick="toggleMovers('${period}', event)" aria-label="Show ${period.toUpperCase()} movers" title="Show ${period.toUpperCase()} movers">+</button>
            </div>
            <strong class="${colorClass}">${displayVal}</strong>
            <div class="metric-benchmark">
              <span>MSCI <span class="${msciClass}">${msciText}</span></span>
              <span class="${vsMsciClass}">${vsMsciText}</span>
            </div>
          </div>
        `;
      }).join("");

      const restHtml = metricDefs.slice(1).map(([key, label]) => `
        <div class="metric">
          <span>${label}</span>
          <strong class="${signedClass(key.includes("pl") || key.includes("pct") ? totals[key] : 0)}">${key.includes("pct") ? percent(totals[key]) : moneyWhole(totals[key])}</strong>
        </div>
      `).join("");

      document.getElementById("metrics").innerHTML = marketValueHtml + restHtml + variationHtml;
      renderMoversPanel();
    }
    function periodLabel(period) {
      if (period === "1d") return "1D";
      if (period === "1w") return "1W";
      if (period === "1m") return "1M";
      return String(period || "").toUpperCase();
    }
    function toggleMovers(period, event) {
      if (event) {
        event.preventDefault();
        event.stopPropagation();
      }
      activeMoversPeriod = activeMoversPeriod === period ? null : period;
      if (dashboardData) renderMetrics(periodMetrics(dashboardData));
    }
    function positionMovers(period) {
      if (!dashboardData) return [];
      return (dashboardData.positions || [])
        .filter(p => p && p.is_open && ["STOCK", "ETF"].includes(String(p.asset_type || "").toUpperCase()))
        .map(p => {
          const variation = (p.variations || {})[period] || {};
          const amount = Number(variation.amount || 0);
          const pctMove = Number(variation.pct || 0);
          return {
            asset: p.asset || p.symbol || "",
            symbol: p.symbol || p.isin || "",
            type: String(p.asset_type || "").toUpperCase(),
            amount,
            pct: pctMove
          };
        })
        .filter(row => row.asset && Number.isFinite(row.amount) && Number.isFinite(row.pct) && (row.amount !== 0 || row.pct !== 0));
    }
    function moverRowsHtml(rows) {
      if (!rows.length) return `<div class="empty-state">No stock or ETF movement data available for this window.</div>`;
      return rows.map(row => `
        <div class="mover-row">
          <div class="mover-name" title="${escapeHtml(row.asset)}">${escapeHtml(row.asset)}</div>
          <span class="mover-pill">${escapeHtml(row.type)}</span>
          <div class="mover-values">
            <strong class="${signedClass(row.amount)}">${row.pct >= 0 ? "+" : ""}${pct.format(row.pct)}%</strong>
            <small class="${signedClass(row.amount)}">${row.amount >= 0 ? "+" : ""}${money(row.amount)}</small>
          </div>
        </div>
      `).join("");
    }
    function renderMoversPanel() {
      const panel = document.getElementById("movers-panel");
      if (!panel) return;
      if (!activeMoversPeriod || !dashboardData) {
        panel.hidden = true;
        panel.innerHTML = "";
        return;
      }
      const movers = positionMovers(activeMoversPeriod);
      const byPct = [...movers].sort((a, b) => Math.abs(b.pct) - Math.abs(a.pct)).slice(0, 3);
      const byAmount = [...movers].sort((a, b) => Math.abs(b.amount) - Math.abs(a.amount)).slice(0, 3);
      const label = periodLabel(activeMoversPeriod);
      panel.hidden = false;
      panel.innerHTML = `
        <div class="movers-head">
          <strong>${label} stock/ETF movers</strong>
          <span class="subtle">Based on current holding value and cached/live price history</span>
        </div>
        <div class="movers-grid">
          <div class="movers-column">
            <h3>Top 3 by % move</h3>
            ${moverRowsHtml(byPct)}
          </div>
          <div class="movers-column">
            <h3>Top 3 by portfolio € move</h3>
            ${moverRowsHtml(byAmount)}
          </div>
        </div>
      `;
    }
    function filterByPeriod(series) {
      if (!series || !series.length) return series || [];
      if (selectedPeriod === "all") return series || [];
      if (selectedPeriod === "since24") return series.filter(p => new Date(p.date) >= new Date("2024-01-11"));
      
      const end = new Date(series[series.length - 1].date);
      const start = new Date(end);
      if (selectedPeriod === "ytd") {
        start.setMonth(0);
        start.setDate(1);
      }
      if (selectedPeriod === "1w") start.setDate(end.getDate() - 7);
      if (selectedPeriod === "1m") start.setMonth(end.getMonth() - 1);
      if (selectedPeriod === "1y") start.setFullYear(start.getFullYear() - 1);
      
      return series.filter(p => new Date(p.date) >= start);
    }
    function selectedWindowLabel() {
      if (selectedPeriod === "1w") return "Last 1 week";
      if (selectedPeriod === "1m") return "Last 1 month";
      if (selectedPeriod === "ytd") return "Year to date";
      if (selectedPeriod === "1y") return "Last 1 year";
      if (selectedPeriod === "since24") return "Since Jan 2024";
      return "All time";
    }
    function canUseSince24Window() {
      return SINCE_2024_PORTFOLIO_IDS.has(selectedPerson) && selectedBroker === "all";
    }
    function defaultPeriodForSelection() {
      return canUseSince24Window() ? "since24" : "all";
    }
    function normalizeSelectedPeriod() {
      if (selectedPeriod === "since24" && !canUseSince24Window()) {
        selectedPeriod = "all";
      }
    }
    function updatePeriodButtons() {
      normalizeSelectedPeriod();
      document.querySelectorAll("#periods button").forEach(button => {
        const isSince24 = button.dataset.period === "since24";
        button.style.display = isSince24 && !canUseSince24Window() ? "none" : "";
        button.classList.toggle("active", selectedPeriod === button.dataset.period);
      });
    }
    function chartRangeLabel(series) {
      const filtered = filterByPeriod(series || []);
      if (!filtered.length) return selectedWindowLabel();
      return `${selectedWindowLabel()} | ${filtered[0].date} to ${filtered[filtered.length - 1].date}`;
    }
    function periodMetrics(data) {
      const totals = { ...data.totals };
      if (selectedReturnMode === "total") {
        totals.return_pct = totals.total_return_pct;
        totals.historical_profit = totals.historical_total_profit;
        totals.market_value = totals.total_market_value || totals.market_value;
      }
      const isPrimaryAll = (selectedPerson === PRIMARY_PORTFOLIO_ID && selectedPeriod === "all");
      if (selectedPeriod === "all" && !isPrimaryAll) return totals;

      const values = filterByPeriod(data.valuation_series || []);
      const cash = filterByPeriod(data.series || []);
      if (values.length >= 2) {
        const first = values[0];
        const last = values[values.length - 1];
        const p_last = Number(selectedReturnMode === "total" ? last.total_profit : last.profit || 0);
        const p_first = Number(selectedReturnMode === "total" ? first.total_profit : first.profit || 0);
        const periodProfit = p_last - p_first;
        const isTotal = (selectedReturnMode === "total");
        const periodContributions = Number(isTotal ? last.total_net_contributions : last.net_contributions || 0) - Number(isTotal ? first.total_net_contributions : first.net_contributions || 0);
        const startVal = Number(isTotal ? first.total_market_value : first.market_value || 0);
        const capitalAtWork = Math.max(0.01, startVal + Math.max(0, periodContributions));
        totals.market_value = Number(isTotal ? last.total_market_value : last.market_value || 0);
        totals.return_pct = periodProfit / capitalAtWork * 100;
        totals.historical_profit = periodProfit;
      }
      if (cash.length >= 2) {
        const first = cash[0];
        const last = cash[cash.length - 1];
        totals.realized_pl = Number(last.realized_pl || 0) - Number(first.realized_pl || 0);
        totals.net_contributions = Number(last.net_contributions || 0) - Number(first.net_contributions || 0);
      }
      return totals;
    }
    function pointPath(points, key, xScale, yScale) {
      return points.map((p, i) => `${i ? "L" : "M"}${xScale(p.date).toFixed(2)} ${yScale(Number(p[key] || 0)).toFixed(2)}`).join(" ");
    }
    function xTicks(series, count = 6) {
      if (series.length <= count) return series.map(p => p.date);
      const ticks = [];
      for (let i = 0; i < count; i++) {
        const idx = Math.round(i * (series.length - 1) / (count - 1));
        ticks.push(series[idx].date);
      }
      return [...new Set(ticks)];
    }
    function formatShortDate(value) {
      return new Date(value).toLocaleDateString("en-GB", { month: "short", year: "2-digit" });
    }
    /* Compute nice Y-axis bounds: auto-scale to data with 5% padding */
    function niceYRange(rawMin, rawMax, forceZero) {
      let lo = rawMin, hi = rawMax;
      if (forceZero) lo = Math.min(0, lo);
      if (lo === hi) { lo -= 1; hi += 1; }
      const pad = (hi - lo) * 0.05;
      lo -= pad;
      hi += pad;
      if (forceZero && lo > 0) lo = 0;
      return { minY: lo, maxY: hi };
    }
    /* Smart tick formatter: abbreviates large numbers (10k, 1.2M) */
    function smartTickFormat(value) {
      const abs = Math.abs(value);
      if (abs >= 1e6) return (value / 1e6).toFixed(1).replace(/\.0$/, '') + 'M';
      if (abs >= 1e4) return (value / 1e3).toFixed(0) + 'k';
      if (abs >= 1e3) return (value / 1e3).toFixed(1).replace(/\.0$/, '') + 'k';
      return Math.round(value).toString();
    }
    /* Get SVG dimensions from its container and set viewBox to match */
    function initSvgSize(svg) {
      const container = svg.closest(".chart-wrap") || svg;
      const rect = container.getBoundingClientRect();
      const w = Math.max(320, Math.round(rect.width));
      const h = Math.max(220, Math.round(rect.height));
      svg.setAttribute('viewBox', `0 0 ${w} ${h}`);
      svg.setAttribute('preserveAspectRatio', 'none');
      return { w, h };
    }

    function pointerToSvgX(svg, clientX, width) {
      const box = svg.getBoundingClientRect();
      if (!box.width) return 0;
      return (clientX - box.left) / box.width * width;
    }

    function addHover(svg, series, defs, xScale, yScale, width, height, topMargin, bottom, valueFormatter) {
      const hover = document.createElementNS("http://www.w3.org/2000/svg", "g");
      hover.style.display = "none";
      hover.innerHTML = `<line class="hover-line" y1="${topMargin}" y2="${height - bottom}"></line><text class="hover-label" x="66" y="${topMargin + 14}"></text>`;
      svg.appendChild(hover);
      const line = hover.querySelector("line");
      const label = hover.querySelector("text");
      const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
      const leftEdge = Math.max(0, Math.min(...series.map(point => xScale(point.date))));
      const rightEdge = Math.min(width, Math.max(...series.map(point => xScale(point.date))));
      rect.setAttribute("x", String(leftEdge));
      rect.setAttribute("y", String(topMargin));
      rect.setAttribute("width", String(Math.max(1, rightEdge - leftEdge)));
      rect.setAttribute("height", String(height - bottom - topMargin));
      rect.setAttribute("fill", "transparent");
      rect.style.cursor = "crosshair";
      rect.addEventListener("pointermove", event => {
        const viewX = pointerToSvgX(svg, event.clientX, width);
        let nearest = series[0];
        let nearestDistance = Infinity;
        for (const point of series) {
          const distance = Math.abs(xScale(point.date) - viewX);
          if (distance < nearestDistance) {
            nearest = point;
            nearestDistance = distance;
          }
        }
        const x = xScale(nearest.date);
        line.setAttribute("x1", x);
        line.setAttribute("x2", x);
        
        // Highlight transaction line if there is one on this date
        svg.querySelectorAll(".flow-event-line").forEach(l => l.classList.remove("highlighted"));
        const flowLine = svg.querySelector(`.flow-event-line[data-date="${nearest.date}"]`);
        if (flowLine) {
          flowLine.classList.add("highlighted");
        }
        
        let flowText = "";
        const idx = series.indexOf(nearest);
        if (idx > 0) {
          const prev = series[idx - 1];
          const isTotal = (selectedReturnMode === "total");
          const useTotal = isTotal && showAllTransactions;
          const prevContrib = Number(useTotal ? (prev.total_net_contributions || 0) : (prev.net_contributions || 0));
          const currContrib = Number(useTotal ? (nearest.total_net_contributions || 0) : (nearest.net_contributions || 0));
          const diff = currContrib - prevContrib;
          if (Math.abs(diff) > 0.01) {
            const flowAmt = Math.abs(diff);
            const formattedAmt = flowAmt.toLocaleString("it-IT", {minimumFractionDigits: 0, maximumFractionDigits: 2});
            if (useTotal) {
              flowText = diff > 0 
                ? `  ·  [Inflow: +€${formattedAmt}]` 
                : `  ·  [Outflow: -€${formattedAmt}]`;
            } else {
              flowText = diff > 0 
                ? `  ·  [Buy: +€${formattedAmt}]` 
                : `  ·  [Sell: -€${formattedAmt}]`;
            }
          }
        }
        const labelText = `${nearest.date}  ${defs.map(([key, name]) => `${name}: ${valueFormatter(Number(nearest[key] || 0), key)}`).join("  ·  ")}${flowText}`;
        label.textContent = labelText;
        /* Keep label inside chart */
        const textLen = label.getComputedTextLength ? label.getComputedTextLength() : 200;
        const maxLabelX = width - textLen - 10;
        label.setAttribute("x", String(Math.min(maxLabelX, Math.max(leftEdge + 8, x + 12))));
        hover.style.display = "block";
      });
      rect.addEventListener("pointerleave", () => {
        hover.style.display = "none";
        svg.querySelectorAll(".flow-event-line").forEach(l => l.classList.remove("highlighted"));
      });
      svg.appendChild(rect);
    }
    function renderLineChart(svgId, series, defs, formatTick = null) {
      const svg = document.getElementById(svgId);
      svg.innerHTML = "";
      if (!series.length) return;
      const { w, h } = initSvgSize(svg);
      const left = 60, right = 20, top = 22, bottom = 36;
      const dates = series.map(p => new Date(p.date).getTime());
      const values = [];
      series.forEach(p => defs.forEach(([key]) => values.push(Number(p[key] || 0))));
      const minX = Math.min(...dates), maxX = Math.max(...dates);
      /* Auto-scale Y to data range — only force zero for "all" period or when data crosses 0 */
      const rawMin = Math.min(...values), rawMax = Math.max(...values);
      const forceZero = selectedPeriod === 'all' || (rawMin < 0 && rawMax > 0);
      const { minY, maxY } = niceYRange(rawMin, rawMax, forceZero);
      const xScale = d => left + ((new Date(d).getTime() - minX) / Math.max(1, maxX - minX)) * (w - left - right);
      const yScale = v => top + (1 - ((v - minY) / Math.max(1, maxY - minY))) * (h - top - bottom);
      /* Draw zero-line if visible */
      if (minY <= 0 && maxY >= 0) {
        const axisY = yScale(0);
        svg.insertAdjacentHTML("beforeend", `<line class="axis" x1="${left}" y1="${axisY}" x2="${w-right}" y2="${axisY}" stroke-opacity="0.3"></line>`);
      }
      svg.insertAdjacentHTML("beforeend", `<line class="axis" x1="${left}" y1="${top}" x2="${left}" y2="${h-bottom}"></line>`);
      /* Y-axis ticks */
      const tickFmt = formatTick || smartTickFormat;
      const tickCount = 5;
      for (let i = 0; i <= tickCount; i++) {
        const t = i / tickCount;
        const y = top + t * (h - top - bottom);
        const value = maxY - t * (maxY - minY);
        svg.insertAdjacentHTML("beforeend", `<line class="grid-line" x1="${left}" y1="${y}" x2="${w-right}" y2="${y}"></line>`);
        svg.insertAdjacentHTML("beforeend", `<text x="${left - 6}" y="${y + 4}" class="chart-axis-label" text-anchor="end">${tickFmt(value)}</text>`);
      }
      /* Transaction Flow Events (Dotted vertical lines) */
      if (svgId === "value-chart" && showTransactions) {
        const isTotal = (selectedReturnMode === "total");
        const useTotal = isTotal && showAllTransactions;
        
        let maxDiff = 0.01;
        for (let i = 1; i < series.length; i++) {
          const prev = series[i - 1];
          const curr = series[i];
          const prevContrib = Number(useTotal ? (prev.total_net_contributions || 0) : (prev.net_contributions || 0));
          const currContrib = Number(useTotal ? (curr.total_net_contributions || 0) : (curr.net_contributions || 0));
          const diff = Math.abs(currContrib - prevContrib);
          if (diff > maxDiff) maxDiff = diff;
        }

        for (let i = 1; i < series.length; i++) {
          const prev = series[i - 1];
          const curr = series[i];
          const prevContrib = Number(useTotal ? (prev.total_net_contributions || 0) : (prev.net_contributions || 0));
          const currContrib = Number(useTotal ? (curr.total_net_contributions || 0) : (curr.net_contributions || 0));
          const diff = currContrib - prevContrib;
          if (Math.abs(diff) > 0.01) {
            const x = xScale(curr.date);
            const ratio = Math.abs(diff) / maxDiff;
            // Scale stroke width from 1.0px to 4.0px
            const strokeWidth = (1.0 + ratio * 3.0).toFixed(2);
            // Scale opacity from 0.25 to 0.75
            const opacity = (0.25 + ratio * 0.5).toFixed(2);
            const flowClass = diff > 0 ? "is-inflow" : "is-outflow";
            const flowAmtStr = Math.abs(diff).toLocaleString("it-IT", {minimumFractionDigits: 0, maximumFractionDigits: 2});
            let tooltipText = "";
            if (useTotal) {
              tooltipText = diff > 0 
                ? `${curr.date}: Inflow +€${flowAmtStr}` 
                : `${curr.date}: Outflow/Purchase -€${flowAmtStr}`;
            } else {
              tooltipText = diff > 0 
                ? `${curr.date}: Buy +€${flowAmtStr}` 
                : `${curr.date}: Sell -€${flowAmtStr}`;
            }
            
            svg.insertAdjacentHTML("beforeend", `
              <line class="flow-event-line ${flowClass}" 
                    x1="${x}" y1="${top}" 
                    x2="${x}" y2="${h - bottom}" 
                    stroke-opacity="${opacity}" 
                    stroke-width="${strokeWidth}" 
                    stroke-dasharray="3,3"
                    data-date="${curr.date}"
                    data-amount="${diff}">
                <title>${tooltipText}</title>
              </line>
            `);
          }
        }
      }

      /* Data lines */
      defs.forEach(([key, label, klass]) => {
        svg.insertAdjacentHTML("beforeend", `<path class="series-line ${klass}" d="${pointPath(series, key, xScale, yScale)}"></path>`);
      });
      /* X-axis ticks */
      xTicks(series, Math.min(8, Math.floor(w / 110))).forEach(date => {
        const x = xScale(date);
        svg.insertAdjacentHTML("beforeend", `<text x="${x}" y="${h - 10}" class="chart-axis-label" text-anchor="middle">${formatShortDate(date)}</text>`);
      });
      addHover(svg, series, defs, xScale, yScale, w, h, top, bottom, (value, key) => key.includes("pct") || key.includes("score") ? `${value.toFixed(2)}%` : money(value));
    }
    function getLegendColor(klass) {
      if (klass.includes("market")) return getComputedStyle(document.documentElement).getPropertyValue("--positive");
      if (klass.includes("invested")) return getComputedStyle(document.documentElement).getPropertyValue("--accent");
      if (klass.includes("profit")) return getComputedStyle(document.documentElement).getPropertyValue("--series-violet");
      if (klass.includes("return")) return getComputedStyle(document.documentElement).getPropertyValue("--negative");
      if (klass.includes("msci")) return getComputedStyle(document.documentElement).getPropertyValue("--series-cyan");
      if (klass.includes("xeon")) return getComputedStyle(document.documentElement).getPropertyValue("--series-pink");
      if (klass.includes("inflation")) return getComputedStyle(document.documentElement).getPropertyValue("--warning");
      if (klass.includes("weighted")) return getComputedStyle(document.documentElement).getPropertyValue("--series-violet");
      if (klass.includes("freq")) return getComputedStyle(document.documentElement).getPropertyValue("--series-teal");
      return getComputedStyle(document.documentElement).getPropertyValue("--text-muted");
    }
    function bindReturnLegend() {
      document.querySelectorAll("[data-return-series]").forEach(input => {
        input.addEventListener("change", event => {
          returnVisibility[event.target.dataset.returnSeries] = event.target.checked;
          if (dashboardData) {
            renderValueCharts(dashboardData.valuation_series || []);
          }
        });
      });
    }
    function normalizeReturnSeries(series) {
      if (!series || !series.length) return [];
      const p0 = series[0];
      const r0 = Number(selectedReturnMode === "total" ? p0.total_return_pct : p0.return_pct || 0);
      const m0 = Number(p0.msci_return_pct || 0);
      const xeon0 = Number(p0.xeon_return_pct || 0);
      const inf0 = Number(p0.inflation_return_pct || 0);
      const mapped = series.map(p => {
        const r_t = Number(selectedReturnMode === "total" ? p.total_return_pct : p.return_pct || 0);
        const m_t = Number(p.msci_return_pct || 0);
        const xeon_t = Number(p.xeon_return_pct || 0);
        const inf_t = Number(p.inflation_return_pct || 0);
        
        const norm_r = Math.abs(1 + r0 / 100) > 1e-6 ? ((1 + r_t / 100) / (1 + r0 / 100) - 1) * 100 : 0;
        const norm_m = Math.abs(1 + m0 / 100) > 1e-6 ? ((1 + m_t / 100) / (1 + m0 / 100) - 1) * 100 : 0;
        const norm_xeon = Math.abs(1 + xeon0 / 100) > 1e-6 ? ((1 + xeon_t / 100) / (1 + xeon0 / 100) - 1) * 100 : 0;
        const norm_inf = Math.abs(1 + inf0 / 100) > 1e-6 ? ((1 + inf_t / 100) / (1 + inf0 / 100) - 1) * 100 : 0;
        
        return {
          ...p,
          return_pct: norm_r,
          msci_return_pct: norm_m,
          xeon_return_pct: norm_xeon,
          inflation_return_pct: norm_inf
        };
      });
      
      mapped.forEach((p, idx) => {
        const scores = timeWeightedOutperformanceScores(mapped.slice(0, idx + 1));
        p.weighted_score = scores.areaScore;
        p.freq_score = scores.timeScore;
      });
      return mapped;
    }
    function integrateDiffSegment(d0, d1, days) {
      if (days <= 0) return { positiveArea: 0, negativeArea: 0, positiveDays: d0 > 0 ? days : 0, totalDays: days };
      if (Math.abs(d0) < 1e-9 && Math.abs(d1) < 1e-9) {
        return { positiveArea: 0, negativeArea: 0, positiveDays: 0, totalDays: days };
      }
      if (d0 >= 0 && d1 >= 0) {
        return { positiveArea: ((d0 + d1) / 2) * days, negativeArea: 0, positiveDays: days, totalDays: days };
      }
      if (d0 <= 0 && d1 <= 0) {
        return { positiveArea: 0, negativeArea: ((Math.abs(d0) + Math.abs(d1)) / 2) * days, positiveDays: 0, totalDays: days };
      }
      const crossing = Math.abs(d0) / (Math.abs(d0) + Math.abs(d1));
      const daysToCross = days * crossing;
      if (d0 > 0) {
        return {
          positiveArea: (d0 / 2) * daysToCross,
          negativeArea: (Math.abs(d1) / 2) * (days - daysToCross),
          positiveDays: daysToCross,
          totalDays: days
        };
      }
      return {
        positiveArea: (d1 / 2) * (days - daysToCross),
        negativeArea: (Math.abs(d0) / 2) * daysToCross,
        positiveDays: days - daysToCross,
        totalDays: days
      };
    }
    function timeWeightedOutperformanceScores(series) {
      if (!series || series.length < 2) return { timeScore: 100, areaScore: 50 };
      let positiveArea = 0;
      let negativeArea = 0;
      let positiveDays = 0;
      let totalDays = 0;
      for (let i = 1; i < series.length; i++) {
        const prev = series[i - 1];
        const curr = series[i];
        const prevDate = new Date(prev.date).getTime();
        const currDate = new Date(curr.date).getTime();
        const days = Math.max(0, (currDate - prevDate) / 86400000);
        if (!Number.isFinite(days) || days <= 0) continue;
        const d0 = Number(prev.return_pct || 0) - Number(prev.msci_return_pct || 0);
        const d1 = Number(curr.return_pct || 0) - Number(curr.msci_return_pct || 0);
        const segment = integrateDiffSegment(d0, d1, days);
        positiveArea += segment.positiveArea;
        negativeArea += segment.negativeArea;
        positiveDays += segment.positiveDays;
        totalDays += segment.totalDays;
      }
      const totalArea = positiveArea + negativeArea;
      return {
        timeScore: totalDays > 1e-6 ? (positiveDays / totalDays * 100) : 100,
        areaScore: totalArea > 1e-6 ? (positiveArea / totalArea * 100) : 50
      };
    }

    function renderValueCharts(series) {
      const filtered = filterByPeriod(series);
      const isTotal = (selectedReturnMode === "total");
      const valueDefs = [
        [isTotal ? "total_market_value" : "market_value", "Portfolio value", "series-market"],
        [isTotal ? "total_net_contributions" : "net_contributions", "Net contributions", "series-invested"],
        [isTotal ? "total_profit" : "profit", "Profit", "series-profit"]
      ];
      const activeReturnDefs = returnDefs.filter(([key]) => returnVisibility[key]);
      renderLineChart("value-chart", filtered, valueDefs);
      
      const normalizedReturns = normalizeReturnSeries(filtered);
      renderLineChart("return-chart", normalizedReturns, activeReturnDefs, value => `${value.toFixed(1)}%`);

      const outperformanceScores = timeWeightedOutperformanceScores(normalizedReturns);
      const scoreFreq = outperformanceScores.timeScore;
      const scoreWeighted = outperformanceScores.areaScore;

      const scorePills = `
        <button type="button" id="freq-pill" class="score-pill teal ${returnVisibility.freq_score ? "active" : ""}" title="Toggle time-weighted outperformance line">
          <span class="score-pill-label">Time > MSCI</span>
          <span class="score-pill-value" style="color: ${scoreFreq >= 50 ? 'var(--positive)' : 'var(--negative)'};">${scoreFreq.toFixed(1)}%</span>
        </button>
        <button type="button" id="weighted-pill" class="score-pill violet ${returnVisibility.weighted_score ? "active" : ""}" title="Toggle area-weighted outperformance line">
          <span class="score-pill-label">Area</span>
          <span class="score-pill-value" style="color: ${scoreWeighted >= 50 ? 'var(--positive)' : 'var(--negative)'};">${scoreWeighted.toFixed(1)}%</span>
        </button>
      `;

      const valHtml = valueDefs.map(([key, label, klass]) => `<span class="legend-item"><i class="dot" style="background:${getLegendColor(klass)}"></i>${label}</span>`);
      const retHtml = returnDefs.map(([key, label, klass]) => {
        const lineStyle = klass.includes('msci') || klass.includes('inflation') || klass.includes('xeon') ? 'border-radius:0; height:2px; margin-top:6px;' : '';
        return `
          <label>
            <input type="checkbox" data-return-series="${key}" ${returnVisibility[key] ? "checked" : ""}>
            <i class="dot" style="background:${getLegendColor(klass)}; ${lineStyle}"></i>
            ${label}
          </label>
        `;
      });
      const transHtml = `
        <label>
          <input type="checkbox" id="toggle-transactions" ${showTransactions ? "checked" : ""}>
          <i class="dot" style="background:var(--accent); border-radius:0; width: 2px; height: 10px; border: 1px dashed var(--accent); margin-top: 2px;"></i>
          Flow Events
        </label>
        ${(showTransactions && isTotal) ? `
        <label>
          <input type="checkbox" id="toggle-show-all-transactions" ${showAllTransactions ? "checked" : ""}>
          Show All
        </label>
        ` : ""}
      `;
      document.getElementById("value-legend").innerHTML = `
        <div class="chart-controls">
          <div class="chart-control-group">
            <div class="chart-control-title">Value chart</div>
            <div class="chart-control-items">${valHtml.join("")}</div>
          </div>
          <div class="chart-control-group">
            <div class="chart-control-title">Return lines</div>
            <div class="chart-control-items">${retHtml.join("")}</div>
          </div>
          <div class="chart-control-group">
            <div class="chart-control-title">Outperformance</div>
            <div class="chart-control-items">${scorePills}</div>
          </div>
          <div class="chart-control-group">
            <div class="chart-control-title">Events</div>
            <div class="chart-control-items">${transHtml}</div>
          </div>
        </div>
      `;
      bindReturnLegend();

      document.getElementById("freq-pill").addEventListener("click", () => {
        returnVisibility.freq_score = !returnVisibility.freq_score;
        if (dashboardData) {
          renderValueCharts(dashboardData.valuation_series || []);
        }
      });
      document.getElementById("weighted-pill").addEventListener("click", () => {
        returnVisibility.weighted_score = !returnVisibility.weighted_score;
        if (dashboardData) {
          renderValueCharts(dashboardData.valuation_series || []);
        }
      });

      const toggleTrans = document.getElementById("toggle-transactions");
      if (toggleTrans) {
        toggleTrans.addEventListener("change", event => {
          showTransactions = event.target.checked;
          if (dashboardData) {
            renderValueCharts(dashboardData.valuation_series || []);
          }
        });
      }
      const toggleAllTrans = document.getElementById("toggle-show-all-transactions");
      if (toggleAllTrans) {
        toggleAllTrans.addEventListener("change", event => {
          showAllTransactions = event.target.checked;
          if (dashboardData) {
            renderValueCharts(dashboardData.valuation_series || []);
          }
        });
      }
    }
    function renderChart(series) {
      series = filterByPeriod(series);
      const svg = document.getElementById("chart");
      svg.innerHTML = "";
      if (!series.length) {
        document.getElementById("legend").innerHTML = "";
        return;
      }
      const activeChartDefs = chartDefs.filter(([key]) => cashVisibility[key]);
      if (!activeChartDefs.length) {
        document.getElementById("legend").innerHTML = chartDefs.map(([key, label, klass]) => cashLegendItem(key, label, klass)).join("");
        bindCashLegend();
        return;
      }
      const { w, h } = initSvgSize(svg);
      const left = 60, right = 20, top = 22, bottom = 36;
      const dates = series.map(p => new Date(p.date).getTime());
      const values = [];
      series.forEach(p => activeChartDefs.forEach(([key]) => values.push(Number(p[key] || 0))));
      const minX = Math.min(...dates), maxX = Math.max(...dates);
      const rawMin = Math.min(...values), rawMax = Math.max(...values);
      const forceZero = selectedPeriod === 'all' || (rawMin < 0 && rawMax > 0);
      const { minY, maxY } = niceYRange(rawMin, rawMax, forceZero);
      const xScale = d => left + ((new Date(d).getTime() - minX) / Math.max(1, maxX - minX)) * (w - left - right);
      const yScale = v => top + (1 - ((v - minY) / Math.max(1, maxY - minY))) * (h - top - bottom);

      if (minY <= 0 && maxY >= 0) {
        const axisY = yScale(0);
        svg.insertAdjacentHTML("beforeend", `<line class="axis" x1="${left}" y1="${axisY}" x2="${w-right}" y2="${axisY}" stroke-opacity="0.3"></line>`);
      }
      svg.insertAdjacentHTML("beforeend", `<line class="axis" x1="${left}" y1="${top}" x2="${left}" y2="${h-bottom}"></line>`);
      const tickCount = 5;
      for (let i = 0; i <= tickCount; i++) {
        const t = i / tickCount;
        const y = top + t * (h - top - bottom);
        const value = maxY - t * (maxY - minY);
        svg.insertAdjacentHTML("beforeend", `<line class="grid-line" x1="${left}" y1="${y}" x2="${w-right}" y2="${y}"></line>`);
        svg.insertAdjacentHTML("beforeend", `<text x="${left - 6}" y="${y + 4}" class="chart-axis-label" text-anchor="end">${smartTickFormat(value)}</text>`);
      }
      activeChartDefs.forEach(([key, label, klass]) => {
        svg.insertAdjacentHTML("beforeend", `<path class="series-line ${klass}" d="${pointPath(series, key, xScale, yScale)}"></path>`);
      });
      xTicks(series, Math.min(8, Math.floor(w / 110))).forEach(date => {
        const x = xScale(date);
        svg.insertAdjacentHTML("beforeend", `<text x="${x}" y="${h - 10}" class="chart-axis-label" text-anchor="middle">${formatShortDate(date)}</text>`);
      });
      document.getElementById("legend").innerHTML = chartDefs.map(([key, label, klass]) => cashLegendItem(key, label, klass)).join("");
      bindCashLegend();
      addHover(svg, series, activeChartDefs, xScale, yScale, w, h, top, bottom, value => money(value));
    }
    function cashLegendColor(klass) {
      return getComputedStyle(document.documentElement).getPropertyValue(
        klass.includes("invested") ? "--blue" : klass.includes("net") ? "--green" : klass.includes("cost") ? "--teal" : klass.includes("proceeds") ? "--amber" : "--red"
      );
    }
    function cashLegendItem(key, label, klass) {
      return `<label><input type="checkbox" data-cash-series="${key}" ${cashVisibility[key] ? "checked" : ""}> <i class="dot" style="background:${cashLegendColor(klass)}"></i>${label}</label>`;
    }
    function bindCashLegend() {
      document.querySelectorAll("[data-cash-series]").forEach(input => {
        input.addEventListener("change", event => {
          cashVisibility[event.target.dataset.cashSeries] = event.target.checked;
          if (dashboardData) renderChart(dashboardData.series);
        });
      });
    }
    function sortValue(row, key) {
      const value = row[key];
      if (value === null || value === undefined) return "";
      return value;
    }
    function sortedPositions(positions) {
      return [...positions].sort((a, b) => {
        const av = sortValue(a, sortState.key);
        const bv = sortValue(b, sortState.key);
        if (typeof av === "number" || typeof bv === "number" || sortState.key === "is_open") {
          return (Number(av || 0) - Number(bv || 0)) * (sortState.direction === "asc" ? 1 : -1);
        }
        return String(av).localeCompare(String(bv), undefined, { numeric: true, sensitivity: "base" }) * (sortState.direction === "asc" ? 1 : -1);
      });
    }
    function updateSortHeaders() {
      document.querySelectorAll("th[data-sort]").forEach(th => {
        const base = th.textContent.replace(/\s[↑↓]$/, "");
        th.textContent = th.dataset.sort === sortState.key ? `${base} ${sortState.direction === "asc" ? "↑" : "↓"}` : base;
      });
    }
    function badgeHtml(type) {
      if (!type) return "";
      let color = "";
      let bg = "";
      if (type === "ETF") {
        color = "var(--positive)";
        bg = "color-mix(in srgb, var(--positive) 12%, transparent)";
      } else if (type === "STOCK") {
        color = "var(--warning)";
        bg = "color-mix(in srgb, var(--warning) 12%, transparent)";
      } else if (type === "CUR") {
        color = "var(--series-violet)";
        bg = "color-mix(in srgb, var(--series-violet) 12%, transparent)";
      } else {
        return "";
      }
      return `<span style="font-size: 9px; font-weight: 700; text-transform: uppercase; color: ${color}; background: ${bg}; border: 1px solid ${color}33; padding: 1px 5px; border-radius: 4px; letter-spacing: 0.5px; display: inline-flex; align-items: center; line-height: 12px; margin-left: 4px; flex-shrink: 0;">${type}</span>`;
    }
    function focusedOpenHoldings(open) {
      if (!open.length) return { rows: [], targetCount: 0 };
      const targetCount = Math.max(1, Math.ceil(open.length * 0.5));
      const ranked = [...open].sort((a, b) => Number(b.market_value_eur || 0) - Number(a.market_value_eur || 0));
      const selected = new Set(ranked.slice(0, targetCount));
      return { rows: open.filter(row => selected.has(row)), targetCount };
    }
    function updateHoldingsControls(open, closed, visibleOpen, focusedCount) {
      const title = document.getElementById("holdings-view-title");
      const detail = document.getElementById("holdings-view-detail");
      const showAllBtn = document.getElementById("btn-show-all-holdings");
      const showAllLabel = document.getElementById("btn-show-all-label");
      const showAllSub = document.getElementById("btn-show-all-sub");
      const closedBtn = document.getElementById("btn-toggle-closed");
      const closedLabel = document.getElementById("btn-closed-label");
      const closedSub = document.getElementById("btn-closed-sub");
      const canFocus = open.length > focusedCount;

      if (title) title.textContent = showAllHoldings || !canFocus ? "All open holdings" : "Top holdings";
      if (detail) {
        detail.textContent = showAllHoldings || !canFocus
          ? `${visibleOpen} open positions shown${closed.length ? `, ${closed.length} closed ${showClosed ? "included" : "available"}` : ""}.`
          : `Showing top ${visibleOpen}/${open.length} open positions by current value.`;
      }
      if (showAllBtn) {
        showAllBtn.disabled = !canFocus;
        showAllBtn.classList.toggle("active", showAllHoldings && canFocus);
      }
      if (showAllLabel) showAllLabel.textContent = showAllHoldings && canFocus ? "Top 50%" : "Show all";
      if (showAllSub) showAllSub.textContent = canFocus ? (showAllHoldings ? "Refocus" : `${open.length - visibleOpen} more`) : "All shown";
      if (closedBtn) {
        closedBtn.disabled = !closed.length;
        closedBtn.classList.toggle("active", showClosed && closed.length > 0);
      }
      if (closedLabel) closedLabel.textContent = showClosed && closed.length ? "Hide closed" : "Closed";
      if (closedSub) closedSub.textContent = closed.length ? `${closed.length} exited` : "None";
    }
    function renderPositions(positions) {
      const open = positions.filter(p => p.is_open);
      const closed = positions.filter(p => !p.is_open);
      const focused = focusedOpenHoldings(open);
      const openDisplayed = showAllHoldings ? open : focused.rows;
      const displayed = showClosed ? [...openDisplayed, ...closed] : openDisplayed;
      const hiddenOpen = Math.max(0, open.length - openDisplayed.length);
      document.getElementById("holdings-count").textContent = `${openDisplayed.length}/${open.length} open shown${hiddenOpen ? ` · ${hiddenOpen} hidden` : ""}${showClosed && closed.length ? ` · ${closed.length} closed shown` : ""}`;
      updateHoldingsControls(open, closed, openDisplayed.length, focused.targetCount);
      const sortedDisplayed = sortedPositions(displayed);
      document.getElementById("positions").innerHTML = sortedDisplayed.length ? sortedDisplayed.map(p => {
        const logoUrl = p.isin ? `https://assets.parqet.com/logos/isin/${p.isin}?format=png` : (p.symbol ? `https://assets.parqet.com/logos/symbol/${p.symbol}?format=png` : '');
        const logoImg = logoUrl ? `<img src="${logoUrl}" onerror="if(this.src.indexOf('/isin/') !== -1 && '${p.symbol}') { this.src = 'https://assets.parqet.com/logos/symbol/${p.symbol}?format=png'; } else { this.style.display='none'; }" style="width: 20px; height: 20px; border-radius: 50%; vertical-align: middle; margin-right: 8px; background: var(--tint-hover); flex-shrink: 0;">` : '';
        
        let assetNameHtml = `<span>${p.asset}</span>`;
        if (p.asset.toLowerCase().includes("europension taxbenefit")) {
          assetNameHtml = `
            <span>${p.asset}</span>
            <span class="info-icon" onclick="showAssetInfoPopup('europension', event)" class="info-dot" title="Click for details">i</span>
          `;
        } else if (p.asset.toLowerCase().includes("mystyle")) {
          assetNameHtml = `
            <span>${p.asset}</span>
            <span class="info-icon" onclick="showAssetInfoPopup('mystyle', event)" class="info-dot" title="Click for details">i</span>
          `;
        }
        
        return `
          <tr>
            <td class="cell-flex">${logoImg}${assetNameHtml}${badgeHtml(p.asset_type)}</td>
            <td>${num.format(p.quantity)}</td>
            <td>${p.isin || ""}</td>
            <td>${p.symbol || ""}</td>
            <td>${p.price ? `${num.format(p.price)} ${p.price_currency}` : "-"}</td>
            <td>${money(p.market_value_eur)}</td>
            <td>${money(p.cost_basis_eur)}</td>
            <td class="${signedClass(p.display_pl_eur)}">${money(p.display_pl_eur)}</td>
            <td class="${signedClass(p.display_pl_pct)}">${percent(p.display_pl_pct)}</td>
            <td><span class="status ${p.pricing_status}">${p.pricing_status}</span></td>
          </tr>
        `;
      }).join("") : `<tr><td colspan="10" class="empty-state">No holdings available for this selection.</td></tr>`;
      updateSortHeaders();
    }
    window.toggleSector = function(subId, rowEl) {
      const subRow = document.getElementById(subId);
      if (!subRow) return;
      const chevron = rowEl.querySelector(".chevron");
      if (subRow.style.display === "none") {
        subRow.style.display = "table-row";
        if (chevron) chevron.style.transform = "rotate(90deg)";
      } else {
        subRow.style.display = "none";
        if (chevron) chevron.style.transform = "rotate(0deg)";
      }
    };
    function distributionRows(rows, key) {
      if (!rows || !rows.length) return `<tr><td colspan="3" class="empty-state">No distribution data available.</td></tr>`;
      
      if (key === "sector") {
        return rows.map((row, index) => {
          const subId = `sector-sub-${index}`;
          const hasHoldings = row.holdings && row.holdings.length;
          
          let holdingsHtml = "";
          if (hasHoldings) {
            holdingsHtml = `
              <tr id="${subId}" style="display: none; background: var(--tint-faint);">
                <td colspan="3" style="padding: 4px 12px 8px 20px;">
                  <table style="width: 100%; border-collapse: collapse; margin: 2px 0;">
                    <tbody>
                      ${row.holdings.map(h => {
                        const hTicker = h.holding_ticker;
                        const logoUrl = hTicker ? `https://assets.parqet.com/logos/symbol/${hTicker}?format=png` : '';
                        const logoImg = logoUrl ? `<img src="${logoUrl}" onerror="this.style.display='none';" style="width: 14px; height: 14px; border-radius: 50%; vertical-align: middle; margin-right: 6px; background: var(--tint-hover); flex-shrink: 0;">` : '';
                        return `
                          <tr style="border-bottom: 1px solid var(--tint-faint); line-height: 24px;">
                            <td style="text-align: left; padding: 2px 0; font-size: 0.82em; display: flex; align-items: center; color: var(--text-muted);">${logoImg}<span>${escapeHtml(h.holding)}</span></td>
                            <td class="sub-cell">${money(h.market_value_eur)}</td>
                            <td class="sub-cell">${percent(h.weight_pct)}</td>
                          </tr>
                        `;
                      }).join("")}
                    </tbody>
                  </table>
                </td>
              </tr>
            `;
          }
          
          const chevron = hasHoldings ? `<span class="chevron" style="display: inline-block; transition: transform 0.2s; margin-right: 6px; font-size: 0.75em; color: var(--text-muted); width: 10px; text-align: center;">▶</span>` : "";
          const clickableStyle = hasHoldings ? "cursor: pointer; user-select: none;" : "";
          const onclickAttr = hasHoldings ? `onclick="toggleSector('${subId}', this)"` : "";
          
          return `
            <tr style="${clickableStyle}" ${onclickAttr}>
              <td class="cell-flex">${chevron}${distributionNameCell(row, key)}</td>
              <td>${money(row.market_value_eur)}</td>
              <td>${percent(row.weight_pct)}</td>
            </tr>
            ${holdingsHtml}
          `;
        }).join("");
      }

      return rows.map(row => {
        const ticker = row.holding_ticker;
        const logoUrl = (key === "holding" && ticker) ? `https://assets.parqet.com/logos/symbol/${ticker}?format=png` : '';
        const logoImg = logoUrl ? `<img src="${logoUrl}" onerror="this.style.display='none';" class="sym-logo">` : '';
        return `
          <tr>
            <td class="cell-flex">${logoImg}${distributionNameCell(row, key)}</td>
            <td>${money(row.market_value_eur)}</td>
            <td>${percent(row.weight_pct)}</td>
          </tr>
        `;
      }).join("");
    }
    function distributionNameCell(row, key) {
      const name = escapeHtml(row[key]);
      const badge = key === "holding" ? badgeHtml(row.asset_type) : "";
      if (key !== "holding" || !row.source_assets || !row.source_assets.length) return `<span>${name}</span>${badge}`;
      const pills = row.source_assets.map(asset => `<span class="source-pill" title="${escapeHtml(asset)}">${escapeHtml(asset)}</span>`).join("");
      return `<div class="underlying-name"><span>${name}</span>${badge}<span class="source-pills">${pills}</span></div>`;
    }
    function sourceStatusLabel(row) {
      const message = row.message ? ` - ${row.message}` : "";
      return `${row.status || ""}${message}`;
    }
    function sourceKey(row) {
      return `${row.asset || ""}|${row.isin || ""}`;
    }
    function sourceRowsForSource(data, source) {
      return (data.source_rows || data.rows || []).filter(row => (
        row.source_asset === source.asset && (!source.isin || !row.source_isin || row.source_isin === source.isin)
      ));
    }
    function selectedUnderlyingRows(data, source) {
      const rows = sourceRowsForSource(data, source);
      const total = rows.reduce((sum, row) => sum + Number(row.market_value_eur || 0), 0);
      return rows.map(row => ({
        holding: row.holding_name,
        holding_ticker: row.holding_ticker,
        market_value_eur: row.market_value_eur,
        weight_pct: total > 0 ? Number(((Number(row.market_value_eur || 0) / total) * 100).toFixed(2)) : 0,
        asset_class: row.asset_class,
        asset_type: determineAssetTypeFromClass(row.asset_class),
        source_assets: [source.asset]
      })).sort((a, b) => Number(b.market_value_eur || 0) - Number(a.market_value_eur || 0));
    }
    function determineAssetTypeFromClass(assetClass) {
      const value = String(assetClass || "").toLowerCase();
      if (value.includes("single share") || value.includes("equity")) return "STOCK";
      if (value.includes("cash")) return "CUR";
      if (value.includes("etf") || value.includes("bond") || value.includes("fund")) return "ETF";
      return "";
    }
    function renderDistribution(distribution) {
      const data = distribution || {};
      const sources = data.composition_sources || [];
      let selectedSource = sources.find(row => sourceKey(row) === selectedDistributionSource);
      if (selectedDistributionSource && !selectedSource) selectedDistributionSource = "";
      const underlyingRows = selectedSource ? selectedUnderlyingRows(data, selectedSource) : data.underlying;
      const sourceCoverage = data.composition_source_coverage || {resolved: 0, total: 0};
      document.getElementById("distribution-summary").textContent =
        `${data.covered_assets || 0}/${data.open_assets || 0} open assets mapped | ${sourceCoverage.resolved}/${sourceCoverage.total} composition sources | ${money(data.total_value_eur)} total${selectedSource ? ` | selected: ${selectedSource.asset}` : ""}`;
      document.getElementById("distribution-sources").innerHTML = sources.length
        ? sources.map(row => {
            const isSelected = sourceKey(row) === selectedDistributionSource;
            const symbol = window.assetToSymbolMap ? window.assetToSymbolMap[row.asset] : '';
            const logoUrl = row.isin ? `https://assets.parqet.com/logos/isin/${row.isin}?format=png` : (symbol ? `https://assets.parqet.com/logos/symbol/${symbol}?format=png` : '');
            const logoImg = logoUrl ? `<img src="${logoUrl}" onerror="if(this.src.indexOf('/isin/') !== -1 && '${symbol}') { this.src = 'https://assets.parqet.com/logos/symbol/${symbol}?format=png'; } else { this.style.display='none'; }" class="sym-logo">` : '';
            return `
              <tr class="composition-source-row ${isSelected ? "selected" : ""}" data-source-key="${escapeHtml(sourceKey(row))}">
                <td class="cell-flex">${logoImg}<div><div style="display:flex; align-items:center; gap:4px;"><span>${row.asset}</span>${badgeHtml(window.assetToTypeMap ? window.assetToTypeMap[row.asset] : '')}${isSelected ? '<span class="selected-flag">Selected</span>' : ''}</div><div class="subtle">${row.isin || ""}</div></div></td>
                <td class="ta-l">${escapeHtml(row.fund_name || row.asset || "")}</td>
                <td>${row.issuer || ""}</td>
                <td>${sourceStatusLabel(row)}</td>
                <td>${row.rows || 0}${row.weight_sum ? ` / ${row.weight_sum}%` : ""}</td>
                <td>${row.fetched_at || ""}</td>
              </tr>
            `;
          }).join("")
        : `<tr><td colspan="6" class="empty-state">No ETF composition source metadata available.</td></tr>`;
      document.getElementById("distribution-underlying").innerHTML = distributionRows(underlyingRows, "holding");
      document.querySelectorAll(".composition-source-row").forEach(rowEl => {
        rowEl.addEventListener("click", () => {
          selectedDistributionSource = selectedDistributionSource === rowEl.dataset.sourceKey ? "" : rowEl.dataset.sourceKey;
          renderDistribution(data);
        });
      });
      document.getElementById("distribution-sectors").innerHTML = distributionRows(data.sectors, "sector");
      document.getElementById("distribution-geographies").innerHTML = distributionRows(data.geographies, "geo");
      document.getElementById("distribution-classes").innerHTML = distributionRows(data.asset_classes, "asset_class");
      document.getElementById("distribution-missing").innerHTML = data.missing && data.missing.length
        ? data.missing.map(row => {
            const symbol = window.assetToSymbolMap ? window.assetToSymbolMap[row.asset] : '';
            const logoUrl = row.isin ? `https://assets.parqet.com/logos/isin/${row.isin}?format=png` : (symbol ? `https://assets.parqet.com/logos/symbol/${symbol}?format=png` : '');
            const logoImg = logoUrl ? `<img src="${logoUrl}" onerror="if(this.src.indexOf('/isin/') !== -1 && '${symbol}') { this.src = 'https://assets.parqet.com/logos/symbol/${symbol}?format=png'; } else { this.style.display='none'; }" class="sym-logo">` : '';
            return `
              <tr>
                <td class="cell-flex">${logoImg}<span>${row.asset}</span>${badgeHtml(window.assetToTypeMap ? window.assetToTypeMap[row.asset] : '')}</td>
                <td>${row.isin || ""}</td>
                <td>${money(row.market_value_eur)}</td>
                <td>${sourceStatusLabel(row)}</td>
              </tr>
            `;
          }).join("")
        : `<tr><td colspan="4" class="empty-state">All open assets have distribution rows.</td></tr>`;
    }
    window.activeNewsFilter = null;
    window.currentNewsData = null;

    function symbolLogoHtml(symbol) {
      if (!symbol) return '';
      const upperSymbol = symbol.toUpperCase();
      const isin = window.symbolToIsinMap ? window.symbolToIsinMap[upperSymbol] : '';
      const logoUrl = isin ? `https://assets.parqet.com/logos/isin/${isin}?format=png` : `https://assets.parqet.com/logos/symbol/${upperSymbol}?format=png`;
      return `<img src="${logoUrl}" onerror="if(this.src.indexOf('/isin/') !== -1) { this.src = 'https://assets.parqet.com/logos/symbol/${upperSymbol}?format=png'; } else { this.style.display='none'; }" style="width: 14px; height: 14px; border-radius: 50%; vertical-align: middle; margin-right: 5px; background: var(--tint-strong); flex-shrink: 0;">`;
    }

    function toggleNewsFilter(symbol) {
      if (!symbol) return;
      const upperSymbol = symbol.toUpperCase();
      if (window.activeNewsFilter === upperSymbol) {
        window.activeNewsFilter = null;
      } else {
        window.activeNewsFilter = upperSymbol;
      }
      if (window.currentNewsData) {
        renderNews(window.currentNewsData);
      }
    }

    function renderNews(news) {
      window.currentNewsData = news || {};
      const data = window.currentNewsData;
      const symbols = data.symbols || [];
      
      let itemsToRender = data.items || [];
      if (window.activeNewsFilter) {
        itemsToRender = itemsToRender.filter(item => (item.symbol || '').toUpperCase() === window.activeNewsFilter);
      }
      
      document.getElementById("news-summary").innerHTML = data.status === "available"
        ? `${itemsToRender.length}/${data.count || 0} headlines | ${symbols.length} tickers${window.activeNewsFilter ? ` | filter: <span style="color:var(--accent); font-weight:bold; cursor:pointer; text-decoration:underline;" onclick="toggleNewsFilter('${escapeHtml(window.activeNewsFilter)}')">${escapeHtml(window.activeNewsFilter)} (clear)</span>` : ''}`
        : `No headlines available | ${symbols.length} tickers`;
        
      document.getElementById("news-symbols").innerHTML = symbols.length
        ? symbols.map(symbol => {
            const upperSymbol = symbol.toUpperCase();
            const activeClass = (window.activeNewsFilter === upperSymbol) ? 'active' : '';
            return `<span class="source-pill ${activeClass}" class="is-clickable" onclick="toggleNewsFilter('${escapeHtml(symbol)}')">${symbolLogoHtml(symbol)}${escapeHtml(symbol)}</span>`;
          }).join("")
        : `<span class="empty-state">No stock tickers detected from current holdings.</span>`;
        
      document.getElementById("news-list").innerHTML = itemsToRender.length
        ? itemsToRender.map(item => {
            const upperSymbol = (item.symbol || '').toUpperCase();
            const cardActive = (window.activeNewsFilter === upperSymbol) ? 'active' : '';
            return `
              <article class="news-card">
                <div class="news-meta">
                  <span class="source-pill ${cardActive}" class="is-clickable" onclick="toggleNewsFilter('${escapeHtml(item.symbol || '')}')">${symbolLogoHtml(item.symbol)}${escapeHtml(item.symbol || "")}</span>
                  <span>${escapeHtml(item.source || "")}</span>
                  <span>${escapeHtml(item.published || "")}</span>
                </div>
                <a href="${escapeHtml(item.link || "#")}" target="_blank" rel="noopener noreferrer">${escapeHtml(item.title || "")}</a>
              </article>
            `;
          }).join("")
        : `<div class="empty-state">No stock news available${window.activeNewsFilter ? ` for ticker ${window.activeNewsFilter}` : ''}.</div>`;
    }

    // ─── Watchlist JS Rendering ───
    function renderWatchlistCard(item) {
      if (item.error) {
        return `
          <div class="glass-card" style="padding: 15px; display: flex; flex-direction: column; justify-content: space-between; position: relative;">
            <div>
              <div style="display: flex; justify-content: space-between; align-items: start;">
                <h4 style="color: var(--negative); font-size: 14px; margin-bottom: 4px;">${escapeHtml(item.ticker)}</h4>
                <button type="button" class="watchlist-remove-btn" data-ticker="${escapeHtml(item.ticker)}" style="
                  background: color-mix(in srgb, var(--negative) 10%, transparent);
                  border: 1px solid color-mix(in srgb, var(--negative) 20%, transparent);
                  color: var(--negative);
                  border-radius: 50%;
                  width: 24px;
                  height: 24px;
                  display: flex;
                  align-items: center;
                  justify-content: center;
                  cursor: pointer;
                  font-size: 14px;
                  font-weight: bold;
                  transition: all 0.2s ease;
                " title="Remove from Watchlist">−</button>
              </div>
              <p style="font-size: 11px; color: var(--text-muted);">${escapeHtml(item.error)}</p>
            </div>
          </div>
        `;
      }

      const sign = item.change >= 0 ? "+" : "";
      const changeColor = item.change >= 0 ? "var(--positive)" : "var(--negative)";
      const priceText = `${item.price.toFixed(2)} ${item.currency}`;
      const changeText = `${sign}${item.change.toFixed(2)} (${sign}${item.change_pct.toFixed(2)}%)`;

      return `
        <div class="glass-card" style="
          padding: 15px; 
          display: flex; 
          flex-direction: column; 
          justify-content: space-between; 
          border-radius: var(--radius-md);
          position: relative;
          transition: transform 0.2s ease, box-shadow 0.2s ease;
        " onmouseover="this.style.transform='translateY(-2px)';" onmouseout="this.style.transform='translateY(0)';">
          <div>
            <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 6px;">
              <span style="font-weight: 700; font-size: 14px; color: var(--text-primary);">${escapeHtml(item.ticker)}</span>
              <button type="button" class="watchlist-remove-btn" data-ticker="${escapeHtml(item.ticker)}" style="
                background: color-mix(in srgb, var(--negative) 10%, transparent);
                border: 1px solid color-mix(in srgb, var(--negative) 20%, transparent);
                color: var(--negative);
                border-radius: 50%;
                width: 24px;
                height: 24px;
                display: flex;
                align-items: center;
                justify-content: center;
                cursor: pointer;
                font-size: 14px;
                font-weight: bold;
                transition: all 0.2s ease;
              " title="Remove from Watchlist">−</button>
            </div>
            <h4 style="
              font-size: 12px; 
              color: var(--text-muted); 
              font-weight: 500;
              margin-bottom: 12px;
              white-space: nowrap;
              overflow: hidden;
              text-overflow: ellipsis;
            " title="${escapeHtml(item.name)}">${escapeHtml(item.name)}</h4>
          </div>
          
          <div style="display: flex; justify-content: space-between; align-items: end; margin-top: auto;">
            <div>
              <div style="font-size: 18px; font-weight: 700; color: var(--text-primary); margin-bottom: 2px;">${priceText}</div>
              <div style="font-size: 12px; font-weight: 600; color: ${changeColor};">${changeText}</div>
            </div>
            
            <div style="display: flex; gap: 8px;">
              <a href="${escapeHtml(item.justetf_url)}" target="_blank" style="
                font-size: 11px;
                font-weight: 600;
                color: var(--series-cyan);
                background: color-mix(in srgb, var(--series-cyan) 10%, transparent);
                border: 1px solid color-mix(in srgb, var(--series-cyan) 20%, transparent);
                border-radius: 6px;
                padding: 4px 8px;
                text-decoration: none;
                transition: all 0.2s ease;
              " onmouseover="this.style.background='color-mix(in srgb, var(--series-cyan) 20%, transparent)';" onmouseout="this.style.background='color-mix(in srgb, var(--series-cyan) 10%, transparent)';">JustETF</a>
              <a href="${escapeHtml(item.yfinance_url)}" target="_blank" style="
                font-size: 11px;
                font-weight: 600;
                color: var(--warning);
                background: color-mix(in srgb, var(--warning) 10%, transparent);
                border: 1px solid color-mix(in srgb, var(--warning) 20%, transparent);
                border-radius: 6px;
                padding: 4px 8px;
                text-decoration: none;
                transition: all 0.2s ease;
              " onmouseover="this.style.background='color-mix(in srgb, var(--warning) 20%, transparent)';" onmouseout="this.style.background='color-mix(in srgb, var(--warning) 10%, transparent)';">Yahoo</a>
            </div>
          </div>
        </div>
      `;
    }

    function renderWatchlist(list) {
      const summary = document.getElementById("watchlist-summary");
      if (summary) {
        summary.textContent = `${list.length} item${list.length !== 1 ? "s" : ""} watched`;
      }
      
      const grid = document.getElementById("watchlist-grid");
      if (!grid) return;
      
      if (!list.length) {
        grid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: var(--text-muted); padding: 30px; border: 1px dashed var(--border); border-radius: var(--radius-md); font-size: 13px;">Watchlist is empty. Enter a ticker to start tracking.</div>`;
        return;
      }
      
      grid.innerHTML = list.map(item => renderWatchlistCard(item)).join("");
      
      grid.querySelectorAll(".watchlist-remove-btn").forEach(btn => {
        btn.addEventListener("click", async () => {
          const ticker = btn.dataset.ticker;
          if (!ticker) return;
          btn.disabled = true;
          btn.textContent = "…";
          try {
            const res = await fetch("/api/watchlist", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ ticker: ticker, action: "remove" })
            });
            const rData = await res.json();
            if (!res.ok) throw new Error(rData.error || "Failed to remove ticker.");
            renderWatchlist(rData.watchlist || []);
          } catch (err) {
            alert(err.message);
            btn.disabled = false;
            btn.textContent = "−";
          }
        });
      });
    }

    async function loadWatchlist(refresh = false) {
      const summary = document.getElementById("watchlist-summary");
      if (summary) summary.textContent = "Loading watchlist…";
      try {
        const response = await fetch(`/api/watchlist${refresh ? "?refresh=true" : ""}`);
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Failed to load watchlist.");
        renderWatchlist(data.watchlist || []);
      } catch (err) {
        console.error("Watchlist error:", err);
        const grid = document.getElementById("watchlist-grid");
        if (grid) grid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: var(--negative); padding: 20px;">Error: ${escapeHtml(err.message)}</div>`;
        if (summary) summary.textContent = "Error loading watchlist";
      }
    }

    async function loadNews(refresh = false, symbols = []) {
      window.activeNewsFilter = null; // Clear active news filter on reloading news
      const summary = document.getElementById("news-summary");
      const list = document.getElementById("news-list");
      summary.textContent = "Loading feeds…";
      try {
        const params = currentQueryParams();
        if (refresh) params.set("refresh", "1");
        if (Array.isArray(symbols) && symbols.length) params.set("symbols", symbols.join(","));
        const response = await fetch(`/api/news?${params.toString()}`);
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "News request failed.");
        renderNews(data);
      } catch (err) {
        summary.textContent = "News unavailable";
        list.innerHTML = `<div class="empty-state">${escapeHtml(err.message)}</div>`;
      }
    }
    function currentQueryParams() {
      return new URLSearchParams({
        person: selectedPerson,
        berkshire: selectedBerkshireMode,
        proxy: selectedProxyMode,
        broker: selectedBroker,
        live_only: selectedLiveMode === "live" ? "on" : "off"
      });
    }
    function updateExportSummary() {
      const summary = document.getElementById("export-summary");
      if (!summary) return;
      const person = selectedPerson.charAt(0).toUpperCase() + selectedPerson.slice(1);
      const broker = selectedBroker === "all" ? "all brokers" : selectedBroker;
      const live = selectedLiveMode === "live" ? "live assets only" : "all assets";
      summary.textContent = `${person} | ${selectedWindowLabel()} | ${broker} | ${selectedBerkshireMode === "lookthrough" ? "BRK 13F" : "BRK stock"} | ${selectedProxyMode === "on" ? "proxy gaps" : "official only"} | ${live}`;
    }
    function exportDashboard() {
      const formatEl = document.getElementById("export-format");
      const format = formatEl ? formatEl.value : "pdf";
      const params = currentQueryParams();
      params.set("period", selectedPeriod);
      params.set("format", format);
      window.location.href = `/api/export?${params.toString()}`;
    }
    function renderDividends(dividends) {
      document.getElementById("dividends-summary").textContent = `${dividends.count} payments | ${money(dividends.total_eur)} net | ${money(dividends.tax_eur)} tax | ${money(dividends.gross_eur)} gross`;
      
      const agg = {};
      (dividends.rows || []).forEach(row => {
        if (!agg[row.asset]) agg[row.asset] = { asset: row.asset, isin: row.isin || "", count: 0, amount: 0, tax: 0, gross: 0 };
        agg[row.asset].count++;
        agg[row.asset].amount += row.amount_eur;
        agg[row.asset].tax += row.tax_eur;
        agg[row.asset].gross += row.gross_eur;
      });
      const sortedAgg = Object.values(agg).sort((a, b) => b.amount - a.amount);
      
      document.getElementById("dividends-aggregate").innerHTML = sortedAgg.map(r => {
        const symbol = window.assetToSymbolMap ? window.assetToSymbolMap[r.asset] : '';
        const logoUrl = r.isin ? `https://assets.parqet.com/logos/isin/${r.isin}?format=png` : (symbol ? `https://assets.parqet.com/logos/symbol/${symbol}?format=png` : '');
        const logoImg = logoUrl ? `<img src="${logoUrl}" onerror="if(this.src.indexOf('/isin/') !== -1 && '${symbol}') { this.src = 'https://assets.parqet.com/logos/symbol/${symbol}?format=png'; } else { this.style.display='none'; }" class="sym-logo">` : '';
        return `
          <tr>
            <td class="cell-flex">${logoImg}<span>${r.asset}</span>${badgeHtml(window.assetToTypeMap ? window.assetToTypeMap[r.asset] : '')}</td>
            <td>${r.isin}</td>
            <td>${r.count}</td>
            <td>${money(r.amount)}</td>
            <td>${money(r.tax)}</td>
            <td>${money(r.gross)}</td>
          </tr>
        `;
      }).join("");

      // Calculate Yearly Dividend Summary
      const yearlyData = {};
      
      // Sum dividends by year
      (dividends.rows || []).forEach(row => {
        const year = new Date(row.date).getFullYear();
        if (Number.isNaN(year)) return;
        if (!yearlyData[year]) {
          yearlyData[year] = { year: year, total_net: 0, market_values: [], net_contribs: [] };
        }
        yearlyData[year].total_net += row.amount_eur;
      });
      
      // Group valuation series points by year to calculate averages
      const valueSeries = (dashboardData && dashboardData.valuation_series) || [];
      valueSeries.forEach(pt => {
        const year = new Date(pt.date).getFullYear();
        if (Number.isNaN(year)) return;
        if (!yearlyData[year]) {
          yearlyData[year] = { year: year, total_net: 0, market_values: [], net_contribs: [] };
        }
        const isTotal = (selectedReturnMode === "total");
        yearlyData[year].market_values.push(Number(isTotal ? pt.total_market_value : pt.market_value || 0));
        yearlyData[year].net_contribs.push(Number(isTotal ? pt.total_net_contributions : pt.net_contributions || 0));
      });
      
      const yearlyRows = Object.values(yearlyData).sort((a, b) => b.year - a.year);
      
      document.getElementById("dividends-yearly").innerHTML = yearlyRows.map(y => {
        const avgMarket = y.market_values.length 
          ? (y.market_values.reduce((sum, val) => sum + val, 0) / y.market_values.length)
          : 0;
        const avgContrib = y.net_contribs.length 
          ? (y.net_contribs.reduce((sum, val) => sum + val, 0) / y.net_contribs.length)
          : 0;
          
        const divYield = avgMarket > 0 ? (y.total_net / avgMarket * 100) : 0;
        const yieldOnCost = avgContrib > 0 ? (y.total_net / avgContrib * 100) : 0;
        
        return `
          <tr>
            <td>${y.year}</td>
            <td>${money(y.total_net)}</td>
            <td>${avgMarket > 0 ? money(avgMarket) : "-"}</td>
            <td class="positive fw-600">${avgMarket > 0 ? `${pct.format(divYield)}%` : "-"}</td>
            <td>${avgContrib > 0 ? money(avgContrib) : "-"}</td>
            <td class="positive fw-600">${avgContrib > 0 ? `${pct.format(yieldOnCost)}%` : "-"}</td>
          </tr>
        `;
      }).join("");

      document.getElementById("dividends").innerHTML = (dividends.rows || []).map(row => {
        const symbol = window.assetToSymbolMap ? window.assetToSymbolMap[row.asset] : '';
        const logoUrl = row.isin ? `https://assets.parqet.com/logos/isin/${row.isin}?format=png` : (symbol ? `https://assets.parqet.com/logos/symbol/${symbol}?format=png` : '');
        const logoImg = logoUrl ? `<img src="${logoUrl}" onerror="if(this.src.indexOf('/isin/') !== -1 && '${symbol}') { this.src = 'https://assets.parqet.com/logos/symbol/${symbol}?format=png'; } else { this.style.display='none'; }" class="sym-logo">` : '';
        return `
          <tr>
            <td>${row.date}</td>
            <td>${row.broker}</td>
            <td class="cell-flex">${logoImg}<span>${row.asset}</span>${badgeHtml(window.assetToTypeMap ? window.assetToTypeMap[row.asset] : '')}</td>
            <td>${row.isin || ""}</td>
            <td>${money(row.amount_eur)}</td>
            <td>${money(row.tax_eur)}</td>
            <td>${money(row.gross_eur)}</td>
          </tr>
        `;
      }).join("");
    }
    function renderCashInterests(data) {
      const info = data || { summary: { total_net_eur: 0.0, total_tax_eur: 0.0, total_gross_eur: 0.0, payments_count: 0 }, by_broker: [], payments: [] };
      
      document.getElementById("cash-interest-summary").textContent = 
        `${info.summary.payments_count} payments | ${money(info.summary.total_net_eur)} net`;
        
      // Render summary by broker
      document.getElementById("cash-interest-broker").innerHTML = info.by_broker && info.by_broker.length
        ? info.by_broker.map(row => `
            <tr>
              <td class="ta-l fw-500">${escapeHtml(row.broker)}</td>
              <td>${row.payments_count}</td>
              <td class="positive fw-600">${money(row.net_eur)}</td>
              <td class="negative">${money(row.tax_eur)}</td>
              <td>${money(row.gross_eur)}</td>
            </tr>
          `).join("")
        : `<tr><td colspan="5" class="empty-state">No cash interest summary available.</td></tr>`;
        
      // Render all payments
      document.getElementById("cash-interest-payments").innerHTML = info.payments && info.payments.length
        ? info.payments.map(row => `
            <tr>
              <td>${row.date}</td>
              <td class="ta-l fw-500">${escapeHtml(row.broker)}</td>
              <td class="positive fw-600">${money(row.net_eur)}</td>
              <td class="negative">${money(row.tax_eur)}</td>
              <td>${money(row.gross_eur)}</td>
              <td style="text-align: left; color: var(--text-muted); font-size: 0.9em;">${escapeHtml(row.description)}</td>
            </tr>
          `).join("")
        : `<tr><td colspan="6" class="empty-state">No interest payments recorded.</td></tr>`;
    }
    function expenseKind(row) {
      const flow = String(row.flow_kind || "");
      const category = String(row.category || "");
      if (flow === "income" || category === "Income") return "income";
      if (flow === "credit" || category === "Credits") return "credits";
      if (flow === "investment" || category === "Investments") return "investments";
      if (flow === "personal_transfer" || category === "Personal Transfers") return "transfers";
      return "spend";
    }
    function summarizeExpenseRows(rows) {
      const categoryMap = {};
      const sourceMap = {};
      const merchantMap = {};
      const monthMap = {};
      let spend = 0;
      let income = 0;
      let transfers = 0;
      let investments = 0;
      let credits = 0;
      const creditRows = [];

      (rows || []).forEach(row => {
        const amount = Number(row.amount_eur || 0);
        if (!Number.isFinite(amount) || amount === 0) return;
        const kind = expenseKind(row);
        if (kind === "income") income += amount;
        else if (kind === "credits") {
          credits += amount;
          creditRows.push(row);
        }
        else if (kind === "investments") investments += amount;
        else if (kind === "transfers") transfers += amount;
        else spend += amount;

        const category = row.category || "Uncategorized";
        categoryMap[category] ||= { category, amount: 0, count: 0 };
        categoryMap[category].amount += amount;
        categoryMap[category].count += 1;

        const source = row.source_label || row.source || "Source";
        sourceMap[source] ||= { source, spend: 0, income: 0, transfers: 0, investments: 0, credits: 0, count: 0 };
        sourceMap[source][kind] += amount;
        sourceMap[source].count += 1;

        const month = String(row.date || "").slice(0, 7);
        if (month) {
          monthMap[month] ||= { month, spend: 0, income: 0, transfers: 0, investments: 0, credits: 0, count: 0 };
          monthMap[month][kind] += amount;
          monthMap[month].count += 1;
        }

        if (kind !== "income" && kind !== "credits") {
          const merchant = row.merchant || "Unknown";
          merchantMap[merchant] ||= { merchant, category, amount: 0, count: 0 };
          merchantMap[merchant].amount += amount;
          merchantMap[merchant].count += 1;
        }
      });

      const totalOutflow = spend + investments;
      const netOutflow = totalOutflow - income;
      const categories = Object.values(categoryMap)
        .filter(row => row.category !== "Income" && row.category !== "Credits" && row.category !== "Personal Transfers")
        .map(row => ({ ...row, share: totalOutflow > 0 ? row.amount / totalOutflow * 100 : null }))
        .sort((a, b) => b.amount - a.amount);
      const sources = Object.values(sourceMap)
        .map(row => ({
          ...row,
          outflow: row.spend + row.investments,
          net: row.spend + row.investments - row.income
        }))
        .sort((a, b) => Math.abs(b.net) - Math.abs(a.net));
      const months = Object.values(monthMap)
        .map(row => ({
          ...row,
          outflow: row.spend + row.investments,
          net: row.spend + row.investments - row.income
        }))
        .sort((a, b) => String(a.month).localeCompare(String(b.month)));
      const merchants = Object.values(merchantMap).sort((a, b) => b.amount - a.amount);

      return {
        spend,
        income,
        transfers,
        investments,
        credits,
        totalOutflow,
        netOutflow,
        rows: rows || [],
        creditRows: creditRows.sort((a, b) => String(b.date || "").localeCompare(String(a.date || ""))),
        categories,
        sources,
        months,
        merchants
      };
    }
    function periodExpenses(data) {
      const source = (data && data.expenses) || { status: "empty", rows: [], message: "" };
      const start = periodStartDate(data || {});
      const rows = (source.rows || []).filter(row => !start || new Date(row.date) >= start);
      return {
        ...source,
        ...summarizeExpenseRows(rows),
        rows
      };
    }
    function renderExpenseTrend(months) {
      const svg = document.getElementById("expense-trend");
      if (!svg) return;

      const legend = document.getElementById("expense-trend-legend");
      if (legend) {
        if (selectedExpenseTrendMode === "cumulative") {
          legend.innerHTML = `
            <span class="inline-legend">
              <i class="legend-dot legend-dot--accent"></i>
              Cumulative Outflow
            </span>
            <span class="inline-legend">
              <i class="legend-dot legend-dot--positive"></i>
              Cumulative Income
            </span>
            <span class="inline-legend">
              <i class="legend-dot legend-dot--warning"></i>
              Cumulative Net Outflow
            </span>
          `;
        } else {
          legend.innerHTML = `
            <span class="inline-legend">
              <i class="legend-dot legend-dot--accent"></i>
              Outflow
            </span>
            <span class="inline-legend">
              <i class="legend-dot legend-dot--positive"></i>
              Income
            </span>
          `;
        }
      }

      const width = 560;
      const height = 230;
      const margin = { top: 18, right: 16, bottom: 34, left: 46 };
      const rows = months || [];
      svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
      svg.setAttribute("preserveAspectRatio", "none");
      if (!rows.length) {
        svg.innerHTML = `<text x="${width / 2}" y="${height / 2}" text-anchor="middle" class="expense-label">No monthly expense rows in this window</text>`;
        return;
      }
      const plotW = width - margin.left - margin.right;
      const plotH = height - margin.top - margin.bottom;

      function getMonthYearLabel(monthStr) {
        const parts = monthStr.split("-");
        const yearShort = parts[0].slice(2);
        const monthNum = parts[1];
        const monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
        return `${monthNames[parseInt(monthNum, 10) - 1]} '${yearShort}`;
      }

      if (selectedExpenseTrendMode === "cumulative") {
        let runningOutflow = 0;
        let runningIncome = 0;
        let runningNet = 0;
        const cumulativeRows = rows.map(row => {
          runningOutflow += Number(row.outflow || 0);
          runningIncome += Number(row.income || 0);
          runningNet += Number(row.net || 0);
          return {
            month: row.month,
            outflow: runningOutflow,
            income: runningIncome,
            net: runningNet
          };
        });

        const maxVal = Math.max(1, ...cumulativeRows.flatMap(row => [row.outflow, row.income, Math.abs(row.net)]));
        const minVal = Math.min(0, ...cumulativeRows.flatMap(row => [row.outflow, row.income, row.net]));
        const yRange = maxVal - minVal;
        const yScale = v => margin.top + plotH - ((Number(v || 0) - minVal) / Math.max(1, yRange)) * plotH;
        const xScale = index => margin.left + (plotW / Math.max(1, cumulativeRows.length - 1)) * index;

        let gridLines = "";
        const tickCount = 4;
        for (let i = 0; i <= tickCount; i++) {
          const t = i / tickCount;
          const val = minVal + t * yRange;
          const y = yScale(val);
          gridLines += `
            <line class="expense-grid-line" x1="${margin.left}" y1="${y.toFixed(2)}" x2="${width - margin.right}" y2="${y.toFixed(2)}"></line>
            <text class="expense-label" x="${margin.left - 6}" y="${(y + 4).toFixed(2)}" text-anchor="end">${smartTickFormat(val)}</text>
          `;
        }

        let outflowPath = "";
        let incomePath = "";
        let netPath = "";

        cumulativeRows.forEach((row, index) => {
          const x = xScale(index).toFixed(2);
          const yOut = yScale(row.outflow).toFixed(2);
          const yInc = yScale(row.income).toFixed(2);
          const yNet = yScale(row.net).toFixed(2);

          outflowPath += `${index ? "L" : "M"}${x} ${yOut}`;
          incomePath += `${index ? "L" : "M"}${x} ${yInc}`;
          netPath += `${index ? "L" : "M"}${x} ${yNet}`;
        });

        const outflowLine = `<path class="expense-line spend" d="${outflowPath}" fill="none" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"></path>`;
        const incomeLine = `<path class="expense-line income" d="${incomePath}" fill="none" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"></path>`;
        const netLine = `<path class="expense-line net" d="${netPath}" fill="none" stroke-width="2" stroke-dasharray="3,3" stroke-linecap="round" stroke-linejoin="round"></path>`;

        const dotsAndLabels = cumulativeRows.map((row, index) => {
          const x = xScale(index);
          const yOut = yScale(row.outflow);
          const yInc = yScale(row.income);
          const yNet = yScale(row.net);
          const label = getMonthYearLabel(row.month);

          const labelStep = cumulativeRows.length > 12 ? Math.ceil(cumulativeRows.length / 8) : 1;
          const showLabel = (index % labelStep === 0) || (index === cumulativeRows.length - 1);

          return `
            <circle cx="${x.toFixed(2)}" cy="${yOut.toFixed(2)}" r="4" class="point point--accent" stroke-width="1.5">
              <title>${row.month} cumulative outflow: ${money(row.outflow)}</title>
            </circle>
            <circle cx="${x.toFixed(2)}" cy="${yInc.toFixed(2)}" r="4" class="point point--positive" stroke-width="1.5">
              <title>${row.month} cumulative income: ${money(row.income)}</title>
            </circle>
            <circle cx="${x.toFixed(2)}" cy="${yNet.toFixed(2)}" r="4" class="point point--warning" stroke-width="1.5">
              <title>${row.month} cumulative net: ${money(row.net)}</title>
            </circle>
            ${showLabel ? `<text class="expense-label" x="${x.toFixed(2)}" y="${height - 10}" text-anchor="middle">${escapeHtml(label)}</text>` : ""}
          `;
        }).join("");

        svg.innerHTML = `
          ${gridLines}
          ${outflowLine}
          ${incomeLine}
          ${netLine}
          ${dotsAndLabels}
        `;
      } else {
        const maxValue = Math.max(1, ...rows.flatMap(row => [row.outflow || 0, row.income || 0, Math.abs(row.net || 0)]));
        const yFor = value => margin.top + plotH - (Number(value || 0) / maxValue) * plotH;
        const groupW = plotW / rows.length;
        const barW = Math.max(5, Math.min(18, groupW * 0.24));
        const grid = [0.25, 0.5, 0.75, 1].map(step => {
          const y = margin.top + plotH - plotH * step;
          return `<line class="expense-grid-line" x1="${margin.left}" y1="${y.toFixed(2)}" x2="${width - margin.right}" y2="${y.toFixed(2)}"></line>`;
        }).join("");
        const bars = rows.map((row, index) => {
          const center = margin.left + groupW * index + groupW / 2;
          const spendY = yFor(row.outflow);
          const incomeY = yFor(row.income);
          const spendH = margin.top + plotH - spendY;
          const incomeH = margin.top + plotH - incomeY;
          const label = getMonthYearLabel(row.month);

          const labelStep = rows.length > 12 ? Math.ceil(rows.length / 8) : 1;
          const showLabel = (index % labelStep === 0) || (index === rows.length - 1);

          return `
            <rect class="expense-bar spend" x="${(center - barW - 2).toFixed(2)}" y="${spendY.toFixed(2)}" width="${barW.toFixed(2)}" height="${Math.max(0, spendH).toFixed(2)}" rx="3"><title>${row.month} outflow ${money(row.outflow)} | net ${money(row.net)}</title></rect>
            <rect class="expense-bar income" x="${(center + 2).toFixed(2)}" y="${incomeY.toFixed(2)}" width="${barW.toFixed(2)}" height="${Math.max(0, incomeH).toFixed(2)}" rx="3"><title>${row.month} income ${money(row.income)}</title></rect>
            ${showLabel ? `<text class="expense-label" x="${center.toFixed(2)}" y="${height - 10}" text-anchor="middle">${escapeHtml(label)}</text>` : ""}
          `;
        }).join("");
        svg.innerHTML = `
          ${grid}
          <line class="expense-axis" x1="${margin.left}" y1="${margin.top + plotH}" x2="${width - margin.right}" y2="${margin.top + plotH}"></line>
          <text class="expense-label" x="${margin.left - 6}" y="${margin.top + 4}" text-anchor="end">${smartTickFormat(maxValue)}</text>
          <text class="expense-label" x="${margin.left - 6}" y="${margin.top + plotH}" text-anchor="end">0</text>
          ${bars}
        `;
      }
    }
    function renderExpenses(data) {
      const expenses = periodExpenses(data);
      const unavailable = (expenses.status === "empty" || expenses.status === "unavailable") && !expenses.rows.length;
      const message = expenses.message || "No classified expense rows are available for this window.";

      window.currentExpenseRows = expenses.rows || [];

      document.getElementById("expenses-summary").textContent = unavailable
        ? "No rows"
        : `${selectedWindowLabel()} | ${money(expenses.netOutflow)} net outflow | ${expenses.rows.length} rows`;
      document.getElementById("expense-metrics").innerHTML = unavailable ? `<div class="empty-state">${escapeHtml(message)}</div>` : `
        <div class="expense-item"><span>Spend</span><strong class="negative">${money(expenses.spend)}</strong></div>
        <div class="expense-item"><span>Transfers</span><strong class="negative">${money(expenses.transfers)}</strong></div>
        <div class="expense-item"><span>Investments</span><strong class="negative">${money(expenses.investments)}</strong></div>
        <div class="expense-item"><span>Credits</span><strong>${money(expenses.credits)}</strong></div>
        <div class="expense-item"><span>Income</span><strong class="positive">${money(expenses.income)}</strong></div>
        <div class="expense-item"><span>Net outflow</span><strong class="${signedClass(-expenses.netOutflow)}">${money(expenses.netOutflow)}</strong></div>
      `;
      document.getElementById("expense-categories").innerHTML = !expenses.categories.length
        ? `<tr><td colspan="4" class="empty-state">${escapeHtml(message)}</td></tr>`
        : expenses.categories.slice(0, 12).map(row => `
          <tr style="cursor: pointer;" onclick="toggleCategorySubcategories(this, '${escapeHtml(row.category)}')">
            <td class="cell-flex">
              <svg class="category-chevron" style="width: 10px; height: 10px; margin-right: 6px; transition: transform 0.2s; fill: var(--text-secondary); flex-shrink: 0;" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M7.21 14.77a.75.75 0 01.02-1.06L11.168 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z" clip-rule="evenodd"/></svg>
              <span>${escapeHtml(row.category)}</span>
            </td>
            <td>${row.count}</td>
            <td>${money(row.amount)}</td>
            <td>${row.share === null ? "-" : percent(row.share)}</td>
          </tr>
        `).join("");
      document.getElementById("expense-sources").innerHTML = !expenses.sources.length
        ? `<tr><td colspan="6" class="empty-state">${escapeHtml(message)}</td></tr>`
        : expenses.sources.map(row => `
          <tr>
            <td>${escapeHtml(row.source)}</td>
            <td>${row.count}</td>
            <td>${money(row.outflow)}</td>
            <td class="positive">${money(row.income)}</td>
            <td>${money(row.credits)}</td>
            <td class="${signedClass(-row.net)}">${money(row.net)}</td>
          </tr>
        `).join("");
      document.getElementById("expense-credits").innerHTML = !expenses.creditRows.length
        ? `<tr><td colspan="5" class="empty-state">No credit rows in this window.</td></tr>`
        : expenses.creditRows.slice(0, 20).map(row => `
          <tr>
            <td>${escapeHtml(row.date || "")}</td>
            <td>${escapeHtml(row.source_label || row.source || "")}</td>
            <td>${escapeHtml(row.subcategory || "")}</td>
            <td>${escapeHtml(row.merchant || "")}</td>
            <td>${money(row.amount_eur || 0)}</td>
          </tr>
        `).join("");
      document.getElementById("expense-merchants").innerHTML = !expenses.merchants.length
        ? `<tr><td colspan="4" class="empty-state">${escapeHtml(message)}</td></tr>`
        : expenses.merchants.slice(0, 15).map(row => `
          <tr>
            <td>${escapeHtml(row.merchant)}</td>
            <td>${escapeHtml(row.category)}</td>
            <td>${row.count}</td>
            <td>${money(row.amount)}</td>
          </tr>
        `).join("");
      document.getElementById("expense-rows").innerHTML = !expenses.rows.length
        ? `<tr><td colspan="6" class="empty-state">${escapeHtml(message)}</td></tr>`
        : expenses.rows.slice(0, 30).map(row => {
          const kind = expenseKind(row);
          const signedAmount = kind === "income" ? Number(row.amount_eur || 0) : (kind === "credits" ? Number(row.amount_eur || 0) : -Number(row.amount_eur || 0));
          return `
            <tr>
              <td>${escapeHtml(row.date)}</td>
              <td>${escapeHtml(row.source_label || row.source || "")}</td>
              <td>${escapeHtml(row.category || "")}</td>
              <td>${escapeHtml(row.merchant || "")}</td>
              <td style="text-align: left; color: var(--text-muted); max-width: 340px; overflow: hidden; text-overflow: ellipsis;">${escapeHtml(row.description || "")}</td>
              <td class="${signedClass(signedAmount)}">${money(signedAmount)}</td>
            </tr>
          `;
        }).join("");
      renderExpenseTrend(expenses.months);
    }
    window.toggleCategorySubcategories = function(rowElement, categoryName) {
      const nextRow = rowElement.nextElementSibling;
      if (nextRow && nextRow.classList.contains("subcategory-breakdown-row")) {
        nextRow.remove();
        const chevron = rowElement.querySelector(".category-chevron");
        if (chevron) chevron.style.transform = "rotate(0deg)";
        return;
      }
      
      // Remove any other expanded subcategory rows to keep UI clean
      document.querySelectorAll(".subcategory-breakdown-row").forEach(el => el.remove());
      document.querySelectorAll(".category-chevron").forEach(el => el.style.transform = "rotate(0deg)");
      
      const allRows = window.currentExpenseRows || [];
      const catRows = allRows.filter(row => (row.category || "Uncategorized") === categoryName);
      
      const subcatMap = {};
      let totalAmount = 0;
      catRows.forEach(row => {
        const subcat = (row.subcategory || "").trim() || "Unspecified";
        const amount = Number(row.amount_eur || 0);
        subcatMap[subcat] ||= { subcategory: subcat, amount: 0, count: 0 };
        subcatMap[subcat].amount += amount;
        subcatMap[subcat].count += 1;
        totalAmount += amount;
      });
      
      const subcategories = Object.values(subcatMap).sort((a, b) => b.amount - a.amount);
      
      const subtableHtml = `
        <tr class="subcategory-breakdown-row" style="background: var(--tint-faint);">
          <td colspan="4" style="padding: 12px 16px 16px 28px; border-bottom: 1px solid var(--border);">
            <div style="border-left: 2px solid var(--positive); padding-left: 12px; margin-top: 4px;">
              <h4 style="font-size: 11px; font-weight: 600; text-transform: uppercase; color: var(--text-secondary); margin-bottom: 8px; letter-spacing: 0.05em; text-align: left;">Subcategories for ${escapeHtml(categoryName)}</h4>
              <table style="width: 100%; font-size: 12px; border-collapse: collapse;">
                <thead>
                  <tr style="border-bottom: 1px solid var(--tint-hover); color: var(--text-secondary); font-weight: 500;">
                    <th style="text-align: left; padding: 4px 8px;">Subcategory</th>
                    <th style="text-align: right; padding: 4px 8px; width: 60px;">Rows</th>
                    <th style="text-align: right; padding: 4px 8px; width: 100px;">Amount</th>
                    <th style="text-align: right; padding: 4px 8px; width: 80px;">Share</th>
                  </tr>
                </thead>
                <tbody>
                  ${subcategories.map(sub => {
                    const pctShare = totalAmount > 0 ? (sub.amount / totalAmount * 100).toFixed(1) : "0.0";
                    return `
                      <tr style="border-bottom: 1px solid var(--tint-subtle); color: var(--text-primary); cursor: pointer;" onclick="showSubcategoryDetails('${escapeHtml(categoryName)}', '${escapeHtml(sub.subcategory)}')">
                        <td style="text-align: left; padding: 6px 8px; font-weight: 500; text-decoration: underline; text-underline-offset: 2px; text-decoration-color: var(--tint-strong);">${escapeHtml(sub.subcategory)}</td>
                        <td style="text-align: right; padding: 6px 8px;">${sub.count}</td>
                        <td style="text-align: right; padding: 6px 8px; font-weight: 600; color: var(--positive);">${money(sub.amount)}</td>
                        <td style="text-align: right; padding: 6px 8px; color: var(--text-secondary);">${pctShare}%</td>
                      </tr>
                    `;
                  }).join("")}
                </tbody>
              </table>
            </div>
          </td>
        </tr>
      `;
      
      rowElement.insertAdjacentHTML("afterend", subtableHtml);
      const chevron = rowElement.querySelector(".category-chevron");
      if (chevron) chevron.style.transform = "rotate(90deg)";
    };
    window.showSubcategoryDetails = function(categoryName, subcategoryName) {
      const allRows = window.currentExpenseRows || [];
      window.currentSubcatRows = allRows.filter(row => 
        (row.category || "Uncategorized") === categoryName &&
        ((row.subcategory || "").trim() || "Unspecified") === subcategoryName
      );
      window.currentSubcatSort = { column: "date", direction: "desc" };
      window.currentSubcatCategory = categoryName;
      window.currentSubcatName = subcategoryName;

      // Sort initially by date desc
      window.currentSubcatRows.sort((a, b) => String(b.date || "").localeCompare(String(a.date || "")));

      window.renderSubcategoryDetailsModal();
    };

    window.renderSubcategoryDetailsModal = function() {
      const categoryName = window.currentSubcatCategory;
      const subcategoryName = window.currentSubcatName;
      const rows = window.currentSubcatRows || [];
      const sort = window.currentSubcatSort || { column: "date", direction: "desc" };

      const indicator = col => {
        if (sort.column !== col) return "";
        return sort.direction === "asc" ? " &#9650;" : " &#9660;"; // ▲ or ▼
      };

      const subcatRowsHtml = rows.map(row => {
        const kind = expenseKind(row);
        const signedAmount = kind === "income" ? Number(row.amount_eur || 0) : (kind === "credits" ? Number(row.amount_eur || 0) : -Number(row.amount_eur || 0));
        const amountClass = signedAmount > 0 ? "positive" : (signedAmount < 0 ? "negative" : "");
        return `
          <tr style="border-bottom: 1px solid var(--tint-subtle);">
            <td style="padding: 6px 8px; font-family: monospace;">${escapeHtml(row.date)}</td>
            <td style="padding: 6px 8px;">${escapeHtml(row.source_label || row.source || "")}</td>
            <td style="padding: 6px 8px; font-weight: 500; color: var(--text-primary);">${escapeHtml(row.merchant || "")}</td>
            <td style="padding: 6px 8px; color: var(--text-secondary); max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${escapeHtml(row.description || "")}">${escapeHtml(row.description || "")}</td>
            <td style="padding: 6px 8px; text-align: right; font-weight: 600;" class="${amountClass}">${money(signedAmount)}</td>
          </tr>
        `;
      }).join("");

      const html = `
        <div class="table-wrap" style="margin-top: 8px;">
          <table style="width: 100%; border-collapse: collapse; font-size: 12.5px;">
            <thead>
              <tr style="border-bottom: 1px solid var(--border-strong); color: var(--text-secondary); font-weight: 500;">
                <th class="sort-cell" onclick="window.sortSubcategoryDetails('date')">Date${indicator('date')}</th>
                <th class="sort-cell" onclick="window.sortSubcategoryDetails('source')">Source${indicator('source')}</th>
                <th style="text-align: left; padding: 6px 8px; width: 120px; cursor: pointer; user-select: none;" onclick="window.sortSubcategoryDetails('merchant')">Merchant${indicator('merchant')}</th>
                <th style="text-align: left; padding: 6px 8px; cursor: pointer; user-select: none;" onclick="window.sortSubcategoryDetails('description')">Description${indicator('description')}</th>
                <th style="text-align: right; padding: 6px 8px; width: 95px; cursor: pointer; user-select: none;" onclick="window.sortSubcategoryDetails('amount')">Amount${indicator('amount')}</th>
              </tr>
            </thead>
            <tbody>
              ${subcatRowsHtml}
            </tbody>
          </table>
        </div>
      `;

      const title = `${escapeHtml(categoryName)} &gt; ${escapeHtml(subcategoryName)} (${rows.length} rows)`;
      window.showInfoModal(title, html);
    };

    window.sortSubcategoryDetails = function(columnName) {
      const sort = window.currentSubcatSort;
      if (sort.column === columnName) {
        sort.direction = sort.direction === "asc" ? "desc" : "asc";
      } else {
        sort.column = columnName;
        sort.direction = (columnName === "date" || columnName === "amount") ? "desc" : "asc";
      }

      const multiplier = sort.direction === "asc" ? 1 : -1;

      window.currentSubcatRows.sort((a, b) => {
        if (columnName === "date") {
          return multiplier * String(a.date || "").localeCompare(String(b.date || ""));
        }
        if (columnName === "source") {
          const sA = String(a.source_label || a.source || "");
          const sB = String(b.source_label || b.source || "");
          return multiplier * sA.localeCompare(sB);
        }
        if (columnName === "merchant") {
          return multiplier * String(a.merchant || "").localeCompare(String(b.merchant || ""));
        }
        if (columnName === "description") {
          return multiplier * String(a.description || "").localeCompare(String(b.description || ""));
        }
        if (columnName === "amount") {
          const getVal = row => {
            const kind = expenseKind(row);
            return kind === "income" ? Number(row.amount_eur || 0) : (kind === "credits" ? Number(row.amount_eur || 0) : -Number(row.amount_eur || 0));
          };
          return multiplier * (getVal(a) - getVal(b));
        }
        return 0;
      });

      window.renderSubcategoryDetailsModal();
    };
    function renderNetContributions(contributions) {
      document.getElementById("contributions-summary").textContent = `${money(contributions.net_eur)} net | ${money(contributions.total_buys_eur)} buys | ${money(contributions.total_sells_eur)} sells`;
      document.getElementById("contributions-broker").innerHTML = contributions.by_broker.map(row => `
        <tr>
          <td>${row.broker}</td>
          <td>${money(row.buys_eur)}</td>
          <td>${money(row.sells_eur)}</td>
          <td class="${signedClass(row.net_eur)}">${money(row.net_eur)}</td>
          <td>${percent(row.share_pct)}</td>
        </tr>
      `).join("");
      document.getElementById("contributions-date").innerHTML = contributions.by_date.slice(0, 20).map(row => `
        <tr>
          <td>${row.date}</td>
          <td>${money(row.buys_eur)}</td>
          <td>${money(row.sells_eur)}</td>
          <td class="${signedClass(row.net_eur)}">${money(row.net_eur)}</td>
        </tr>
      `).join("");
    }
    function periodStartDate(data) {
      if (selectedPeriod === "all") return null;
      if (selectedPeriod === "since24") return new Date("2024-01-11");
      const valueSeries = data.valuation_series || [];
      const endValue = valueSeries.length ? valueSeries[valueSeries.length - 1].date : data.date_range.end;
      const start = new Date(endValue || Date.now());
      if (selectedPeriod === "ytd") {
        start.setMonth(0);
        start.setDate(1);
      }
      if (selectedPeriod === "1w") start.setDate(start.getDate() - 7);
      if (selectedPeriod === "1m") start.setMonth(start.getMonth() - 1);
      if (selectedPeriod === "1y") start.setFullYear(start.getFullYear() - 1);
      return start;
    }
    function periodFrictions(data) {
      const source = data.frictions || { status: "unavailable", rows: [], message: "" };
      if (source.status !== "available") return { ...source, by_broker: [], rows: [] };

      const start = periodStartDate(data);
      const rows = (source.rows || []).filter(row => !start || new Date(row.date) >= start);
      const brokerMap = {};
      let costs = 0;
      let taxes = 0;
      let dividendTax = 0;
      rows.forEach(row => {
        const amount = Number(row.amount_eur || 0);
        brokerMap[row.broker] ||= { broker: row.broker, costs_eur: 0, taxes_eur: 0, dividend_tax_eur: 0, total_eur: 0 };
        if (row.type === "cost") {
          costs += amount;
          brokerMap[row.broker].costs_eur += amount;
        } else if (row.type === "dividend_tax") {
          dividendTax += amount;
          brokerMap[row.broker].dividend_tax_eur += amount;
          brokerMap[row.broker].taxes_eur += amount;
        } else {
          taxes += amount;
          brokerMap[row.broker].taxes_eur += amount;
        }
        brokerMap[row.broker].total_eur += amount;
      });
      const totalTaxes = taxes + dividendTax;
      const totalDrag = costs + totalTaxes;
      const totals = periodMetrics(data);
      return {
        status: "available",
        message: "",
        total_costs_eur: costs,
        total_taxes_eur: totalTaxes,
        trade_taxes_eur: taxes,
        dividend_tax_eur: dividendTax,
        total_drag_eur: totalDrag,
        net_liquidation_eur: Number(totals.market_value || 0) - totalDrag,
        by_broker: Object.values(brokerMap).sort((a, b) => Math.abs(b.total_eur) - Math.abs(a.total_eur)),
        rows
      };
    }
    function renderFrictions(data) {
      const frictions = periodFrictions(data);
      const unavailable = frictions.status !== "available";
      const message = frictions.message || "No tax or broker cost events are available for this portfolio.";
      document.getElementById("frictions-summary").textContent = unavailable
        ? "Not available"
        : `${selectedWindowLabel()} | ${money(frictions.total_drag_eur)} total drag`;
      document.getElementById("friction-metrics").innerHTML = unavailable ? `<div class="empty-state">${message}</div>` : `
        <div class="friction-item"><span>Taxes paid</span><strong>${money(frictions.total_taxes_eur)}</strong></div>
        <div class="friction-item"><span>Costs paid</span><strong>${money(frictions.total_costs_eur)}</strong></div>
        <div class="friction-item"><span>Total drag</span><strong>${money(frictions.total_drag_eur)}</strong></div>
        <div class="friction-item"><span>Net liquidation</span><strong>${money(frictions.net_liquidation_eur)}</strong></div>
      `;
      document.getElementById("frictions-broker").innerHTML = unavailable || !frictions.by_broker.length
        ? `<tr><td colspan="5" class="empty-state">${message}</td></tr>`
        : frictions.by_broker.map(row => `
          <tr>
            <td>${row.broker}</td>
            <td>${money(row.costs_eur)}</td>
            <td>${money(row.taxes_eur)}</td>
            <td>${money(row.dividend_tax_eur)}</td>
            <td>${money(row.total_eur)}</td>
          </tr>
        `).join("");
      document.getElementById("frictions-events").innerHTML = unavailable || !frictions.rows.length
        ? `<tr><td colspan="5" class="empty-state">${message}</td></tr>`
        : frictions.rows.slice(0, 30).map(row => `
          <tr>
            <td>${row.date}</td>
            <td>${row.broker}</td>
            <td>${row.type_label}</td>
            <td>${row.description}</td>
            <td class="${signedClass(row.amount_eur)}">${money(row.amount_eur)}</td>
          </tr>
        `).join("");

      // Render Tax Loss Carry-forwards
      const losses = data.tax_losses || [];
      const lossesWrap = document.getElementById("tax-losses-wrap");
      if (lossesWrap) {
        if (losses.length > 0) {
          lossesWrap.style.display = "block";
          document.getElementById("tax-losses-tbody").innerHTML = losses.map(row => `
            <tr>
              <td>${row.year}</td>
              <td>${row.broker}</td>
              <td class="red">${money(row.amount_eur)}</td>
              <td>31/12/${row.expires_year}</td>
            </tr>
          `).join("");
        } else {
          lossesWrap.style.display = "none";
        }
      }
    }
    function renderCoverage(data) {
      const open = data.positions.filter(p => p.is_open);
      const priced = open.filter(p => p.pricing_status === "priced").length;
      const pct = open.length ? Math.round(priced / open.length * 100) : 0;
      if (data.valuation_status.status === "snapshot") {
        document.getElementById("coverage-bar").style.width = open.length ? "100%" : "0%";
        document.getElementById("coverage-text").textContent = `${open.length} snapshot assets`;
        document.getElementById("mapping-status").innerHTML = `<div>Values come from the uploaded monthly CSV snapshot.</div>`;
        return;
      }
      document.getElementById("coverage-bar").style.width = `${pct}%`;
      document.getElementById("coverage-text").textContent = `${priced}/${open.length} open assets priced`;
      document.getElementById("mapping-status").innerHTML = `
        <div>${data.mapping_status.filled_isins}/${data.mapping_status.total_rows} mapping rows have ISINs.</div>
        <div>${data.mapping_status.missing_in_mapping.length} assets are missing from the mapping CSV.</div>
      `;
    }
    function calculateReturnStats(portfolioReturns, msciReturns, xeonReturns) {
      const rfDaily = 0.03 / 252;
      const sqrt252 = Math.sqrt(252);
      const mean = values => values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0;
      const variance = (values, avg) => values.length ? values.reduce((sum, value) => sum + Math.pow(value - avg, 2), 0) / values.length : 0;
      const statsFor = values => {
        const avg = mean(values);
        const varValue = variance(values, avg);
        const std = Math.sqrt(varValue);
        const sharpe = std > 0 ? ((avg - rfDaily) / std * sqrt252) : 0;
        return {
          daily_variance_pct: varValue * 10000,
          daily_volatility_pct: std * 100,
          annualized_volatility_pct: std * sqrt252 * 100,
          sharpe_ratio: sharpe,
          mean_daily_return_pct: avg * 100
        };
      };
      return {
        portfolio: statsFor(portfolioReturns),
        msci: statsFor(msciReturns),
        xeon: statsFor(xeonReturns)
      };
    }
    function statsForSelectedWindow(data, mode) {
      const stats = data.stats;
      const rows = (stats && stats.daily_returns) || [];
      if (!rows.length) {
        return {
          statsData: stats ? stats[mode] : null,
          daysEvaluated: stats ? stats.days_evaluated : 0,
          startDate: stats ? stats.start_date : "",
          endDate: stats ? stats.end_date : "",
          returns: { portfolio: [], msci: [], xeon: [] }
        };
      }

      const start = periodStartDate(data);
      const windowRows = rows.filter(row => !start || new Date(row.date) >= start);
      const key = mode === "price_return" ? "price_return" : "total_return";
      const numericValue = value => value === null || value === undefined ? null : Number(value);
      const portfolioReturns = windowRows.map(row => numericValue(row[key])).filter(Number.isFinite);
      const msciReturns = windowRows.map(row => numericValue(row.msci_return)).filter(Number.isFinite);
      const xeonReturns = windowRows.map(row => numericValue(row.xeon_return)).filter(Number.isFinite);

      if (portfolioReturns.length < 2) {
        return {
          statsData: null,
          daysEvaluated: portfolioReturns.length,
          startDate: windowRows[0] ? windowRows[0].date : "",
          endDate: windowRows.length ? windowRows[windowRows.length - 1].date : "",
          returns: { portfolio: portfolioReturns, msci: msciReturns, xeon: xeonReturns }
        };
      }

      return {
        statsData: calculateReturnStats(portfolioReturns, msciReturns, xeonReturns),
        daysEvaluated: portfolioReturns.length,
        startDate: windowRows[0] ? windowRows[0].date : "",
        endDate: windowRows.length ? windowRows[windowRows.length - 1].date : "",
        returns: { portfolio: portfolioReturns, msci: msciReturns, xeon: xeonReturns }
      };
    }
    function signedReturnPct(value) {
      if (!Number.isFinite(Number(value))) return "-";
      const n = Number(value);
      return `${n >= 0 ? "+" : ""}${pct.format(n)}%`;
    }
    function quantile(sortedValues, q) {
      if (!sortedValues.length) return 0;
      const pos = (sortedValues.length - 1) * q;
      const base = Math.floor(pos);
      const rest = pos - base;
      const next = sortedValues[base + 1];
      return next === undefined ? sortedValues[base] : sortedValues[base] + rest * (next - sortedValues[base]);
    }
    function distributionMeta(values) {
      const pctValues = (values || []).map(value => Number(value) * 100).filter(Number.isFinite).sort((a, b) => a - b);
      if (!pctValues.length) return "No data";
      const meanValue = pctValues.reduce((sum, value) => sum + value, 0) / pctValues.length;
      const medianValue = quantile(pctValues, 0.5);
      const lowValue = quantile(pctValues, 0.05);
      const highValue = quantile(pctValues, 0.95);
      return `n=${pctValues.length}<br>mean ${signedReturnPct(meanValue)} | median ${signedReturnPct(medianValue)}<br>5-95% ${signedReturnPct(lowValue)} to ${signedReturnPct(highValue)}`;
    }
    function returnDistributionDomain(portfolioReturns, msciReturns) {
      const values = [...(portfolioReturns || []), ...(msciReturns || [])]
        .map(value => Number(value) * 100)
        .filter(Number.isFinite);
      const maxAbs = Math.max(0.25, ...values.map(value => Math.abs(value)));
      const padded = maxAbs * 1.08;
      const step = padded <= 1 ? 0.25 : padded <= 3 ? 0.5 : padded <= 8 ? 1 : 2;
      const limit = Math.ceil(padded / step) * step;
      return { min: -limit, max: limit };
    }
    function histogramForReturns(values, domain, bins) {
      const pctValues = (values || []).map(value => Number(value) * 100).filter(Number.isFinite);
      const counts = Array.from({ length: bins }, () => 0);
      const width = (domain.max - domain.min) / bins;
      pctValues.forEach(value => {
        const rawIndex = Math.floor((value - domain.min) / width);
        const index = Math.max(0, Math.min(bins - 1, rawIndex));
        counts[index] += 1;
      });
      const meanValue = pctValues.length ? pctValues.reduce((sum, value) => sum + value, 0) / pctValues.length : 0;
      return { counts, meanValue, values: pctValues };
    }
    function renderHistogramSvg(svgId, histogram, domain, yMax, seriesClass) {
      const svg = document.getElementById(svgId);
      if (!svg) return;
      const values = histogram.values || [];
      if (values.length < 2) {
        svg.setAttribute("viewBox", "0 0 520 210");
        svg.innerHTML = `<text x="260" y="108" text-anchor="middle" class="hist-label">Not enough daily returns for this window</text>`;
        return;
      }

      const width = 520;
      const height = 210;
      const margin = { top: 14, right: 18, bottom: 32, left: 36 };
      const plotW = width - margin.left - margin.right;
      const plotH = height - margin.top - margin.bottom;
      const bins = histogram.counts.length;
      const binW = plotW / bins;
      const domainWidth = domain.max - domain.min;
      const xFor = value => margin.left + ((value - domain.min) / domainWidth) * plotW;
      const yFor = count => margin.top + plotH - (count / Math.max(1, yMax)) * plotH;
      const bars = histogram.counts.map((count, index) => {
        const x = margin.left + index * binW + 1.5;
        const y = yFor(count);
        const h = margin.top + plotH - y;
        return `<rect class="hist-bar ${seriesClass}" x="${x.toFixed(2)}" y="${y.toFixed(2)}" width="${Math.max(1, binW - 3).toFixed(2)}" height="${Math.max(0, h).toFixed(2)}" rx="3"><title>${count} days</title></rect>`;
      }).join("");
      const zeroLine = domain.min < 0 && domain.max > 0
        ? `<line class="hist-zero-line" x1="${xFor(0).toFixed(2)}" y1="${margin.top}" x2="${xFor(0).toFixed(2)}" y2="${margin.top + plotH}"></line>`
        : "";
      const meanX = xFor(histogram.meanValue);
      const grid = [0.25, 0.5, 0.75, 1].map(step => {
        const y = margin.top + plotH - plotH * step;
        return `<line class="hist-grid-line" x1="${margin.left}" y1="${y.toFixed(2)}" x2="${margin.left + plotW}" y2="${y.toFixed(2)}"></line>`;
      }).join("");
      svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
      svg.innerHTML = `
        ${grid}
        <line class="hist-axis" x1="${margin.left}" y1="${margin.top + plotH}" x2="${margin.left + plotW}" y2="${margin.top + plotH}"></line>
        ${zeroLine}
        ${bars}
        <line class="hist-mean-line ${seriesClass}" x1="${meanX.toFixed(2)}" y1="${margin.top}" x2="${meanX.toFixed(2)}" y2="${margin.top + plotH}"><title>Mean ${signedReturnPct(histogram.meanValue)}</title></line>
        <text class="hist-label" x="${margin.left}" y="${height - 10}" text-anchor="start">${signedReturnPct(domain.min)}</text>
        <text class="hist-label" x="${xFor(0).toFixed(2)}" y="${height - 10}" text-anchor="middle">0%</text>
        <text class="hist-label" x="${margin.left + plotW}" y="${height - 10}" text-anchor="end">${signedReturnPct(domain.max)}</text>
        <text class="hist-label" x="${margin.left}" y="${margin.top + 10}" text-anchor="start">${yMax} days</text>
      `;
    }
    function renderReturnDistributions(windowStats) {
      const returns = windowStats.returns || { portfolio: [], msci: [] };
      const portfolioReturns = returns.portfolio || [];
      const msciReturns = returns.msci || [];
      const domain = returnDistributionDomain(portfolioReturns, msciReturns);
      const bins = 18;
      const portfolioHistogram = histogramForReturns(portfolioReturns, domain, bins);
      const msciHistogram = histogramForReturns(msciReturns, domain, bins);
      const yMax = Math.max(1, ...portfolioHistogram.counts, ...msciHistogram.counts);

      const summary = document.getElementById("stats-dist-summary");
      if (summary) {
        summary.textContent = `${selectedWindowLabel()} | same daily-return bins | dashed line = mean`;
      }
      const portfolioMeta = document.getElementById("stats-port-dist-meta");
      if (portfolioMeta) portfolioMeta.innerHTML = distributionMeta(portfolioReturns);
      const msciMeta = document.getElementById("stats-msci-dist-meta");
      if (msciMeta) msciMeta.innerHTML = distributionMeta(msciReturns);

      renderHistogramSvg("stats-port-dist", portfolioHistogram, domain, yMax, "portfolio");
      renderHistogramSvg("stats-msci-dist", msciHistogram, domain, yMax, "msci");
    }
    function renderStats(data) {
      const statsSection = document.getElementById("stats-section");
      if (!statsSection) return;
      
      const stats = data.stats;
      if (!stats) {
        statsSection.style.display = "none";
        return;
      }
      
      statsSection.style.display = "block";
      
      const mode = (selectedReturnMode === "price") ? "price_return" : "total_return";
      const modeLabel = (selectedReturnMode === "price") ? "Price Return (securities only)" : "Total Return (including cash & dividends)";
      const windowStats = statsForSelectedWindow(data, mode);
      const statsData = windowStats.statsData;
      
      if (!statsData) {
        statsSection.style.display = "none";
        return;
      }
      
      document.getElementById("stats-summary").textContent = 
        `${windowStats.daysEvaluated} trading days evaluated | period: ${windowStats.startDate} to ${windowStats.endDate} | window: ${selectedWindowLabel()} | mode: ${modeLabel}`;
      
      const p = statsData.portfolio;
      document.getElementById("stats-port-mean").textContent = `${p.mean_daily_return_pct.toFixed(4)}%`;
      document.getElementById("stats-port-var").textContent = `${p.daily_variance_pct.toFixed(4)}%² (${(p.daily_variance_pct / 10000).toFixed(8)})`;
      document.getElementById("stats-port-daily-vol").textContent = `${p.daily_volatility_pct.toFixed(4)}%`;
      document.getElementById("stats-port-ann-vol").textContent = `${p.annualized_volatility_pct.toFixed(2)}%`;
      document.getElementById("stats-port-sharpe").textContent = p.sharpe_ratio.toFixed(2);
      renderReturnDistributions(windowStats);
      
      const m = statsData.msci;
      document.getElementById("stats-msci-mean").textContent = `${m.mean_daily_return_pct.toFixed(4)}%`;
      document.getElementById("stats-msci-var").textContent = `${m.daily_variance_pct.toFixed(4)}%² (${(m.daily_variance_pct / 10000).toFixed(8)})`;
      document.getElementById("stats-msci-daily-vol").textContent = `${m.daily_volatility_pct.toFixed(4)}%`;
      document.getElementById("stats-msci-ann-vol").textContent = `${m.annualized_volatility_pct.toFixed(2)}%`;
      document.getElementById("stats-msci-sharpe").textContent = m.sharpe_ratio.toFixed(2);
      
      const x = statsData.xeon;
      if (x) {
        document.getElementById("stats-xeon-mean").textContent = `${x.mean_daily_return_pct.toFixed(4)}%`;
        document.getElementById("stats-xeon-var").textContent = `${x.daily_variance_pct.toFixed(4)}%² (${(x.daily_variance_pct / 10000).toFixed(8)})`;
        document.getElementById("stats-xeon-daily-vol").textContent = `${x.daily_volatility_pct.toFixed(4)}%`;
        document.getElementById("stats-xeon-ann-vol").textContent = `${x.annualized_volatility_pct.toFixed(2)}%`;
        document.getElementById("stats-xeon-sharpe").textContent = x.sharpe_ratio.toFixed(2);
      }
    }
    function selectorButtonLabel(button) {
      return button.dataset.label || (button.querySelector(".selector-label")?.textContent || button.textContent || "").trim();
    }
    function brokerLogoClass(broker) {
      const key = String(broker || "all").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
      return key || "all";
    }
    function brokerLogoMark(broker) {
      const key = String(broker || "all").toLowerCase();
      if (key === "all") {
        return `<svg viewBox="0 0 24 24"><rect x="4" y="4" width="6" height="6" rx="1.5"/><rect x="14" y="4" width="6" height="6" rx="1.5"/><rect x="4" y="14" width="6" height="6" rx="1.5"/><rect x="14" y="14" width="6" height="6" rx="1.5"/></svg>`;
      }
      if (key === "crypto wallet") {
        return `<svg viewBox="0 0 24 24"><path d="M19 7H5a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2Z"/><path d="M16 12h3"/><path d="M17 7V5a2 2 0 0 0-2-2H6"/></svg>`;
      }
      const marks = {
        "fineco": "F",
        "interactive brokers": "IB",
        "trade republic": "TR",
        "etoro": "eT",
        "bbva": "BB",
        "mediolanum": "M",
        "manual": "M"
      };
      if (marks[key]) return escapeHtml(marks[key]);
      const initials = String(broker || "")
        .replace(/[^A-Za-z0-9 ]+/g, " ")
        .trim()
        .split(/\s+/)
        .filter(Boolean)
        .map(word => word[0])
        .join("")
        .slice(0, 2)
        .toUpperCase();
      return escapeHtml(initials || "W");
    }
    function brokerLogoHtml(broker) {
      return `<span class="broker-logo ${brokerLogoClass(broker)}" aria-hidden="true">${brokerLogoMark(broker)}</span>`;
    }
    function renderBrokerButtons(brokers) {
      const container = document.getElementById("brokers");
      if (!brokers || brokers.length <= 1) {
        container.style.display = "none";
        container.innerHTML = "";
        return;
      }
      container.style.display = "flex";
      
      const list = brokers.includes("all") ? brokers : ["all", ...brokers];
      
      container.innerHTML = list.map(b => {
        const brokerKey = String(b || "all").toLowerCase();
        const activeClass = selectedBroker === brokerKey ? "active" : "";
        const label = b === "all" ? "All Brokers" : b;
        return `<button type="button" data-broker="${escapeHtml(brokerKey)}" data-label="${escapeHtml(label)}" title="${escapeHtml(label)}" class="${activeClass}">
          ${brokerLogoHtml(b)}
          <span class="selector-label">${escapeHtml(label)}</span>
        </button>`;
      }).join("");

      container.querySelectorAll("button").forEach(button => {
        button.addEventListener("click", () => {
          if (selectedBroker === button.dataset.broker) return;
          selectedBroker = button.dataset.broker;
          resetHoldingsView();
          selectedPeriod = defaultPeriodForSelection();
          updatePeriodButtons();
          container.querySelectorAll("button").forEach(item => item.classList.toggle("active", item === button));
          load(false, `Filtering ${selectorButtonLabel(button)}`);
        });
      });
    }
    function formatRankingPct(val) {
      if (val === null || val === undefined) return `<span style="color:var(--text-muted)">—</span>`;
      const num = Number(val);
      const sign = num > 0 ? "+" : "";
      const color = num > 0 ? "var(--positive)" : (num < 0 ? "var(--negative)" : "var(--text-muted)");
      return `<span style="color:${color};font-weight:600">${sign}${num.toFixed(2)}%</span>`;
    }

    function renderRankings(data) {
      if (!data) return;
      const rankingsTbody = document.getElementById("rankings-tbody");
      const windowLabel = document.getElementById("rankings-window-label");
      if (!rankingsTbody || !windowLabel) return;
      
      const isTotal = (selectedReturnMode === "total");
      const modeKey = isTotal ? "total" : "price";
      
      const commonDateStr = data.common_start_date || "—";
      const ytdDateStr = data.ytd_start_date || "—";
      windowLabel.innerHTML = `Common alignment from <span style="color:var(--series-violet);font-weight:600">${commonDateStr}</span> | YTD from <span style="color:var(--warning);font-weight:600">${ytdDateStr}</span>`;

      const sorted = [...data.rankings].sort((a, b) => {
        let valA = 0.0;
        let valB = 0.0;
        if (a.returns && a.returns[modeKey]) {
          valA = a.returns[modeKey][rankingsSort.key] || 0.0;
        }
        if (b.returns && b.returns[modeKey]) {
          valB = b.returns[modeKey][rankingsSort.key] || 0.0;
        }
        return rankingsSort.direction === "desc" ? valB - valA : valA - valB;
      });

      rankingsTbody.innerHTML = sorted.map(user => {
        const ret = user.returns[modeKey] || {};
        const startVal = ret.start;
        const commonVal = ret.common;
        const ytdVal = ret.ytd;
        
        const isCurrentPerson = (user.person === selectedPerson);
        const rowStyle = isCurrentPerson ? 'background: color-mix(in srgb, var(--accent) 8%, transparent); font-weight: 500;' : '';
        const nameStyle = isCurrentPerson ? 'color: var(--accent); font-weight: 700;' : '';

        return `
          <tr style="${rowStyle}">
            <td style="text-align: left; display: flex; align-items: center; gap: 8px;">
              <span class="user-avatar ${user.person}" aria-hidden="true">
                <svg viewBox="0 0 24 24"><path d="M20 21a8 8 0 0 0-16 0"/><circle cx="12" cy="7" r="4"/></svg>
              </span>
              <span style="${nameStyle}">${escapeHtml(user.name)}</span>
            </td>
            <td>${formatRankingPct(startVal)}</td>
            <td>${formatRankingPct(commonVal)}</td>
            <td>${formatRankingPct(ytdVal)}</td>
          </tr>
        `;
      }).join("");
    }

    function updateRankingsHeaders() {
      ["start", "common", "ytd"].forEach(k => {
        const el = document.getElementById(`rank-header-${k}`);
        if (!el) return;
        let title = k === "start" ? "Return (Start of Portfolio)" : (k === "common" ? "Return (Common Alignment)" : "Return (YTD)");
        if (rankingsSort.key === k) {
          const arrow = rankingsSort.direction === "desc" ? " ↓" : " ↑";
          el.textContent = title + arrow;
          el.style.color = "var(--text-primary)";
        } else {
          el.textContent = title;
          el.style.color = "";
        }
      });
    }

    window.sortRankings = function(key) {
      if (rankingsSort.key === key) {
        rankingsSort.direction = rankingsSort.direction === "desc" ? "asc" : "desc";
      } else {
        rankingsSort.key = key;
        rankingsSort.direction = "desc";
      }
      updateRankingsHeaders();
      if (rankingsData) {
        renderRankings(rankingsData);
      }
    };

    function renderDashboard(data) {
      updatePeriodButtons();
      // Check if MyStyle is in the portfolio to show/hide and setup fee calculator
      const hasMyStyle = (data.positions || []).some(p => p.asset.toLowerCase().includes("mystyle"));
      const calcSection = document.getElementById("mystyle-calc-section");
      const breakdownSection = document.getElementById("mystyle-breakdown-section");
      if (calcSection) {
        if (hasMyStyle) {
          calcSection.style.display = "block";
          if (breakdownSection) breakdownSection.style.display = "block";
          const mystylePos = data.positions.find(p => p.asset.toLowerCase().includes("mystyle"));
          if (mystylePos) {
            const cap = Math.round(mystylePos.market_value_eur);
            document.getElementById("input-start-cap").value = cap;
            document.getElementById("input-start-cap").max = Math.max(1000000, cap * 2);
          }
          updateCalculator();
        } else {
          calcSection.style.display = "none";
          if (breakdownSection) breakdownSection.style.display = "none";
        }
      }

      // Build symbol and type lookup maps for company logos and badges
      const assetToSymbol = {};
      const assetToType = {};
      const symbolToIsin = {};
      (data.positions || []).forEach(p => {
        if (p.symbol) assetToSymbol[p.asset] = p.symbol;
        if (p.asset_type) assetToType[p.asset] = p.asset_type;
        if (p.symbol && p.isin) symbolToIsin[p.symbol.toUpperCase()] = p.isin;
      });
      window.assetToSymbolMap = assetToSymbol;
      window.assetToTypeMap = assetToType;
      window.symbolToIsinMap = symbolToIsin;
      if (!((data.distribution || {}).composition_sources || []).some(row => sourceKey(row) === selectedDistributionSource)) {
        selectedDistributionSource = "";
      }

      renderMetrics(periodMetrics(data));
      renderRankings(rankingsData);
      renderValueCharts(data.valuation_series || []);
      renderChart(data.series);
      renderPositions(data.positions);
      renderDistribution(data.distribution);
      renderDividends(data.dividends);
      renderCashInterests(data.cash_interests);
      renderExpenses(data);
      renderNetContributions(data.net_contributions);
      renderFrictions(data);
      renderCoverage(data);
      renderStats(data);
      renderBrokerButtons(data.brokers);
      
      // Render optional actions supplied by the selected portfolio profile.
      const todosSection = document.getElementById("todos-section");
      if (todosSection) {
        const todoItems = Array.isArray(data.todo_items) ? data.todo_items : [];
        if (todoItems.length) {
          todosSection.style.display = "block";
          document.getElementById("todos-list").innerHTML = todoItems
            .map(item => `<li style="margin-bottom: 8px;">${escapeHtml(item)}</li>`)
            .join("");
        } else {
          todosSection.style.display = "none";
        }
      }

      document.getElementById("range").textContent = chartRangeLabel(data.series || []);
      document.getElementById("value-window").textContent = selectedWindowLabel();
      document.getElementById("meta").textContent = `Portfolio Dashboard v${APP_VERSION}`;
      updateExportSummary();
    }
    function renderChartsOnly() {
      if (!dashboardData) return;
      renderValueCharts(dashboardData.valuation_series || []);
      renderChart(dashboardData.series || []);
      document.getElementById("range").textContent = chartRangeLabel(dashboardData.series || []);
      document.getElementById("value-window").textContent = selectedWindowLabel();
      updateExportSummary();
    }
    function scheduleChartResize() {
      if (!dashboardData) return;
      window.clearTimeout(chartResizeTimer);
      chartResizeTimer = window.setTimeout(renderChartsOnly, 80);
    }
    async function load(refresh = false, label = "Updating dashboard") {
      const requestId = ++loadRequestId;
      const button = document.getElementById("refresh");
      const error = document.getElementById("error");
      button.disabled = true;
      error.style.display = "none";
      setDashboardBusy(true, label);
      try {
        const params = currentQueryParams();
        if (refresh) params.set("refresh", "1");
        const [portfolioRes, rankingsRes] = await Promise.all([
          fetch(`/api/portfolio?${params.toString()}`),
          fetch(`/api/rankings?${params.toString()}`)
        ]);
        const data = await portfolioRes.json();
        if (!portfolioRes.ok) throw new Error(data.error || "Dashboard request failed.");
        if (rankingsRes.ok) {
          rankingsData = await rankingsRes.json();
        } else {
          const rankErr = await rankingsRes.json();
          console.warn("Rankings failed to load:", rankErr.error);
        }
        if (requestId !== loadRequestId) return;
        dashboardData = data;
        renderDashboard(data);
        loadNews(refresh, data.news_symbols || []);
        loadWatchlist(refresh);
      } catch (err) {
        if (requestId !== loadRequestId) return;
        error.textContent = err.message;
        error.style.display = "block";
      } finally {
        if (requestId === loadRequestId) {
          button.disabled = false;
          setDashboardBusy(false);
        }
      }
    }
    document.querySelectorAll("#periods button").forEach(button => {
      button.addEventListener("click", () => {
        if (button.dataset.period === "since24" && !canUseSince24Window()) return;
        if (selectedPeriod === button.dataset.period) return;
        selectedPeriod = button.dataset.period;
        updatePeriodButtons();
        if (dashboardData) withRedrawVeil("Redrawing selected window", () => renderDashboard(dashboardData));
      });
    });
    document.querySelectorAll("#persons button").forEach(button => {
      button.addEventListener("click", () => {
        if (selectedPerson === button.dataset.person) return;
        selectedPerson = button.dataset.person;
        selectedBroker = "all";
        resetHoldingsView();
        selectedPeriod = defaultPeriodForSelection();
        updatePeriodButtons();
        document.querySelectorAll("#persons button").forEach(item => item.classList.toggle("active", item === button));
        load(false, `Switching to ${selectorButtonLabel(button)}`);
      });
    });
    document.querySelectorAll("#berkshire-mode button").forEach(button => {
      button.addEventListener("click", () => {
        if (selectedBerkshireMode === button.dataset.berkshire) return;
        selectedBerkshireMode = button.dataset.berkshire;
        document.querySelectorAll("#berkshire-mode button").forEach(item => item.classList.toggle("active", item === button));
        load(false, `Applying ${button.textContent.trim()}`);
      });
    });
    document.querySelectorAll("#proxy-mode button").forEach(button => {
      button.addEventListener("click", () => {
        if (selectedProxyMode === button.dataset.proxy) return;
        selectedProxyMode = button.dataset.proxy;
        document.querySelectorAll("#proxy-mode button").forEach(item => item.classList.toggle("active", item === button));
        load(false, `Applying ${button.textContent.trim()}`);
      });
    });
    document.querySelectorAll("#live-mode button").forEach(button => {
      button.addEventListener("click", () => {
        if (selectedLiveMode === button.dataset.live) return;
        selectedLiveMode = button.dataset.live;
        resetHoldingsView();
        document.querySelectorAll("#live-mode button").forEach(item => item.classList.toggle("active", item === button));
        load(false, `Applying ${button.textContent.trim()}`);
      });
    });
    document.querySelectorAll("#return-mode button").forEach(button => {
      button.addEventListener("click", () => {
        if (selectedReturnMode === button.dataset.returnMode) return;
        selectedReturnMode = button.dataset.returnMode;
        document.querySelectorAll("#return-mode button").forEach(item => item.classList.toggle("active", item === button));
        if (dashboardData) {
          withRedrawVeil(`Switching to ${button.textContent.trim()}`, () => renderDashboard(dashboardData));
        }
      });
    });
    document.querySelectorAll("th[data-sort]").forEach(th => {
      th.addEventListener("click", () => {
        const key = th.dataset.sort;
        if (sortState.key === key) {
          sortState.direction = sortState.direction === "asc" ? "desc" : "asc";
        } else {
          sortState = { key, direction: ["asset", "isin", "symbol", "pricing_status"].includes(key) ? "asc" : "desc" };
        }
        if (dashboardData) renderPositions(dashboardData.positions);
      });
    });
    document.getElementById("refresh").addEventListener("click", () => {
      load(true, "Refreshing live prices");
    });
    document.getElementById("export-button").addEventListener("click", exportDashboard);

    const toggleMonthly = document.getElementById("expense-toggle-monthly");
    const toggleCumulative = document.getElementById("expense-toggle-cumulative");
    if (toggleMonthly && toggleCumulative) {
      toggleMonthly.addEventListener("click", () => {
        if (selectedExpenseTrendMode === "monthly") return;
        selectedExpenseTrendMode = "monthly";
        toggleMonthly.classList.add("active");
        toggleCumulative.classList.remove("active");
        toggleMonthly.style.background = "var(--accent)";
        toggleMonthly.style.color = "white";
        toggleCumulative.style.background = "transparent";
        toggleCumulative.style.color = "var(--text-muted)";
        if (dashboardData) {
          const expenses = periodExpenses(dashboardData);
          renderExpenseTrend(expenses.months);
        }
      });
      toggleCumulative.addEventListener("click", () => {
        if (selectedExpenseTrendMode === "cumulative") return;
        selectedExpenseTrendMode = "cumulative";
        toggleCumulative.classList.add("active");
        toggleMonthly.classList.remove("active");
        toggleCumulative.style.background = "var(--accent)";
        toggleCumulative.style.color = "white";
        toggleMonthly.style.background = "transparent";
        toggleMonthly.style.color = "var(--text-muted)";
        if (dashboardData) {
          const expenses = periodExpenses(dashboardData);
          renderExpenseTrend(expenses.months);
        }
      });
    }

    // Watchlist add bindings
    const addInput = document.getElementById("watchlist-add-input");
    const addBtn = document.getElementById("watchlist-add-btn");
    if (addBtn && addInput) {
      const addTickerAction = async () => {
        const ticker = addInput.value.trim();
        if (!ticker) return;
        addBtn.disabled = true;
        const originalText = addBtn.textContent;
        addBtn.textContent = "Adding…";
        try {
          const res = await fetch("/api/watchlist", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ticker: ticker, action: "add" })
          });
          const rData = await res.json();
          if (!res.ok) throw new Error(rData.error || "Failed to add ticker.");
          addInput.value = "";
          renderWatchlist(rData.watchlist || []);
        } catch (err) {
          alert(err.message);
        } finally {
          addBtn.disabled = false;
          addBtn.textContent = originalText;
        }
      };
      addBtn.addEventListener("click", addTickerAction);
      addInput.addEventListener("keydown", event => {
        if (event.key === "Enter") {
          addTickerAction();
        }
      });
    }
    const btnShowAllHoldings = document.getElementById("btn-show-all-holdings");
    btnShowAllHoldings.addEventListener("click", () => {
      showAllHoldings = !showAllHoldings;
      if (dashboardData) renderPositions(dashboardData.positions);
    });
    const btnClosed = document.getElementById("btn-toggle-closed");
    btnClosed.addEventListener("click", () => {
      showClosed = !showClosed;
      if (dashboardData) renderPositions(dashboardData.positions);
    });
    if ("ResizeObserver" in window) {
      const chartObserver = new ResizeObserver(scheduleChartResize);
      document.querySelectorAll(".chart-wrap").forEach(item => chartObserver.observe(item));
    }
    window.addEventListener("resize", scheduleChartResize);

    // Fee Compounding Calculator Logic
    function updateCalculator() {
      const cap = parseFloat(document.getElementById("input-start-cap").value);
      const years = parseInt(document.getElementById("input-horizon").value);
      const gross = parseFloat(document.getElementById("input-gross-ret").value) / 100.0;
      const mystyleFee = parseFloat(document.getElementById("input-mystyle-fee").value) / 100.0;
      const etfFee = parseFloat(document.getElementById("input-etf-fee").value) / 100.0;
      
      document.getElementById("lbl-start-cap").textContent = "€" + cap.toLocaleString("it-IT");
      document.getElementById("lbl-horizon").textContent = years + " years";
      document.getElementById("lbl-gross-ret").textContent = (gross * 100).toFixed(1) + "%";
      document.getElementById("lbl-mystyle-fee").textContent = (mystyleFee * 100).toFixed(2) + "%";
      document.getElementById("lbl-etf-fee").textContent = (etfFee * 100).toFixed(2) + "%";
      
      const mystyleNet = gross - mystyleFee;
      const etfNet = gross - etfFee;
      
      document.getElementById("val-mystyle-net-ret").textContent = (mystyleNet * 100).toFixed(2) + "%";
      document.getElementById("val-etf-net-ret").textContent = (etfNet * 100).toFixed(2) + "%";
      
      const mystyleProj = cap * Math.pow(1 + mystyleNet, years);
      const etfProj = cap * Math.pow(1 + etfNet, years);
      const lost = etfProj - mystyleProj;
      
      document.getElementById("val-proj-mystyle").textContent = "€" + Math.round(mystyleProj).toLocaleString("it-IT");
      document.getElementById("val-proj-etf").textContent = "€" + Math.round(etfProj).toLocaleString("it-IT");
      document.getElementById("val-lost-fees").textContent = "€" + Math.round(lost).toLocaleString("it-IT");
      
      const pct = etfProj > 0 ? (mystyleProj / etfProj * 100) : 0;
      document.getElementById("bar-pct-mystyle").textContent = pct.toFixed(1) + "%";
      document.getElementById("bar-mystyle").style.width = pct.toFixed(1) + "%";
    }

    ["input-start-cap", "input-horizon", "input-gross-ret", "input-mystyle-fee", "input-etf-fee"].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.addEventListener("input", updateCalculator);
    });

    /* ─── Colour-blind palette ─── */
    const PALETTE_KEY = "palette";

    function applyPalette(useCb) {
      const root = document.documentElement;
      if (useCb) {
        root.setAttribute("data-palette", "cb");
      } else {
        root.removeAttribute("data-palette");
      }
      const btn = document.getElementById("palette-toggle");
      if (btn) btn.setAttribute("aria-pressed", useCb ? "true" : "false");
      try { localStorage.setItem(PALETTE_KEY, useCb ? "cb" : "default"); } catch (e) { /* ignore */ }
      renderChartsOnly();
    }

    const paletteToggle = document.getElementById("palette-toggle");
    if (paletteToggle) {
      paletteToggle.addEventListener("click", () => {
        applyPalette(document.documentElement.getAttribute("data-palette") !== "cb");
      });
      paletteToggle.setAttribute(
        "aria-pressed",
        document.documentElement.getAttribute("data-palette") === "cb" ? "true" : "false"
      );
    }

    /* ─── Theme ─── */
    const THEME_KEY = "theme";

    function storedTheme() {
      try { return localStorage.getItem(THEME_KEY); } catch (e) { return null; }
    }

    function systemTheme() {
      return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
    }

    function activeTheme() {
      return document.documentElement.getAttribute("data-theme") || systemTheme();
    }

    function applyTheme(theme) {
      document.documentElement.setAttribute("data-theme", theme);
      try { localStorage.setItem(THEME_KEY, theme); } catch (e) { /* ignore */ }
      // Charts read their colours from computed tokens at draw time, so they
      // need a repaint; CSS-driven parts re-theme on their own.
      renderChartsOnly();
    }

    const themeToggle = document.getElementById("theme-toggle");
    if (themeToggle) {
      themeToggle.addEventListener("click", () => {
        applyTheme(activeTheme() === "light" ? "dark" : "light");
      });
    }

    // Follow the OS while the user has not made an explicit choice.
    window.matchMedia("(prefers-color-scheme: light)").addEventListener("change", () => {
      if (!storedTheme()) renderChartsOnly();
    });

    initializeSectionIdentity();
    initializeSectionWrapButtons();
    checkImportOnboarding();
    load(false, "Loading dashboard");
