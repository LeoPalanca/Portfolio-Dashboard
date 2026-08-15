# Security policy

Portfolio Dashboard processes sensitive financial records. It is designed for one
user on a trusted computer and binds to `127.0.0.1` by default.

## Safe operation

- Do not expose the Flask development server to a LAN or the public internet. The
  application has no authentication, authorization, TLS termination, or multi-user
  isolation.
- Keep `config.toml`, statement archives, SQLite databases, exports, logs, caches,
  and local golden snapshots private. The repository ignores the standard paths,
  but files copied elsewhere remain your responsibility.
- Review generated XLSX and PDF reports before sharing them.
- Treat third-party statement files as untrusted input and stay on a supported
  version of Python and the locked dependencies.
- Crypto-wallet integrations are optional. Never commit API credentials or recovery
  phrases; use environment variables or another local secret store.

## Reporting a vulnerability

Please use GitHub's private vulnerability-reporting or security-advisory feature for
the repository. Do not include real statements, credentials, account identifiers, or
portfolio values in a public issue. A minimal synthetic reproducer is preferred.

Security fixes are made on the current development version. There is no guaranteed
support window for older releases while the project remains pre-1.0.
