"""Problems found while parsing one statement, so an import can refuse or warn.

Parsers call :func:`report_import_issue`; it does nothing unless an import is
collecting issues with :func:`collect_import_issues`, so the same parsers keep
their lenient behaviour when the dashboard reads data outside an import.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

UNREADABLE_NUMBER = "number"
MISSING_FX_RATE = "fx"
SKIPPED_ROW = "row"
BLOCKING_KINDS = frozenset({UNREADABLE_NUMBER, MISSING_FX_RATE})
EXAMPLE_LIMIT = 3


@dataclass
class ImportIssues:
    entries: dict[str, list[str]] = field(default_factory=dict)

    def add(self, kind: str, detail: str) -> None:
        self.entries.setdefault(kind, []).append(detail)

    @property
    def blocking(self) -> bool:
        return any(kind in self.entries for kind in BLOCKING_KINDS)

    def blocking_message(self) -> str:
        parts = []
        numbers = self.entries.get(UNREADABLE_NUMBER, [])
        if numbers:
            parts.append(f"{_count(numbers, 'value')} could not be read as a number ({_examples(numbers)})")
        rates = self.entries.get(MISSING_FX_RATE, [])
        if rates:
            parts.append(
                f"no EUR exchange rate was available for {_count(rates, 'row')} ({_examples(rates)}); "
                "try again when market data is reachable"
            )
        return "Nothing was imported: " + "; ".join(parts) + "."

    def warnings(self) -> list[str]:
        rows = self.entries.get(SKIPPED_ROW, [])
        if not rows:
            return []
        return [f"{_count(rows, 'row')} skipped: {_examples(rows)}"]


def _count(items: list[str], noun: str) -> str:
    return f"{len(items)} {noun}{'' if len(items) == 1 else 's'}"


def _examples(items: list[str]) -> str:
    unique = list(dict.fromkeys(items))
    shown = "; ".join(unique[:EXAMPLE_LIMIT])
    return shown + (f"; and {len(unique) - EXAMPLE_LIMIT} more" if len(unique) > EXAMPLE_LIMIT else "")


_ACTIVE: ContextVar[ImportIssues | None] = ContextVar("portfolio_import_issues", default=None)


@contextmanager
def collect_import_issues() -> Iterator[ImportIssues]:
    issues = ImportIssues()
    token = _ACTIVE.set(issues)
    try:
        yield issues
    finally:
        _ACTIVE.reset(token)


def report_import_issue(kind: str, detail: str) -> None:
    issues = _ACTIVE.get()
    if issues is not None:
        issues.add(kind, detail)
