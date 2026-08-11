"""Domain records shared across import, analytics, and reporting layers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class Trade:
    asset: str
    isin: str
    broker: str
    action: str
    currency_hint: str
    cash_currency: str
    date: date
    price: Decimal
    quantity: Decimal
    quantity_diff: Decimal
    total_spend: Decimal
    fees: Decimal
    tax: Decimal
    grand_total: Decimal
    grand_total_present: bool
    source: str


@dataclass(frozen=True)
class Dividend:
    broker: str
    asset: str
    isin: str
    date: date
    amount_eur: Decimal
    tax_eur: Decimal


@dataclass(frozen=True)
class FrictionEvent:
    broker: str
    event_type: str
    date: date
    amount_eur: Decimal
    description: str


@dataclass(frozen=True)
class ExpenseRule:
    priority: int
    source: str
    match_field: str
    match_type: str
    pattern: str
    category: str
    subcategory: str
    merchant: str

