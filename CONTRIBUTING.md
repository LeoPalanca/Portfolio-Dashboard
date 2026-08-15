# Contributing

Thanks for improving Portfolio Dashboard. Bug reports and focused pull requests are
welcome, especially for additional statement formats, synthetic fixtures, privacy,
accessibility, and deterministic tests.

## Development setup

```bash
uv sync --dev
uv run pytest -q
uv run ruff check src run.py scripts/import_statements.py
uv run mypy src
uv run python scripts/lint_design_tokens.py --strict
node --check static/app.js
```

Run `python run.py --setup` to exercise fresh-install onboarding. Never use real
financial documents in tests or screenshots; build the smallest synthetic fixture
that proves the behavior.

## Statement adapters

- Keep platform detection and extension validation explicit.
- Normalize imported rows through the SQLite movement schema.
- Include deduplication and malformed-input tests.
- Document the exact native export and extension in `README.md`.
- Do not add personal filesystem paths, names, account numbers, or one-off portfolio
  adjustments to application code.

## Pull requests

Keep changes narrowly scoped and explain any data migration or external network
request. All checks above should pass. By contributing, you agree that your work is
licensed under the repository's MIT License.
