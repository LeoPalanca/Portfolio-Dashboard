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
| Revolut | CSV | Account statement, including supported foreign-currency rows |
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

Routine dashboard loads are cache-first. `Refresh Prices` performs a synchronous
market update. Depending on the enabled feature, the application may contact:

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
