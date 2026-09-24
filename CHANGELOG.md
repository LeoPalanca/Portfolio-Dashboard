# Changelog

Notable changes to Portfolio Dashboard are documented here. The project follows
[Semantic Versioning](https://semver.org/) while it remains pre-1.0.

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
