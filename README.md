# Portfolio Dashboard

A local-first dashboard for turning broker, bank, wallet, and portfolio exports into
one private view of holdings, performance, income, spending, and investment costs.

Your statements and normalized SQLite ledger stay on your computer. The repository
contains application code, synthetic tests, and public reference data—not your
financial records.

> [!IMPORTANT]
> Portfolio Dashboard is an independent personal-analysis tool, not financial, tax,
> or investment advice. Verify imported figures against the original statements
> before making decisions.

## What it does

- Imports supported CSV, XLS, XLSX, and PDF statements from the browser or CLI.
- Normalizes trades, dividends, taxes, fees, interest, expenses, and cash movements
  into a deduplicated SQLite ledger.
- Calculates holdings, realized and unrealized P/L, historical valuation, total
  return, volatility, drawdown, and benchmark comparisons.
- Shows dividends, cash interest, expenses, contributions, tax and fee drag, and
  look-through portfolio exposure.
- Supports multiple locally configured portfolios; rankings appear only when more
  than one profile exists.
- Exports dashboard tables to XLSX or PDF.
- Uses cache-first market data so routine loads do not wait for network refreshes.

The current reporting currency is EUR. Instruments and transactions denominated in
currencies such as USD and CHF are converted when the relevant importer and FX price
history provide enough information. Selectable USD/CHF base reporting is not yet
supported: API fields and exports ending in `_eur` are always EUR values.

## Quick start

Requirements:

- Python 3.11 or newer
- [`uv`](https://docs.astral.sh/uv/) (the guided launcher can install it with `pip`)
- `pdftotext` only for Interactive Brokers PDF confirmations

Clone the repository and run the guided launcher:

```bash
git clone https://github.com/LeoPalanca/portfolio-dashboard.git
cd portfolio-dashboard
python run.py
```

The launcher installs the locked environment, creates private directories, offers
to import statements, starts the server on `http://127.0.0.1:8050`, and opens a
browser. On a fresh install, the default private root is `~/PortfolioDashboard`.

Useful variants:

```bash
python run.py --setup
python run.py --import /path/to/statement.csv --setup
python run.py --import /path/to/statement.xlsx --portfolio household_a --setup
python run.py --port 8051 --no-browser
```

The manual workflow is also available:

```bash
uv sync
cp config.example.toml config.toml
# Edit config.toml so all private paths point outside this repository.
uv run python app.py
```

For local background operation:

```bash
./dashboard.sh start
./dashboard.sh status
./dashboard.sh logs
./dashboard.sh stop
```

### Optional GitHub update control

The top bar checks GitHub main for a newer semantic version and displays the
new release notes. The check does not modify local files. The **Install update**
button is disabled unless `auto_update_enabled = true` is configured and the
restricted host-side updater is installed. Do not enable it on an exposed,
unauthenticated web deployment; the app is intended to remain loopback-only.

For the Pi systemd deployment, the updater uses a separate Git checkout at
`/opt/portfolio-dashboard-source`. Commit any Pi-only code customizations on
that checkout's local branch before enabling updates, and write its deployed
commit hash to `/var/lib/portfolio-dashboard/update/deployed-head`. Install
the two units in `deploy/systemd/`, enable `portfolio-dashboard-update.path`,
and set `PORTFOLIO_AUTO_UPDATE_ENABLED=true` for the dashboard service. The
updater merges GitHub main, refuses conflicts or drift in installed code,
copies only changed tracked files (never private `data/` or `config.toml`),
and restarts the service with rollback on a failed startup.

## Supported inputs

Platform exports are not interchangeable. Select the matching source and use the
platform's native export; renaming or converting a file does not make its workbook
layout compatible.

| Source | Supported input | Notes |
| --- | --- | --- |
| Trade Republic | CSV | Account/activity export |
| Fineco | XLSX | Securities workbook or current-account `Movimenti` export; investment settlements, dividends, income, and transfers are excluded from expenses |
| Interactive Brokers | PDF | Trade-confirmation report; requires `pdftotext` |
| eToro | XLSX | Account-statement workbook |
| Revolut | CSV | Account statement or Italian consolidated statement, including native-currency transactions and net savings interest |
| Intesa | XLSX | Account-operations workbook |
| BBVA | XLS | Account workbook |
| Personal trades | CSV or XLSX | Header-based template available during onboarding |
| Snapshot portfolio | CSV | Declared in a local portfolio profile |

The import dialog detects a source when possible, validates the extension and
expected headers or sheets, retains an audit copy under `source_dir`, and writes
normalized movements to `data_dir/movements.sqlite3`. The same pipeline is available
through `python run.py --import ...` and `scripts/import_statements.py`.

### Personal trade template

CSV and XLSX templates use this schema:

```text
date,action,asset,isin,broker,currency,quantity,price,fees,tax,total
```

`date`, `action`, `asset`, `quantity`, and `price` are required. Dates use
`YYYY-MM-DD`; actions are `BUY` or `SELL`; quantity and price must be positive. ISIN,
broker, currency, fees, tax, and total are optional. `total` is the absolute cash
value and is calculated when omitted. The former positional 17-column personal CSV
remains supported for existing installations.

## Data model and filesystem boundaries

`config.example.toml` documents the available settings. The main private locations
are:

- `source_dir`: retained broker and cash-account exports.
- `data_dir`: `movements.sqlite3`, mappings, wallet data, classification rules,
  watchlist, and portfolio-specific data.
- `cache_dir`: disposable prices, history, news, watchlist, and CPI caches.

SQLite is the canonical runtime source for imported movements. Statements are not
reparsed on every dashboard refresh. Older installations are imported into SQLite
once; version-1 ledgers are migrated in place and assigned to the configured primary
portfolio. Imports and deduplication are scoped by portfolio.

Automatic scanning of `~/Downloads` is disabled on fresh installations. Existing
users can opt in with `scan_downloads = true`.

These optional private files are read from `data_dir`:

```text
asset_mappings.csv
asset_exposures.csv
crypto_wallets.csv
crypto_wallet_positions.csv
crypto_wallet_transactions.csv
expense_category_rules.csv
watchlist.json
```

The repository ignores local configuration, SQLite files, caches, logs, statement
backups, and real-data contract snapshots. Keep private paths outside the clone as an
additional boundary.

### Portfolio profiles and private editions

Additional portfolios are declared under `[portfolios.<id>]` in ignored
`config.toml`. A profile can define a display name, snapshot pattern, history start,
transaction adjustments, friction events, tax-loss metadata, private action items,
and opt-in features.

The Custom performance window has an editable start date in Dashboard Settings.
Both the chosen window and date persist in the browser. A private installation can
provide its initial date with `default_custom_period_start = "YYYY-MM-DD"`; public
installations have no account-specific default.

If a private cash-account export begins after the account was funded, record the
missing opening balance as a dated `cash_flow` in that edition's private movement
ledger. Its amount and `contribution_change` must match so market value and return
use the same capital basis. Account names, dates, and amounts must not be hardcoded
or committed to the public edition.

The package version follows semantic versioning, for example `0.6.0`. A private
installation can add a display-only marker without forking package metadata:

```toml
edition_suffix = "L"
```

That installation displays `0.6.0L`; fresh/public installations display `0.6.0`.
Personal paths, adjustments, and feature flags remain in ignored configuration.

## Market data, network access, and caches

Routine dashboard loads reuse the last computed local snapshot, including across
service restarts. A statement import, configuration change, or other source-data
change invalidates the snapshot. `Refresh Prices` performs a synchronous market
update and replaces it. Depending on the enabled feature, the application may contact:

- Yahoo Finance through `yfinance` for prices, currency metadata, benchmarks, and
  Yahoo RSS headlines.
- Eurostat for euro-area HICP inflation data.
- Coinbase public market endpoints for supported crypto conversion history.
- Parqet's image host directly from the browser for optional security logos; the
  requested symbol or ISIN is visible to that service.
- Fund issuers and reference sites only when the manual ETF composition updater is
  run.
- Coinbase, BNB Chain, or TON endpoints only when optional wallet tools are run.

No analytics or telemetry service is included. External data can be incomplete,
delayed, rate-limited, or revised. Cached market data is stored under `cache_dir` and
can be deleted without losing the movement ledger.

Historical prices use one compact merged JSON file per symbol. Installations with
the former monolithic `history.json` cache migrate it automatically and archive the
original under `cache_dir/legacy`.

## Holdings and exposure data

`asset_mappings.csv` maps imported names or ISINs to price symbols. Optional `Ticker`
and `Borsa` columns provide exchange hints for Yahoo Finance symbol construction.
For the equity-only MSCI comparison, an optional `benchmark_class` column can be
set to `equity` or `other` per asset; otherwise the dashboard infers the class
from exposure data and the asset name. Review the mapping for ambiguous funds.
The comparison uses invested equity values, purchase/sale cash flows and net
dividends; it excludes idle cash and cash interest. It is shown only when every
equity valuation in the selected window has price coverage. The MSCI proxy is
the accumulating SWDA.MI ETF (or EUNL.DE fallback), both quoted in EUR.

`asset_exposures.csv` supplies look-through data for direct shares, ETFs, and funds:

```text
asset_name,isin,holding_name,holding_ticker,weight_pct,sector,geo,asset_class
```

Official compositions take precedence. The checked-in `data/proxy_exposures.csv`
contains curated, modelled, and in some cases synthetic compositions used only to
fill missing or partial products. Proxy mode is **off by default** on fresh installs.
When enabled, proxy results are approximations for visualization—not issuer data and
not suitable for trading, compliance, or tax decisions.

The manual updater can inspect positions and refresh issuer-sourced compositions:

```bash
uv run python etf_fetcher.py list-targets
uv run python etf_fetcher.py update --official-only --dry-run --offline
uv run python etf_fetcher.py update --official-only
```

## Expense classification

Rules are evaluated by ascending priority; the first enabled match wins:

```text
priority,enabled,source,match_field,match_type,pattern,category,subcategory,merchant
```

`source` can name one importer or `all`. Match types are `contains`, `exact`, and
`regex`. Copy `data/expense_category_rules.example.csv` into the external `data_dir`
and customize it.

Refunds and cashback are income. Transfers, investments, credits, withdrawals,
fees, and spending remain separate flows so net outflow is not treated as pure
consumption.

## Assumptions and limitations

- The server is a local Flask development server with no login, authorization, TLS,
  or multi-user isolation. Never bind it to a public or untrusted interface.
- Reporting is EUR-first. Eurostat supplies euro-area inflation, and some labels and
  benchmark choices reflect that reporting context.
- When a supported Fineco or BBVA export provides a net amount without explicit tax,
  the importer reconstructs gross and tax using configurable 26% defaults
  (`fineco_withholding_tax_rate` and `bbva_interest_tax_rate`). Adjust them for the
  relevant tax residence, instrument, and account treatment, then verify locally.
- Market prices, FX conversion, news, mappings, and proxy compositions are best-effort
  data and may be stale or unavailable.
- Selected-window returns are linked across available valuation dates and adjust
  external flows at those dates. They approximate, rather than exactly reproduce,
  daily time-weighted returns when intra-period trade timing is unavailable.
- Snapshot portfolios cannot provide transaction-level accuracy for periods before
  the supplied history and adjustments.

See [SECURITY.md](SECURITY.md) for handling and deployment guidance.

## Verification

```bash
uv sync --dev
uv run python -m compileall -q app.py run.py src scripts
uv run pytest -q
uv run ruff check src run.py scripts/import_statements.py
uv run mypy src
uv run python scripts/lint_design_tokens.py --strict
node --check static/app.js
```

Tests use synthetic fixtures. The optional contract snapshot tool writes canonical
real-data responses to the ignored `tests/golden/local/` directory:

```bash
uv run python scripts/snapshot_local_api.py --skip-news
```

Never commit that directory; its payloads contain real portfolio figures.

## Project status

Version 0.6 is a beta release. The importer, SQLite ledger, dashboard, onboarding,
and exports are functional, while the internal application is being modularized from
the legacy Flask module. Backward compatibility may change before 1.0 and migrations
will be documented in release notes.

Contributions are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md). Security guidance
is in [SECURITY.md](SECURITY.md), and release notes are in
[CHANGELOG.md](CHANGELOG.md).

## License

Released under the [MIT License](LICENSE).

## IBKR research monitor

Open **IBKR research** in the header (`/ibkr`). It uses the account already saved
on the dashboard host. No account suffix or session selection is required in the
browser. If no snapshot exists, the page requests one automatically; use
**Refresh snapshot** for subsequent checks.

The bridge loads its private `account_config.json` from its working
directory, or the file named by `IBKR_CONNECTION_CONFIG`. That file contains the
previously selected full account ID and Gateway endpoint. It must already exist;
missing configuration never falls back to the first accessible account. The
saved full ID must match an accessible account exactly. Only a masked suffix is
returned to the dashboard.

For research, keep Gateway logged in with **Read-Only API** enabled and reachable at
`127.0.0.1:4001` (live) or `127.0.0.1:4002` (paper) on the dashboard host.
An SSH reverse tunnel can forward that loopback port from Gateway on another machine.
Run the loopback bridge on the dashboard host using an environment
with `ib_async==2.1.0` (`uv sync --extra ibkr` for a new installation):

```sh
python scripts/ibkr_cash_bridge.py
```

The bridge binds to `127.0.0.1:8766`. It uses the protocol handshake directly to avoid ib_async 2.1.0’s unconditional
position synchronization on the cash endpoint, which makes only account-summary
requests and returns a masked suffix and cash totals. Manual order endpoints are
separate and disabled by default (see version 0.12 below). The
dashboard itself needs no new runtime dependency, so existing code-only app
updates remain compatible. Keep this port on loopback; no public listener is needed.

**Refresh snapshot** runs a background snapshot. The stock scan supports ticker
search, All/Within budget/Declining filters and sorting by decline, price or ticker.
Cash, account equity, snapshot age and watchlist breadth remain visible beside the
formatted agent notebook. Light/dark selection follows the main dashboard theme.
Reports refresh in the browser without requesting new broker snapshots.

The snapshot compares the lower of TotalCashValue and AvailableFunds (clamped at zero) with Yahoo Finance reference
prices and reference FX. It is an indicative affordability check, not a verification
of settled USD cash or an order preview. Each purchase estimate reserves USD 1;
actual fees, FX, spread and sale costs vary. Fractional eligibility is unverified.
The 10% position cap is not applied.

The bundled 100-security universe is a dated market-cap research list sourced from
[Slickcharts](https://www.slickcharts.com/sp500/marketcap), including separate share
classes. It is not the S&P 100 index and is not refreshed automatically. Quotes
more than four days old, missing quotes and missing FX yield unknown affordability.
Snapshots older than 30 minutes are marked stale. Latest reference data may be a
previous session close; session changes are not executable entry signals.

Snapshots are written to private `data_dir/ibkr_monitor.json` with mode 0600. Only
a masked account suffix is retained. Public price requests contain stock/FX symbols
and no account identifier or balance. Dashboard status GETs do not contact IBKR. Refresh
POST requests require a page token and same-origin browser request.

### Optional OpenCode research on the dashboard host

`scripts/ibkr_research.py` collects the reference universe through the local cash
bridge when available, then runs standard OpenCode with Big Pickle primary and
DeepSeek Flash/OpenRouter fallback, a private server and tools denied. Only public
price/history/news/analyst evidence and eligibility freshness metadata enter the model
prompt: account identity, holdings, cash and quantities are excluded. Provider
processing of those public prompts follows the OpenCode provider's own terms.

Copy and customize the example units under `deploy/systemd/user/`. The timer wakes
every 30 minutes, including outside regular US market hours using explicitly dated
closing/reference data. Missing session metadata is labelled unknown and does not
stop public research; this is not an authoritative exchange calendar.
A systemd oneshot unit prevents overlapping scheduled runs. Use
`--review-last-session` for an explicit off-hours research report, never for trading.

Set the bridge's `IBKR_RESEARCH_STATE` to the research script's `--state-dir` (default
`research` relative to the bridge working directory). The dashboard reads its latest
report from the fixed loopback `/analysis` endpoint. Model commentary is unverified,
and old reports are labelled by completion time. Reports and OpenCode session data
remain on the dashboard host. Research has no order approval or execution tools.

The first purchase still requires a review of the reason for the drop, current
broker bid/ask, quantity, limit, actual cost preview and exit rules, followed by
manual confirmation in the separate order desk. Keep Gateway read-only until the
manual execution setup below has been reviewed.

### Evidence for the research agent

The research runner uses the dashboard's existing `/api/news?symbols=...` feed
with an explicit list, so it never falls back to private portfolio holdings. Set
`--dashboard-url http://HOST:8050` if the dashboard uses a private interface instead
of localhost. Public headlines retain source links, publication dates and the
dashboard cache's generated timestamp. Only headline content is fetched; neither
the collector nor the model has verified the full articles.

For the six largest session declines that fit local cash, the collector adds
split/dividend-adjusted daily history, drawdown from 20/60/252-session highs, worst
peak-to-trough drawdown inside each window, 5/20-session returns and relative
20-session performance against SPY when the last bar dates match. The newest daily
bar may be partial during trading. History windows with insufficient observations
remain unknown. The 100-stock table still provides the broader price context.

Yahoo/yfinance supplies analyst consensus, Buy/Hold/Sell counts, low/mean/median/high
price targets, up to five dated rating changes and available valuation ratios.
Retrieval dates are not issue dates: summary rating/target issue dates are unknown
unless supplied separately. Targets are provider consensus, typically long-horizon,
and are not short-term exit prices or guaranteed returns. Partial lookups stay
partial and failed lookups stay unavailable.

The isolated research environment needs the dashboard's existing `yfinance`
dependency as well as its IBKR dependency. Evidence collection is bounded to 240
seconds in a child process. Timeout/failure gives the model no verified candidate
list and a WAIT instruction. Raise the example research service timeout to 720
seconds to cover collection plus model response. The agent receives public evidence
only, delimited as untrusted data with source IDs; tool permissions remain denied.
Reports include structured coverage and source links for manual verification.

Research reports may now conclude `BUY_PROPOSAL` or `WAIT`. A BUY_PROPOSAL is an
unapproved research draft: one candidate, cited thesis, conditional entry, holding
horizon, downside/invalidation and exit logic. Numeric levels must be supported
by supplied evidence; missing levels and risk parameters require manual agreement.
Missing broker quotes or cost previews block execution, without forcing every
research conclusion to WAIT. A WAIT report must identify a decision-critical
blocker, an observable change condition and a next review point. The agent weighs
panic-driven overshoot against fundamental repricing and does not have to agree
with a desire to buy. No execution endpoint or autonomous trading is added.

### Continuous research, volatility and model fallback

The 30-minute timer runs research at night and on closed-market days too. Yahoo’s
regular-session interval labels the run as regular, closed or unknown; it no longer
skips outside hours. This does not authorize orders. News is refreshed through the
existing dashboard endpoint each cycle.

Volatility covers all 100 dated-universe stocks, including those outside the cash
budget. It is the sample standard deviation of adjusted daily log returns, multiplied
by sqrt(252) and 100, over 20/60/252 completed sessions. A known unfinished session
is excluded. Last-close sigma compares the last completed return with its prior
20 returns, excluding the return being assessed. Zero variance and insufficient
history stay unknown where a ratio cannot be calculated. These are historical
variability measures, not implied volatility, normal-distribution probabilities or
rebound forecasts. The notebook receives the complete scan and six deeper news/analyst
checks; the table adds annualized 20-session volatility and last-close sigma.

A private account-scoped cash cache supports research if the Mac/Gateway disconnects.
Cached cash is labelled cached and never verifies current buying capacity. Without
a cache, public market research still runs and affordability is unknown. Broker
refresh on the dashboard itself continues to require a fresh broker response.

Standard OpenCode uses Big Pickle first and falls back to
`openrouter/deepseek/deepseek-v4.1-flash-1017`, using the existing OpenRouter
authentication. The fallback consumes OpenRouter credits. Provider quota retry times
are persisted privately so exhausted Big Pickle calls are not repeated every cycle;
the primary is retried after expiry. Reports identify the actual model and fallback
status. Tool permissions remain denied for both models. If neither model responds,
the report explicitly contains calculated statistics only; no new AI conclusion is
claimed. The last successful AI report is retained separately in `last_ai_report.json`.
Use a 720-second systemd timeout for collection plus model attempts.

Proposed exit preferences can be stored privately in the research state directory's
`strategy.json`, with `take_profit_pct`, `take_profit_basis` set to
`entry_price_before_costs`, and `max_holding_months`. Only these whitelisted
preferences enter the model prompt. The target is actual entry multiplied by
(1 + percentage/100) in the trade currency, before costs. It is a planning objective,
not a forecast or an active sell order. Fees, spread, FX and tax effects remain
separate. No loss limit is inferred, and `execution_authorized` remains false
regardless of the file's contents.

### Manual analysis, stock chat and first-order execution (0.12)

The IBKR page has **Run analysis now** and a ticker-specific research chat. Both
use the standard OpenCode runner, Big Pickle first and the configured DeepSeek
Flash fallback. Requests collect fresh public evidence. A stock conversation does
not replace the 100-stock report. Jobs serialize with scheduled research; keep the
page open to receive the result. Closing the page does not cancel the job. Model
tools remain denied and neither news nor chat can authorize an order.

The private strategy now records `loss_policy: "hold_for_now"`: no automatic
stop-loss or liquidation at the 12-month research horizon. Review deteriorating
theses manually. This preference does not itself authorize broker orders.

**Preview with IBKR → review → confirm purchase** is a separate, human-controlled
first-order flow. It supports whole shares of watchlist USD stocks, regular hours,
DAY limit buys, and one attached GTC limit profit sell. The profit price is rounded
up to the contract minimum tick at 115% of the **buy limit**. A lower actual entry
therefore increases the gross percentage return. This is before commissions, FX
and taxes; there is no stop order. Partial fills, rejected orders, manual position
changes and the validity/expiry of a GTC order require supervision in IBKR.

Submission rechecks the saved exact account, qualified USD stock, broker liquid
hours, real-time bid/ask (maximum age 10 seconds), spread, current positions,
account open orders, USD cash and settlement, available funds and a broker what-if
commission estimate. It blocks existing positions and any account open orders.
There is no margin, automatic currency conversion or fractional-share assumption.
Missing broker fields fail closed. A preview expires after 60 seconds and its token
is single-use. Browser edits invalidate the visible preview. The confirmed draft
comes from server memory and all broker checks run again before transmission.

The bridge persists a private, fsynced order intent **before** transmitting, sends
the parent with `transmit=False`, then the profit child with `transmit=True`.
Acknowledgement means receipt, not a fill or guaranteed profit. Exceptions or
uncertain broker states require review; they never trigger an automatic retry.
Only one purchase intent is supported in this first-order release. After an order
has been submitted, reconcile parent, child, fills and positions in IBKR before an
operator archives the intent and permits another purchase. Do not simply delete
an unresolved intent. Manage/cancel submitted orders in IBKR. Autonomous entries
remain disabled.

Deployment: copy `scripts/ibkr_orders.py` alongside `ibkr_cash_bridge.py` in the
bridge directory, and update the isolated `research_source` runner/modules too.
The bridge service needs writable `research/`, `orders/` and OpenCode runtime
directories, as shown in its service example; create these directories first. Set
`IBKR_DASHBOARD_URL` to the existing dashboard address so jobs reuse its news feed.
Execution defaults off: the private connection config must explicitly contain
`execution_enabled: true` and `read_only: false`, and Gateway's **Read-Only API**
must be disabled by the account owner before a live preview can work. Keep both
settings off until the implementation and order flow are reviewed. This release
does not activate live trading or send an order during installation. For a paper
account, use the saved paper endpoint and its own account; never infer accounts.

The bridge remains loopback-only, with fixed endpoint proxies, JSON bounds,
host/origin checks and dashboard same-origin CSRF tokens. Broker errors are
redacted. Protect access to the dashboard itself: users who can open the page
can obtain its action token. The broker SDK is still isolated and optional; the
main app needs no new dependency.

### Berkshire 13F reference

BRK look-through uses `resources/berkshire_holdings.csv`, bundled with app updates.
The current snapshot covers June 30, 2026 (filed August 14), accession
`0001193125-26-352200`: 89 SEC rows aggregated by CUSIP into 29 securities,
with reported equity value of $299,253,556,246. The legacy CSV column
`value_usd_thousands` stores the filing’s dollar values for this snapshot.
The existing model allocates 40% to disclosed equities, 30% to cash/short-term
Treasuries and 30% to operating businesses; the latter two are assumptions,
not figures disclosed by the 13F. The old data-directory reference is no longer used.
