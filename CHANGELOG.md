# Changelog

## 0.18.1 — 2026-11-25

- **Fineco capital-gain tax estimate.** The estimate grossed up the gain as if it were already net of tax, which came to 35.1% of the gain instead of 26%: Fineco books a sale before tax and debits the tax separately. It is now 26% of the gain. The gain uses Fineco's own average cost (the cross-broker average only for shares transferred in), and earlier losses are offset as in the administered regime: a loss offsets stock, bond and ETC gains until the end of the fourth following year, while ETF and fund gains are taxed in full. The 12.5% rate on government bonds is not modelled.
- **Realized P/L before tax at every broker.** Trade Republic and Interactive Brokers sales showed realized P/L after the tax withheld from them, while Fineco's was before tax. All are now before tax, with the tax listed under Taxes & costs; cash flows and returns are unchanged.
- **Taxes & costs.** Taxes are split into withheld by the broker and estimated, and each estimated row says so. Trade Republic tax refunds now lower the total instead of adding to it. "Net liquidation" subtracted fees and taxes already paid, which counted them twice; it is replaced by an after-tax value if everything were sold today: market value minus 26% of each open position's unrealized gain, before selling costs. The note now lists what is not included (stamp duty, IVAFE, tax on interest, self-declared taxes). The Dividends section says that Fineco's gross amount is after foreign withholding.
- **Pence.** A trade settled in GBX is converted as pence, not pounds.

## 0.18.0 — 2026-11-25

- **Family rankings are time-weighted.** Each person is ranked on the same time-weighted return their own dashboard shows, so money paid in or taken out no longer moves the ranking. Each window starts from the last value on or before its start date (YTD from the 31 December close). Portfolios rebuilt from a holdings snapshot are tagged "reconstructed": their history assumes today's holdings were bought on the start date, so it has no past sales or cash flows and carries hindsight.
- **Risk statistics.** The Sharpe ratio is now the mean of each day's return minus XEON's return that day, over its standard deviation, times √252. A fixed rate is used only when XEON quotes are missing, and the page says which one was used. XEON itself has no Sharpe ratio. Standard deviations are sample estimates (n−1). Below 60 daily returns, annualised volatility and Sharpe show "—" with the number of days instead of a figure that is mostly noise. With a broker filter, other brokers' dividends and interest no longer enter the daily returns. The statistics say that the crypto wallet is not included.
- **Return histogram.** Bars show the share of days, so the portfolio and MSCI are drawn on the same scale even with different numbers of days. The range covers the 1st to 99th percentile, with an overflow bin at each end.
- **Allocation.** Asset classes are grouped into Equity, Bond, Cash, Crypto, Commodity, Real estate and Other instead of each source's own wording. Open positions with no price are listed as not covered. The page says that cash-account balances are not part of the allocation, and the Berkshire look-through note gives its 13F / cash / operating-business split.

## 0.17.1 — 2026-11-25

- **Movers count your money.** The 1D/1W/1M movers used to multiply the stock's move by the shares held today, so a position bought during the window showed the whole move, including the part before the purchase. The euro figure now starts from the value held at the start of the window, adds what was bought and takes off what was sold in it, so it is the gain or loss on your money; its percentage is on the money at stake. The left column ranks by the stock's own price move, the right one by the euro result. Splits inside the window are counted in today's shares.

## 0.17.0 — 2026-11-25

- **Rail in groups.** The section rail is split into Portfolio (performance, holdings, allocation, statistics, family rankings), Cash & income (income & expenses, cash flows, contributions, dividends, cash interest, taxes & costs), Markets (watchlist, news) and Data (data & prices, export). The default section order follows the same groups; a saved order that was still the old default moves to the new one, while a custom order, and any hidden sections, are kept. On tablets and phones a thin divider separates the groups in the strip.
- **Filters in one panel.** People and the window are two segmented controls on the first row (names only: initials were not telling people apart); brokers, price/total return and a "View options" button sit on the second. View options opens the Berkshire, fund-composition and assets-shown choices, each with a line saying what it does, and the button counts the choices that differ from the defaults. On phones each row scrolls sideways instead of wrapping.
- **Headline chart: value and return.** Beside the headline, the value and net contributions (dashed) are drawn over the window, with the time-weighted return below it, green above zero and red below. The readout above shows the current value and return, matching the headline and the opening sentence; moving across the chart shows the value and return on that day. Both follow the price/total return choice.

## 0.16.0 — 2026-11-25

Halfway between the monthly report and a finance app: the serif and the calm stay, and the page gains a way around, icons and framed sections. Every section and control is still there.

- **Section rail.** On wide screens a column on the left lists every visible section with its icon, in your saved order; choosing one opens it if closed and scrolls to it, and the current section is highlighted as you scroll. On tablets and phones the same list is a strip of chips under the masthead.
- **Headline.** The portfolio value now sits beside a line of its value over the selected window, with the last day's move as a chip (arrow, percentage and euro amount) and the opening sentence below.
- **Sheets.** Investments, income & expenses and every section sit on their own sheet with an icon in the section's colour, a serif title, the summary and an open/closed marker on the right. Day, week and month changes are tiles inside the investments sheet.
- **Filters.** People are chips with their initial, brokers are chips with their marks, the window is a segmented control, and the view options are small segmented pairs.
- **Colour.** A slightly cooler stone page with white sheets in the light theme and graphite in the dark one; gain and loss inks, the colour-blind palette and contrast checks are unchanged.
- **Small screens.** On tablets the secondary masthead buttons become icons; on phones the masthead keeps to one line and the key figures fall into two columns.

## 0.15.0 — 2026-11-25

A calmer, editorial look: the dashboard now reads like a private monthly report. Every section and control is still there.

- **Paper and ink.** Warm paper in the light theme and a lamp-lit dark theme. Gains are set in a dark green ink and losses in red ink, with blue reserved for links and the selection; the colour-blind palette is kept.
- **Type.** A book serif (Iowan Old Style or Charter, falling back to Georgia) for headings and the figures that matter, and the system sans with tabular figures for tables and controls. No more capitalised labels.
- **An opening line.** Above the key figures, the portfolio value and a sentence for the selected window: the time-weighted return, how equities did against MSCI World, and the unrealised gain on current holdings.
- **Key figures as a statement.** Investments and income & expenses are two columns of label-and-figure rows separated by hairlines instead of boxed cards; the day/week/month changes are named "Last day", "Last week" and "Last month".
- **Chapters instead of cards.** Sections are separated by a rule and a serif title, without shadows, coloured borders or icons; tables, charts, legends and dialogs follow the same quiet style. Instrument types appear as small text ("ETF", "Stock", "Cash").
- **Selectors as words.** Portfolios, windows, brokers and options are plain words with an underline under the current choice.
- **Keyboard.** Section headings can be reached with Tab and opened with Enter or Space, and announce whether they are expanded.
- **Phones.** The masthead stays on a compact line with icon buttons, and selectors wrap instead of truncating names.

## 0.14.9 — 2026-11-25

- Risk statistics no longer see a crash when a position has no quote yet or no exchange rate on a day: it keeps its last EUR value (or its cost until its first quote) instead of counting as 0, and amounts in USD or pence are no longer added as euros when the rate is missing. Cash, dividend and interest totals are accumulated day by day instead of re-summed for every day.
- The Sharpe ratio computed in the browser uses the configured `annual_risk_free_rate`, like the server and the label, instead of a fixed 3%.
- The 1M and 1Y windows clamp to the end of the month: one month before 31 March starts on the last day of February, not on 3 March.
- When switching portfolio fails, the selection returns to the portfolio still on screen and the message says so, instead of showing the previous portfolio's numbers under the new name.
- `crypto_wallet_fetcher.py` reads and writes its CSV files in `data_dir`, and `etf_fetcher.py` writes `asset_exposures.csv` there, where the dashboard reads them; both used the project folder.
- yfinance (and pandas) are imported only when an ISIN search or a watchlist quote needs them, so the app starts faster and uses less memory.
- Tests run against temporary source, data and cache directories (`conftest.py`), so a local configuration can never point them at a real ledger.
- README: background price refresh, current data sources, pre-1.0 status.

## 0.14.8 — 2026-11-25

- The portfolio response is about 80% smaller (about 75 KB instead of 400 KB compressed for a typical portfolio), which matters most over a relayed or mobile connection. Income and expense rows are no longer sent twice: the page requests them from `/api/expenses` alongside the portfolio and shows "…" until they arrive. Fund and sector holdings are fetched from `/api/portfolio/distribution-details` when first opened. Floats are rounded to the precision shown. Saved snapshots and exports are unchanged.
- The page, scripts and stylesheets are sent gzip-compressed (about 80% smaller), and versioned static files are cached by the browser for a year instead of being revalidated on every visit.
- News feeds are fetched in parallel instead of one after another (up to 12 seconds each), and news cache entries older than a week are dropped.
- Cache files are serialized under their write lock from a point-in-time copy, so a concurrent update can no longer abort a save with "dictionary changed size during iteration".
- A full snapshot is no longer pre-encoded to JSON every time it is kept in memory.

## 0.14.7 — 2026-11-25

- Archived statements are read again when the parser improves, and a re-read replaces that file's movements instead of adding to them. Rows the parser now reads differently are updated in place (keeping their categories), rows it no longer reads are removed with a revision kept, and nothing is stored twice. The first start after updating re-reads every archived file once: Intesa transfers and incoming bank transfers, and Fineco account transfers, that older parsers skipped are added; existing movements are unchanged.
- Imported files can be deleted from the import dialog. Deleting a file removes its movements, re-reads the other files of the same platform so rows they also contain are kept, and stops the file from being imported again at startup; uploading it again restores it.
- A Trade Republic export named after another portfolio's holder (`trade_republic_name`) in the archive folder is no longer imported into the primary portfolio at startup.
- Revolut cash movements present in both the regular and the consolidated statement are stored once instead of doubling the cash balance.
- Consolidated Revolut amounts are read with the shared parser, so `€12.50` is 12.50 rather than 1250.

## 0.14.6 — 2026-11-25

- The crypto wallet tool no longer empties a wallet when a fetch fails: a rate limit (HTTP 429) or outage used to rewrite `crypto_wallet_positions.csv` without that wallet, so its value vanished from the dashboard. The last balance is kept, marked `stale` with the error, along with the account's transaction audit.
- A cash-ledger deposit no longer hides an equal payment on the same day (or the other way round): rows repeating a statement row are matched on the signed amount, one cash row per statement row.
- Splits with a small ratio (free shares, stock dividends, up to about 4:3) were re-applied to the stored price history on every load, flipping it back and forth. Price gaps are now only corrected when they sit clearly closer to the split ratio than to no gap, which makes the correction idempotent, and ratios under 3:2 are left to the provider.
- A reverse split no longer reads as a realized loss: quantity-only corporate actions change the share count and keep the cost basis, and a split booked as "old shares out, new shares in" on one day restates the history by its net ratio. Shares written off to zero are still a loss.
- eToro closed positions are imported as sales (amount invested plus profit, in USD), so they no longer stay open forever. Short positions are skipped and reported in the import result.
- Current holdings quoted in pence (GBp, many `.L` tickers) are converted as hundredths of a pound; they were overstated 100× (the price history already divided by 100).
- CI also runs the period-window frontend test.

## 0.14.5 — 2026-11-24

- Read amounts in either notation: `1,234.56` was parsed as 1.23456, and `€1,234.56`, `(2.00)`, non-breaking-space grouping, `1.234.567` and the Unicode minus became 0. Empty cells and placeholders such as `-` or `n/a` still count as zero.
- Refuse an import, storing and archiving nothing, when a value cannot be read as a number instead of saving it as 0.
- Refuse an import when a foreign-currency row has no EUR exchange rate. Revolut and other expense rows used to be dropped while the import reported success, and re-uploading the file then said "duplicate"; trade commissions, taxes and eToro closed-position fees were stored in USD as if they were EUR.
- BBVA amounts with thousands separators (`2.500,00 EUR`) no longer abort the import or get skipped.
- Interactive Brokers confirmations are parsed for any account, with thousands separators in quantities and amounts.
- The import result lists rows skipped for an unreadable date, an unrecognised Interactive Brokers trade line or an unsupported symbol, and the import dialog shows them.

## 0.14.4 — 2026-11-24

- Window net contributions and realized P/L now include the first trade inside the window, and show only that window's trades (not the all-time totals) when it holds one trade or none.
- Window returns start from the valuation point nearest the window start: YTD is measured from the 31 December close instead of the first point in the year, which could skip most of January. The 1Y anniversary is now a valuation date.
- Purchases and sales no longer distort the time-weighted return: each trade day is valued together with the day before it, so its cash flow sits in a one-day interval instead of being spread over a month.
- The 1D/1W/1M cards use the same time-weighted return, so money added in the period is no longer reported as performance (a 9,000 purchase on top of 1,000 showed +10% for a +1% week), and they follow the Price/Total Return mode.
- Trade Republic dividends are shown net of withholding: the export's `amount` is gross, so dividends were overstated by the tax and the gross column double-counted it. Existing imports are corrected when read; nothing is re-imported.
- Saved dashboard snapshots are rebuilt once after updating.

## 0.14.3 — 2026-11-24

- Escape statement-derived names, ISINs, symbols, brokers, dates and descriptions everywhere the dashboard builds HTML. Asset logos no longer run inline JavaScript, and inline click handlers receive JSON-quoted arguments, so an imported row can no longer run script in the page.
- Reject cross-site writes: POST, PUT, PATCH and DELETE requests whose `Origin` is another site (or `Sec-Fetch-Site: cross-site`) get 403, so a web page open on the same network cannot upload a statement or change data. Requests without browser headers, such as local scripts, still work.
- Reject requests whose `Host` is not an IP address, `localhost`, or this machine's name (`name`, `name.local`, `name.<tailnet>.ts.net`), blocking DNS-rebinding reads. Add other names with `PORTFOLIO_TRUSTED_HOSTS` (comma-separated; a leading dot matches a domain and its subdomains).
- Send a Content-Security-Policy (`connect-src 'self'`, logo images only from assets.parqet.com, no framing) plus `nosniff`, `X-Frame-Options: DENY` and `Referrer-Policy: same-origin`.
- Keep exported text inert: XLSX cells starting with `=` are written as text instead of formulas, and PDF exports never fetch remote images named in statement text.
- CI now syntax-checks every script in `static/` and runs the income & expenses frontend test.

## 0.14.2 — 2026-11-10

- Classify a single share with no private exposure row (e.g. a newly bought NVIDIA position) from the sector and country any bundled or proxy fund gives the same company, instead of listing it as Uncategorized.
- Bundle the official iShares MSCI Global Semiconductors (IE000I8KRLL9) holdings, 240 rows as of 6 Nov 2026.
- Fetch iShares holdings from the BlackRock document API; the old product-page CSV endpoint now returns HTML.
- Replace issuer "Unknown" sector and country labels: cash lines become Cash, companies take the classification another fund gives them. Map the NVO listing to Novo Nordisk.

## 0.14.1 — 2026-11-10

- Skip cash-ledger rows that repeat a statement row on the same account, day and amount; BBVA's ledger lists every payment, which double-counted rent and card spending as transfers out.
- Import Fineco current-account transfers (bonifici, giroconti) as account cash flows, so deposits count in Net flow after re-importing the Fineco export.
- Group Top Merchants under normalized names: processor prefixes, store numbers, legal forms and FX suffixes are stripped, and common chains share one name.

## 0.14.0 — 2026-11-10

- Bring broker top-ups and withdrawals into income & expenses; card payments and trades already in the cash ledger are not repeated.
- Mark giroconti (an outflow from one own account matched by an equal inflow into another within four days). An "Include giroconti" toggle shows them per account; off, totals show only money entering or leaving your finances.
- Source Breakdown replaces "Bank balance" with Net flow: income, credits, top-ups, sales and dividends minus expenses, transfers out and purchases, so broker accounts no longer show impossible negative balances from missing deposits.

## 0.13.1 — 2026-11-10

- Upstream the Pi fix that nets Trade Republic card refunds against expenses instead of counting them as income; the browser summary now applies the same rule.
- Drop the always-zero bank "Investments" column from Source Breakdown; broker Invested/Sold columns replace it.

## 0.13.0 — 2026-11-10

- Credit cash added during a return interval for half the interval (Modified Dietz), and count a deposit that dwarfs the prior balance as invested at the start. A first real deposit on top of a few euros no longer shows as a −33% loss, which had pulled "since 1 Jan 2024" to −12%.
- Date live benchmark quotes by their own market close, so a closed market no longer reports a fresh "MSCI +0.00%" day against a moving portfolio.
- Refetch cached price history when it lacks the previous business day's close, instead of accepting data up to four days old (Monday's MSCI close was missing).
- Include the crypto wallet in the all-broker history, profit and contributions; the latest history point now matches the headline value.
- Source Breakdown adds Invested, Sold and Dividends & interest per broker for the selected window, plus a totals row, so every cash flow appears in one table.
- Move the saved-snapshot and price-date line from the top of the page into a Data & Prices section that collects trades, price dates, benchmark close, history consistency, allocation coverage and statement coverage.

## 0.12.1 — 2026-11-07

- Refresh BRK look-through to the June 30, 2026 SEC 13F, filed August 14: 89 manager rows consolidated into 29 securities.
- Bundle the public Berkshire reference in resources so app updates deliver it without changing private data. Preserve the existing 40/30/30 model allocation.

## 0.11.1 — 2026-11-06

- Load private proposed take-profit and holding-horizon preferences into research reports, without authorizing any exit orders.
- Define price-return targets separately from fees/FX and flag the still-unagreed downside rule.


## 0.11.0 — 2026-11-06

- Run 30-minute research outside US market hours and continue public analysis with explicitly cached/unknown cash if Gateway is unavailable.
- Calculate 20/60/252-session annualized historical volatility for the full 100-stock watchlist, plus completed-session shocks against prior volatility; show sortable volatility columns.
- Keep Big Pickle primary and use DeepSeek V4.1 Flash via OpenRouter when unavailable; respect provider quota reset times and identify the actual model in reports.
- Refresh dashboard headlines each research cycle. If both models fail, publish clearly labelled calculated statistics rather than stale AI commentary.


## 0.10.10 — 2026-11-06

- Fix saved IBKR cash refresh failures caused by ib_async’s unconditional position synchronization during connection startup.
- Use a protocol handshake followed only by account-summary requests; preserve exact saved-account selection and Gateway read-only enforcement.


## 0.10.9 — 2026-11-06

- Let the research agent propose an unapproved, conditional rebound-entry idea for manual review, alongside a precise WAIT rationale.
- Compare panic-driven overshoot with fundamental repricing; separate execution checks from research conclusions and keep all order submission disabled.


## 0.10.8 — 2026-11-06

- Remove the IBKR account setup form and reuse the host’s saved account connection automatically.
- Load the first snapshot on opening the monitor; keep a single refresh action and preserve read-only access.
- Require the saved full account ID to match exactly, without choosing another account implicitly.


## 0.10.7 — 2026-11-06

- Feed OpenCode the dashboard’s existing news headlines, adjusted-price drawdowns and analyst ratings, targets and recent changes for six locally affordable research candidates.
- Track 20/60/252-session drawdowns and relative 20-session performance against SPY; preserve data sources, dates, partial coverage and unavailable fields.
- Show evidence coverage and linked news sources in the agent notebook; keep account data out of model prompts and preserve manual first-purchase review.


## 0.10.6 — 2026-11-06

- Redesign the IBKR monitor as a responsive research workspace with a cash summary, stock scan and agent notebook.
- Add ticker search, affordability/decline filters, sorting, session breadth and safe Markdown formatting for agent reports.
- Add light/dark controls, compact connection settings and background status refresh; preserve read-only broker behavior.


## 0.10.5 — 2026-11-06

- Add a read-only IBKR monitor with account-scoped cash and indicative whole-share affordability for a dated 100-stock S&P 500 watchlist.
- Show session moves, source timestamps, unknown prices and stale snapshots without presenting reference data as executable quotes.
- Add an optional 30-minute, market-session-gated OpenCode Big Pickle research runner with public-data-only prompts, tools denied and manual-review reports.
- Repair existing static-type errors in release-version parsing, Revolut date parsing and movement ID tracking without changing their normal behavior.
- Reserve estimated fees and exclude margin from the cash estimate; no position percentage cap, order submission or autonomous trading is enabled.


## 0.10.4 — 2026-11-02

- Treat crypto positions as direct holdings in distribution coverage, without missing constituent warnings.
- Fill missing MSCI World Quality ETF exposures (IE00BL25JL35) with a bundled 303-row official DWS holdings snapshot; preserve existing private fund rows.
- Register the fund's official holdings URL for future refreshes.

## 0.10.3 — 2026-11-02

- Support Italian Revolut consolidated CSV statements alongside regular account statements, including native-currency transactions and net savings interest.
- Ignore summaries and EUR conversion columns; preserve fees already included in cash amounts and mirror savings transfers to avoid reducing total cash.
- Discover consolidated statements in Downloads when Downloads scanning is enabled.

Notable changes to Portfolio Dashboard are documented here. The project follows
[Semantic Versioning](https://semver.org/) while it remains pre-1.0.

## 0.10.2 - 2026-10-18

### Fixed

- Align income/expense panel titles and wrap long recent-income descriptions.
- Accept Intesa booked statuses CONTABILIZZATO and CONTABILIZZATA.
- Allow portfolio-specific custom categories for bank and manual cash entries.
- Support a private per-portfolio payer policy separating credits from ordinary income, without publishing personal names.

## 0.10.1 - 2026-10-18

### Added

- Serve cached dashboard snapshots with background asynchronous refresh and gzip compression.
- Partial family rankings reporting per-portfolio availability when refreshing or temporarily unavailable.
- Stable transaction identity on fills to prevent dropping duplicate fills across imports.

### Fixed

- Reclassify refunds and reversals for BBVA and Trade Republic as credits rather than income.
- Balanced overview layout and deferred rendering for collapsed dashboard sections.

## 0.10.0 - 2026-10-18

### Added

- Edit imported transaction categories and subcategories without modifying bank
  records; optionally learn exact normalized merchant/source/direction rules.
- Apply rules to past and future matches while preserving individual overrides,
  or restrict a rule to future imports. Review and remove learned rules.
- Manual EUR cash ledger with income, expenses, cash transfers, editable entries,
  an opening balance and current balance, kept separate from investment returns.
- Search and progressively reveal imported transactions beyond the latest 30.
- Refresh income/expenses independently after edits, without refreshing prices.

### Fixed

- Bank cash withdrawals are transfers rather than spending, avoiding double
  counting when actual cash purchases are entered into the manual ledger.
- Categories cannot change a transaction's underlying income/expense direction.
- Main grid tracks shrink to the viewport, keeping dense tables from widening
  the page and displacing the cash editor on mobile.
- Expense category summaries and exports include spending only, and exports
  reload saved categories and manual cash entries instead of using stale snapshots.

## 0.9.1 - 2026-10-17

### Fixed

- Intesa's importer explicitly identifies native Lista_Operazioni XLSX files as
  bank income/expense statements, without creating investment trades.
- Intesa giroconti stay separate from income in either direction; bank-labelled
  incoming refunds and reversals are credits rather than earnings.
- A recipient's name in Intesa payment details no longer causes salary and
  third-party receipts to be discarded as own-account transfers.
- Added upload-to-ledger coverage for Intesa automatic detection, statement
  archiving, duplicate uploads, and separation from investment positions.

## 0.9.0 - 2026-10-17

### Added

- Expenses becomes Income & expenses, with income, spending, and their balance
  upfront plus a dedicated recent-income table using existing classified imports.
- Period-filtered monthly and cumulative charts compare income with expenses;
  cumulative balance shows income minus expenses. Investments, credits, and
  personal transfers remain separate from that balance.
- Expense categories, shares, merchants, and drilldowns now cover spending only;
  source breakdowns show income, expenses, investments, credits, and balance.

## 0.8.4 - 2026-10-17

### Fixed

- Closed import dialogs remain hidden while the dashboard loads or redraws.
  Loading effects no longer fade, blur, or disable modal dialogs.

## 0.8.3 - 2026-10-17

### Fixed

- Equivalent numeric formats such as `4` and `4.00` now deduplicate across
  imports and parser enrichment without rounding transaction values.
- Existing ledgers receive a backed-up, atomic migration retaining the earliest
  matching transaction and reconciling duplicate import counts. Portfolios and
  transactions with different fees or other financial fields remain distinct.

## 0.8.2 - 2026-10-17

### Fixed

- Fineco securities imports locate columns by header, supporting both the
  15-column and compact 12-column exports without losing commissions.
- Trades, dividends, and dividend-tax entries also support reordered columns
  and variable preambles; missing required columns produce a clear error.

## 0.8.1 - 2026-10-06

### Fixed

- Failed ISIN lookups retry after a 15-minute cooldown instead of permanently
  caching temporary Yahoo rate-limit and network errors for imported assets.

## 0.8.0 - 2026-09-24

### Added

- The options menu credits Leonardo and links to ellep.it.
- A top-bar update box appears when GitHub main has a newer version and shows
  the intervening release changelog. An opt-in, CSRF-protected update action
  queues a host-side Git merge and deployment, preserving local customizations
  and refusing conflicting or locally modified files.
- A restricted systemd updater for Pi installations stages only changed code,
  verifies startup, reports progress, and rolls back installed files if the new
  service fails its health check.

## 0.7.0 - 2026-09-24

### Added

- An equity-only, cash-flow-adjusted total-return line includes net dividends and
  compares with the EUR-traded accumulating MSCI World ETF over the same window.
  The equity gap and time/area ahead scores now use this line, independently of
  the portfolio Price/Total Return switch.
- Optional `benchmark_class` values `equity` or `other` in asset mappings let
  users correct inferred security classification for the equity comparison.
  Missing or unpriced equity history makes the comparison unavailable instead
  of presenting a misleading number.

## 0.6.9 - 2026-09-24

### Added

- The statement import dialog shows the latest import time for each platform
  with data in the selected portfolio.

### Fixed

- The selected-window comparison now shows the portfolio’s return gap against
  MSCI World in percentage points and both window returns, alongside clearly
  labeled time and area ahead percentages.
- Time-weighted portfolio returns retain intervals with buys and sells; only a
  change in quote coverage for the same number of holdings is excluded. This
  corrects understated returns when the portfolio added or closed positions.
- Current portfolio prices refresh through a background job while the existing
  dashboard remains available, with progress shown in the refresh button.
- Quote fetching, partial history repair, and cached valuation rebuilds keep
  current prices and historical performance in sync without forcing a full
  history download on each manual price refresh.

## 0.6.8 - 2026-09-02

### Fixed

- Historical valuation now rejects partial price caches that do not cover the
  requested timeline and fills the missing range when the provider is available.
  Stale partial data remains an offline fallback instead of masquerading as full
  history.
- Period performance uses cash-flow-adjusted, time-weighted returns. Changes in
  pricing coverage are excluded from performance, preventing a newly available
  quote from appearing as an investment gain.
- The MSCI World comparison is visible by default, and changing the timeline no
  longer replaces the accurate live headline value with a partial historical
  valuation.

## 0.6.7 - 2026-09-02

### Fixed

- Split-adjusted price caches now repair mixed overlapping ranges instead of
  applying the split factor twice to already-adjusted dates. Broker-recorded
  corporate actions also self-heal cached history, keeping mover percentages
  and euro changes consistent after a split.

## 0.6.6 - 2026-09-01

### Added

- A custom performance window with an editable start date. The selected window
  and date persist on the current device; private editions can provide a default.

### Performance

- Normal dashboard opens reuse the last computed payload from a persistent local
  cache. Explicit price refreshes rebuild it, and ledger or configuration changes
  invalidate it automatically.

## 0.6.5 - 2026-08-30

### Fixed

- Documented that opening balances omitted by cash-account exports belong in the
  private movement ledger, where they count as both cash and contributed capital.
  Account-specific values remain outside the public repository.

## 0.6.4 - 2026-08-30

### Added

- Per-browser automatic live-price refresh settings, defaulting to every 30
  minutes while the dashboard is open. Setting the interval to zero disables it.
- An opt-in refresh-on-login setting for users who prefer current prices despite
  the longer initial load on slower devices.

### Fixed

- Version discovery falls back to project metadata when an editable installation
  has an empty package-version record.

## 0.6.3 - 2026-08-18

### Fixed

- Fineco securities imports now record quantity-only corporate actions (free
  shares from a capital increase, splits, reverse splits). They adjust the
  position without touching the cost basis, so a split no longer reads as a
  large unrealized loss.
- Cached price history is back-adjusted for splits the price provider has not
  rebased yet, across the whole stored series rather than only the refetched
  window. Movers and period variations no longer report the split drop as a
  crash.
- Historical valuation and statistics series restate pre-split share counts, so
  a position is not valued at half its real size on every date before the split
  now that its price history is back-adjusted.
- ISIN lookups prefer a real venue ticker over the placeholder Yahoo lists an
  instrument under when no venue is indexed. Those placeholders carry no price
  history, which left the affected holdings unpriced.

## 0.6.2 - 2026-08-15

### Fixed

- Fineco trade settlements, dividends, income, and transfers are no longer sent
  to expense analytics. Fineco bank imports retain only actual spending,
  withdrawals, and explicit fees or taxes.

## 0.6.1 - 2026-08-15

### Added

- Native Fineco current-account XLSX detection and import alongside the existing
  Fineco securities workbook.
- Booked-movement validation, European number parsing, and bank-flow classification
  for Fineco fees, income, investments, transfers, withdrawals, and spending.
- Owner-only permissions for retained raw statement audit copies.

### Changed

- Onboarding and supported-input documentation now distinguish Fineco securities
  and current-account workbooks.

## 0.6.0 - 2026-08-15

### Added

- Guided first-run setup and browser/CLI statement imports.
- Native Personal trades CSV and XLSX templates.
- A portfolio-scoped SQLite movement ledger with import manifests and deduplication.
- Per-symbol history caches with migration from the legacy monolithic cache.
- Private-edition display suffixes such as `0.6.0L`.
- Public release documentation, MIT licensing, security guidance, and contribution
  instructions.

### Changed

- SQLite is now the canonical runtime source for imported movements.
- Routine dashboard loads use stale-while-refresh market caches; explicit price
  refreshes remain synchronous.
- Multi-portfolio rankings load after the selected dashboard and are hidden on
  single-profile installations.
- Approximate proxy compositions are opt-in on fresh installations.
- Public exposure and Berkshire reference data load without requiring a private
  `asset_exposures.csv` file.
- Fineco/BBVA tax reconstruction and the Sharpe risk-free rate are configurable.
- The public CI gate now checks Python and JavaScript syntax, scoped lint, package
  types, tests, design tokens, and distribution builds.

### Security and privacy

- Personal paths, portfolio adjustments, databases, statements, caches, and real
  contract snapshots remain outside version control.
- External services and the local-server trust boundary are documented explicitly.
