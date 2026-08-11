# Portfolio Dashboard

A local-first finance dashboard that consolidates brokerage exports, cash-account
statements, crypto wallets, and snapshot portfolios. It provides current holdings,
historical valuation, total-return statistics, look-through exposure, expense
classification, frictions, news, and XLSX/PDF exports.

Personal financial data is deliberately kept outside the repository. The application
loads local paths and portfolio profiles from environment variables or an ignored
`config.toml` file.

## Requirements

- Python 3.11 or newer (Python 3.13 is the primary development target)
- [`uv`](https://docs.astral.sh/uv/) for dependency management
- `pdftotext` when importing Interactive Brokers PDF confirmations

## Install and run

The guided launcher installs the locked environment, creates private directories
outside the repository, offers to import statements, starts the server, and opens
the browser:

```bash
python run.py
```

Useful non-interactive variants are:

```bash
python run.py --setup
python run.py --import /path/to/statement.csv --setup
python run.py --port 8051 --no-browser
```

The manual workflow remains available:

```bash
uv sync
cp config.example.toml config.toml
# Edit config.toml so its paths point to directories outside this repository.
uv run python app.py
```

Open `http://127.0.0.1:8050`.

The existing helper remains available for local background operation:

```bash
./dashboard.sh start
./dashboard.sh status
./dashboard.sh logs
./dashboard.sh stop
```

## Configuration and privacy

`config.example.toml` documents the supported settings. The important filesystem
boundaries are:

- `source_dir`: broker and cash-account exports.
- `data_dir`: private mappings, wallet snapshots, expense rules, watchlist, and
  portfolio-specific derived data.
- `cache_dir`: disposable price, history, news, watchlist, and CPI caches.

The top-bar `Import data` action accepts CSV, XLS, XLSX, and PDF statements. It
detects the institution when possible, preserves the raw file under `source_dir`,
and writes deduplicated normalized events plus an import manifest to
`data_dir/movements.sqlite3`. The same pipeline is available from
`scripts/import_statements.py`; `run.py --import` is the recommended CLI entry.

Automatic discovery in `~/Downloads` is disabled by default. Existing installations
that rely on it can explicitly set `scan_downloads = true` in private configuration.

Historical prices are stored as one compact merged JSON file per symbol under
`cache_dir/history/`. On first use, installations with the former monolithic
`history.json` cache migrate it automatically and archive the original under
`cache_dir/legacy/`.

Environment variables use the `PORTFOLIO_` prefix and override TOML values. For
example:

```bash
export PORTFOLIO_DATA_DIR=/path/to/private-data
export PORTFOLIO_CACHE_DIR=/path/to/cache
```

The following private filenames are expected inside `data_dir` when the associated
feature is used:

```text
asset_mappings.csv
asset_exposures.csv
crypto_wallets.csv
crypto_wallet_positions.csv
crypto_wallet_transactions.csv
expense_category_rules.csv
watchlist.json
```

They are ignored by Git even if accidentally copied back into the repository. Local
`config.toml`, caches, logs, statement backups, and real-data contract snapshots are
also ignored.

Public market reference data stays under `data/`, including Berkshire holdings,
issuer-document metadata, and proxy exposure compositions.

## Input discovery

Broker discovery patterns are configurable. The parsers currently support:

- Trade Republic CSV exports
- Fineco workbooks
- Interactive Brokers PDF confirmations
- eToro account-statement workbooks
- Revolut account-statement CSVs
- Intesa account-operation workbooks
- BBVA account workbooks
- Manual trade CSV fallback
- Configured snapshot portfolios

Each non-primary portfolio is declared under a `[portfolios.<id>]` TOML table. A
profile can specify its display name, snapshot pattern, history start, transaction
adjustments, friction events, tax-loss metadata, and private action items. These
details remain in ignored local configuration rather than application code.

## Expense classification

Rules are evaluated by ascending priority; the first enabled match wins. The schema
is:

```text
priority,enabled,source,match_field,match_type,pattern,category,subcategory,merchant
```

`source` may target one importer or use `all`. Match types are `contains`, `exact`,
and `regex`. A synthetic starter file is provided at
`data/expense_category_rules.example.csv`; copy and customize it in the external
`data_dir`.

Refunds and cashback are represented as income. Transfers, investments, credits,
cash withdrawals, fees, and spending remain separate flows so the expense summary
can reconcile net outflow without treating every account movement as consumption.

## Holdings and exposure data

`asset_mappings.csv` maps imported names or ISINs to pricing symbols. Optional
columns include `Ticker` and `Borsa`; exchange hints are used when constructing
Yahoo Finance symbols.

`asset_exposures.csv` provides the look-through split for direct shares, ETFs, and
funds:

```text
asset_name,isin,holding_name,holding_ticker,weight_pct,sector,geo,asset_class
```

Official compositions take precedence. `data/proxy_exposures.csv` fills unresolved
or partial products only when Proxy mode is enabled.

The manual ETF refresh tool can inspect current positions and update issuer-sourced
compositions:

```bash
uv run python etf_fetcher.py list-targets
uv run python etf_fetcher.py update --official-only --dry-run --offline
uv run python etf_fetcher.py update --official-only
```

## Verification

Run the project checks with:

```bash
/opt/anaconda3/bin/python3 -m compileall -q .
/opt/anaconda3/bin/python3 -m unittest discover -s . -p 'test*.py'
```

The test suite uses synthetic fixtures. For local refactors, the contract snapshot
tool can also capture canonicalized real-data API responses into the ignored
`tests/golden/local/` directory:

```bash
/opt/anaconda3/bin/python3 scripts/snapshot_local_api.py --skip-news
```

Never commit that directory: its payloads contain real portfolio figures.

## Development status

The application is being migrated incrementally from a single-file Flask app to a
typed `src/portfolio_dashboard` package. The safety and privacy boundary is in place;
structural extraction and the planned FastAPI API layer follow as separate stages so
behavior changes remain attributable and testable.
