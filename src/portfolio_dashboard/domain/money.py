"""Decimal parsing and JSON-boundary conversion helpers."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from .issues import UNREADABLE_NUMBER, report_import_issue

EUR = Decimal(1)
ZERO = Decimal(0)

# Cells that mean "no value" in broker exports rather than a malformed number.
_PLACEHOLDERS = frozenset({"-", "–", "—", "n/a", "na", "n.a.", "n.d.", "nd", "none", "null", "nan"})
_CURRENCY = re.compile(r"(?i)(?:eur|usd|gbp|chf)|[€$£]")
_SPACING = re.compile(r"[\s  ']")


def parse_decimal_or_none(value: str | None) -> Decimal | None:
    """Parse an amount written in either European or English notation.

    Empty cells and placeholders are zero; text that is not a number is None.
    With both separators present the last one is the decimal mark ("1.234,56",
    "1,234.56"); a repeated separator is a thousands mark ("1.234.567"); a single
    comma is a decimal comma ("12,5"). Parentheses and the Unicode minus mean
    negative; currency codes, symbols and grouping spaces are ignored.
    """

    raw = (value or "").strip()
    if not raw or raw.casefold() in _PLACEHOLDERS:
        return ZERO
    text = _SPACING.sub("", _CURRENCY.sub("", raw.replace("−", "-")))
    if not text:
        return ZERO
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", "") if text.count(",") > 1 else text.replace(",", ".")
    elif text.count(".") > 1:
        text = text.replace(".", "")
    try:
        number = Decimal(text)
    except InvalidOperation:
        return None
    if not number.is_finite():
        return None
    return -number if negative else number


def parse_decimal(value: str | None) -> Decimal:
    """Lenient amount parser: unreadable text counts as zero but is reported to an active import."""

    number = parse_decimal_or_none(value)
    if number is None:
        report_import_issue(UNREADABLE_NUMBER, repr((value or "").strip()[:40]))
        return ZERO
    return number


def decimal_to_float(value: Decimal) -> float:
    if not value.is_finite():
        return 0.0
    return float(value.quantize(Decimal("0.0001")))


def money(value: Decimal) -> float:
    if not value.is_finite():
        return 0.0
    return float(value.quantize(Decimal("0.01")))
