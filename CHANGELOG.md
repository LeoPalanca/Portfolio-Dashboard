# Changelog

Notable changes to Portfolio Dashboard are documented here. The project follows
[Semantic Versioning](https://semver.org/) while it remains pre-1.0.

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
