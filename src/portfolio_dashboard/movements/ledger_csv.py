"""Read small user-written CSV files: account balances and manual cash entries.

Headers are matched without regard to case or surrounding spaces, English or Italian
("account"/"conto", "date"/"data", ...). The delimiter is a comma, semicolon or tab.
Every row that cannot be used is reported with its line number instead of guessed.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import date
from decimal import Decimal

from ..domain.money import parse_decimal_or_none

MAX_CSV_CHARACTERS = 1_000_000
MAX_CSV_ROWS = 10_000

BALANCE_COLUMNS = {
    "account": ("account", "conto", "rapporto"),
    "date": ("date", "data"),
    "balance": ("balance", "saldo"),
    "currency": ("currency", "valuta", "divisa"),
}
CASH_COLUMNS = {
    "date": ("date", "data"),
    "amount": ("amount", "importo"),
    "description": ("description", "descrizione"),
    "category": ("category", "categoria"),
    "subcategory": ("subcategory", "sottocategoria"),
}
DATE_PATTERNS = (
    re.compile(r"^(?P<year>\d{4})-(?P<month>\d{1,2})-(?P<day>\d{1,2})$"),
    re.compile(r"^(?P<day>\d{1,2})[/.-](?P<month>\d{1,2})[/.-](?P<year>\d{4})$"),
)


def parse_ledger_date(raw: str) -> date | None:
    text = (raw or "").strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}[T ]", text):
        text = text[:10]
    for pattern in DATE_PATTERNS:
        match = pattern.match(text)
        if match:
            try:
                return date(int(match["year"]), int(match["month"]), int(match["day"]))
            except ValueError:
                return None
    return None


def parse_ledger_amount(raw: str) -> Decimal | None:
    if not (raw or "").strip():
        return None
    value = parse_decimal_or_none(raw)
    if value is None or not value.is_finite() or abs(value) > Decimal(1000000000) or value != value.quantize(Decimal("0.01")):
        return None
    return value


def read_ledger_csv(
    text: str, columns: dict[str, tuple[str, ...]], required: set[str]
) -> tuple[list[tuple[int, dict[str, str]]], list[dict[str, object]]]:
    """``([(line, {column: value})], [problems])``; raises when the file itself is unusable."""

    if len(text) > MAX_CSV_CHARACTERS:
        raise ValueError("The CSV file is too large")
    text = text.lstrip("﻿")
    first = text.splitlines()[0] if text.strip() else ""
    delimiter = max(",;\t", key=first.count) if first else ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    header = next(reader, [])
    names = {" ".join(cell.split()).casefold(): index for index, cell in enumerate(header) if cell.strip()}
    positions = {
        column: next((names[alias] for alias in aliases if alias in names), None) for column, aliases in columns.items()
    }
    absent = sorted(column for column in required if positions[column] is None)
    if absent:
        raise ValueError(f"The CSV header must name the columns: {', '.join(sorted(required))} (missing {', '.join(absent)})")
    rows: list[tuple[int, dict[str, str]]] = []
    problems: list[dict[str, object]] = []
    for line, cells in enumerate(reader, start=2):
        if not any(cell.strip() for cell in cells):
            continue
        if len(rows) >= MAX_CSV_ROWS:
            raise ValueError(f"The CSV file has more than {MAX_CSV_ROWS} rows")
        if len(cells) > len(header):
            problems.append({"line": line, "reason": "more cells than header columns (quote amounts with a decimal comma, or use ';')"})
            continue
        rows.append(
            (line, {column: cells[index].strip() if index is not None and index < len(cells) else "" for column, index in positions.items()})
        )
    return rows, problems
