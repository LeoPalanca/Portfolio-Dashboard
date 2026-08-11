"""Decimal parsing and JSON-boundary conversion helpers."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation


EUR = Decimal("1")
ZERO = Decimal("0")


def parse_decimal(value: str | None) -> Decimal:
    raw = (value or "").strip()
    if not raw:
        return ZERO
    raw = raw.replace("EUR", "").replace("$", "").replace(" ", "")
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    try:
        return Decimal(raw)
    except InvalidOperation:
        return ZERO


def decimal_to_float(value: Decimal) -> float:
    if not value.is_finite():
        return 0.0
    return float(value.quantize(Decimal("0.0001")))


def money(value: Decimal) -> float:
    if not value.is_finite():
        return 0.0
    return float(value.quantize(Decimal("0.01")))

