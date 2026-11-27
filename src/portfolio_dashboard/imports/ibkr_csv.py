"""Read an Interactive Brokers activity statement exported as CSV.

The export stacks every report section in one file. Each line starts with the
section's name and a row kind (``Header``, ``Data``, ``SubTotal``, ``Total``); a
``Header`` line names the columns of the ``Data`` lines after it. Section and column
names follow the statement's language, so both the English and the Italian names
are recognised.

Trades keep their own currency, as the PDF reader does, and the dashboard converts
them on their date. Dividends, withholding tax, fees and interest are stored in
EUR: each currency block of those sections ends with a "Total" line and, for a
foreign currency, a "Total in EUR" line, whose ratio converts the block's rows. That
keeps the stored rows equal to the statement's own totals without market data.
Those rows carry an identity built from the statement row (date, ISIN, currency and
native amount), so a later statement covering the same days matches them even if
its EUR totals, and so the ratio, differ.
"""

from __future__ import annotations

import csv
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from ..domain.issues import SKIPPED_ROW, UNREADABLE_NUMBER, report_import_issue

BROKER = "Interactive Brokers"
SOURCE = "interactive_brokers"
ZERO = Decimal(0)
EUR_PLACES = Decimal("0.0001")

SECTIONS = {
    "statement": {"statement", "rendiconto"},
    "account": {"account information", "dati del conto"},
    "trades": {"trades", "dettaglio eseguiti", "operazioni"},
    "dividends": {"dividends", "dividendi"},
    "withholding": {"withholding tax", "ritenute alla fonte"},
    "fees": {"fees", "commissioni"},
    "interest": {"interest", "interessi"},
    "deposits": {"deposits & withdrawals", "depositi e prelievi", "depositi & prelievi"},
    "corporate_actions": {"corporate actions", "azioni societarie", "operazioni societarie"},
    "instruments": {"financial instrument information", "informazioni sullo strumento finanziario"},
}
FIELDS = {
    "discriminator": {"datadiscriminator"},
    "asset_class": {"asset category", "tipo di attivo"},
    "currency": {"currency", "valuta"},
    "symbol": {"symbol", "simbolo"},
    "datetime": {"date/time", "data/ora"},
    "quantity": {"quantity", "quantità"},
    "price": {"t. price", "prezzo eseguito", "prezzo t."},
    "proceeds": {"proceeds", "ricavo"},
    "commission": {"comm/fee", "comm./tasse", "comm/tasse", "comm./comm."},
    "date": {"date", "data", "settle date", "data di regolamento"},
    "description": {"description", "descrizione"},
    "amount": {"amount", "importo"},
    "security_id": {"security id", "id titolo"},
    "field_name": {"field name", "nome del campo"},
    "field_value": {"field value", "valore del campo", "valore del cmapo"},
}
STOCK_CLASSES = {"stocks", "azioni"}
FOREX_CLASSES = {"forex"}
# "Order" rows are one line per order; "Execution" rows split an order into its fills
# and "ClosedLot" rows repeat a sale's lots, so only one kind is read.
ORDER_ROWS = {"order", "trade"}
EXECUTION_ROWS = {"execution"}
# "EXMP(XX0000000001) Cash Dividend USD 0.50 per Share ..." names the symbol and ISIN.
INSTRUMENT_PREFIX = re.compile(r"^\s*(?P<symbol>[^\s(]+)\s*\((?P<isin>[A-Z]{2}[A-Z0-9]{9}\d)\)")

Converter = Callable[[Decimal, str, date], Decimal | None]


def _key(value: Any) -> str:
    return " ".join(str(value or "").replace("﻿", "").split()).casefold()


def _section(name: str) -> str | None:
    key = _key(name)
    return next((section for section, names in SECTIONS.items() if key in names), None)


def _number(value: Any) -> Decimal | None:
    text = str(value or "").strip().replace(",", "")  # IB groups thousands with commas
    if text in {"", "--", "-"}:
        return None
    try:
        number = Decimal(text.rstrip("%"))
    except InvalidOperation:
        report_import_issue(UNREADABLE_NUMBER, f"{value!r}")
        return None
    return number if number.is_finite() else None


def _day(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value or "").strip()[:10])
    except ValueError:
        return None


def _rows(path: Path) -> list[list[str]]:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            with path.open(newline="", encoding=encoding) as handle:
                return [row for row in csv.reader(handle) if row]
        except (OSError, UnicodeDecodeError, csv.Error):
            continue
    return []


def looks_like_activity_statement(path: Path) -> bool:
    """An IBKR CSV opens with ``Statement,Header`` and names the broker in its first lines."""

    rows = _rows(path)[:12]
    if not rows or len(rows[0]) < 2 or _section(rows[0][0]) != "statement" or _key(rows[0][1]) != "header":
        return False
    return any("interactive brokers" in _key(" ".join(row)) for row in rows)


@dataclass
class _Table:
    """One section's data lines, as dicts keyed by canonical column name."""

    rows: list[dict[str, str]] = field(default_factory=list)


def _tables(lines: list[list[str]]) -> dict[str, _Table]:
    tables: dict[str, _Table] = {}
    headers: dict[str, list[str]] = {}
    for line in lines:
        if len(line) < 2:
            continue
        section = _section(line[0])
        if section is None:
            continue
        kind = _key(line[1])
        values = line[2:]
        if kind == "header":
            headers[section] = [_canonical_field(name) for name in values]
            continue
        header = headers.get(section)
        if header is None:
            continue
        record = {name: (values[index].strip() if index < len(values) else "") for index, name in enumerate(header)}
        if kind == "data" and not _is_total(values):
            tables.setdefault(section, _Table()).rows.append(record)
    return tables


def _canonical_field(name: str) -> str:
    key = _key(name)
    return next((field_name for field_name, names in FIELDS.items() if key in names), key)


def _first_value(values: Iterable[str]) -> str:
    return next((value.strip() for value in values if value.strip()), "")


def _is_total(values: Iterable[str]) -> bool:
    """Dividend, tax and fee sections write their totals as ``Data`` lines."""

    return _key(_first_value(values)).startswith(("total", "totale"))


def _base_currency(tables: dict[str, _Table]) -> str:
    for row in tables.get("account", _Table()).rows:
        if _key(row.get("field_name")) in {"base currency", "valuta di base"}:
            return str(row.get("field_value") or "EUR").strip().upper()
    return "EUR"


def _block_rates(lines: list[list[str]], section: str, base: str) -> dict[str, Decimal]:
    """Each foreign currency's rate to ``base`` from a section's "Total"/"Total in EUR" lines.

    The totals follow the rows of their currency block, so the lines are read in
    file order: a "Total" line closes the block of the currency seen last, and the
    "Total in <base>" line after it gives that block's value in the base currency.
    """

    rates: dict[str, Decimal] = {}
    header: list[str] = []
    currency = ""
    native: Decimal | None = None
    in_base = f"in {base}".casefold()
    for line in lines:
        if len(line) < 2 or _section(line[0]) != section:
            continue
        kind, values = _key(line[1]), line[2:]
        if kind == "header":
            header = [_canonical_field(name) for name in values]
            continue
        record = dict(zip(header, (value.strip() for value in values), strict=False))
        if not _is_total(values):
            currency = str(record.get("currency") or "").strip().upper() or currency
            continue
        label = _key(_first_value(values))
        amount = _number(record.get("amount"))
        if label in {"total", "totale"}:
            native = amount
        elif label in {f"total {in_base}", f"totale {in_base}"}:
            if currency and currency != base and native and amount is not None:
                rates[currency] = amount / native
            native = None
    return rates


def _to_eur(amount: Decimal, currency: str, day: date, rates: dict[str, Decimal], base: str, convert: Converter) -> Decimal | None:
    if currency == base == "EUR":
        return amount
    if base == "EUR" and currency in rates:
        return amount * rates[currency]
    return convert(amount, currency, day)


def _identity(kind: str, day: date, isin: str, currency: str, amount: Decimal, seen: dict[str, int]) -> str:
    """A row's identity across statements: what IBKR booked, never the EUR value derived from it."""

    base = f"ibkr:{kind}:{day.isoformat()}:{isin}:{currency}:{format(amount.normalize(), 'f')}"
    seen[base] = seen.get(base, 0) + 1
    return base if seen[base] == 1 else f"{base}:{seen[base]}"


def _instruments(tables: dict[str, _Table]) -> tuple[dict[str, dict[str, str]], dict[str, str]]:
    """Stock instruments by symbol, and their names by ISIN."""

    by_symbol: dict[str, dict[str, str]] = {}
    names: dict[str, str] = {}
    for row in tables.get("instruments", _Table()).rows:
        if _key(row.get("asset_class")) not in STOCK_CLASSES:
            continue
        symbol = str(row.get("symbol") or "").strip()
        isin = str(row.get("security_id") or "").strip().upper()
        name = " ".join(str(row.get("description") or "").split())
        if symbol:
            by_symbol[symbol] = {"asset": name or symbol, "isin": isin}
        if isin and name:
            names[isin] = name
    return by_symbol, names


def _trades(tables: dict[str, _Table], instruments: dict[str, dict[str, str]]) -> list[dict[str, Any]]:
    rows = tables.get("trades", _Table()).rows
    kinds = {_key(row.get("discriminator")) for row in rows}
    wanted = ORDER_ROWS if kinds & ORDER_ROWS else EXECUTION_ROWS if kinds & EXECUTION_ROWS else {""}
    movements: list[dict[str, Any]] = []
    for row in rows:
        if _key(row.get("discriminator")) not in wanted:
            continue
        asset_class = _key(row.get("asset_class"))
        symbol = str(row.get("symbol") or "").strip()
        if asset_class in FOREX_CLASSES:
            continue  # a currency conversion moves cash between currencies, not a holding
        if asset_class not in STOCK_CLASSES:
            report_import_issue(SKIPPED_ROW, f"Interactive Brokers {row.get('asset_class')} trade in {symbol} is not supported")
            continue
        day = _day(row.get("datetime"))
        quantity = _number(row.get("quantity"))
        if day is None or not quantity:
            report_import_issue(SKIPPED_ROW, f"Interactive Brokers trade line not recognised ({symbol} {row.get('datetime')})")
            continue
        proceeds = _number(row.get("proceeds")) or ZERO
        commission = _number(row.get("commission")) or ZERO
        currency = str(row.get("currency") or "EUR").strip().upper()
        instrument = instruments.get(symbol, {})
        action = "Acquisto" if quantity > 0 else "Vendita"
        movements.append(
            {
                "occurred_on": day,
                "event_type": "trade",
                "broker": BROKER,
                "asset": instrument.get("asset") or symbol,
                "isin": instrument.get("isin", ""),
                "description": action,
                "currency": currency,
                "amount": proceeds + commission,
                "quantity": quantity,
                "price": _number(row.get("price")) or ZERO,
                "fees": abs(commission),
                "tax": ZERO,
                "metadata": {"action": action, "source": SOURCE, "transaction_id": ""},
            }
        )
    return movements


def _dated_rows(table: _Table | None) -> list[tuple[date, str, Decimal, dict[str, str]]]:
    rows = []
    for row in (table or _Table()).rows:
        day = _day(row.get("date"))
        amount = _number(row.get("amount"))
        if day is None or amount is None or amount == 0:
            continue
        rows.append((day, str(row.get("currency") or "EUR").strip().upper(), amount, row))
    return rows


def _instrument_of(description: str) -> tuple[str, str]:
    match = INSTRUMENT_PREFIX.match(description)
    return (match["symbol"], match["isin"]) if match else ("", "")


def read_activity_statement(path: Path, convert: Converter) -> list[dict[str, Any]]:
    """Every ledger row of one IBKR activity statement CSV.

    ``convert(amount, currency, day)`` values a foreign amount in EUR when the
    statement gives no EUR total for its block (or the account's base currency is not
    EUR); it returns None when no rate is known.
    """

    lines = _rows(path)
    tables = _tables(lines)
    base = _base_currency(tables)
    by_symbol, names = _instruments(tables)
    movements = _trades(tables, by_symbol)

    def eur(section: str) -> Callable[[Decimal, str, date], Decimal | None]:
        rates = _block_rates(lines, section, base)

        def value(amount: Decimal, currency: str, day: date) -> Decimal | None:
            converted = _to_eur(amount, currency, day, rates, base, convert)
            return None if converted is None else converted.quantize(EUR_PLACES)

        return value

    seen: dict[str, int] = {}
    dividend_eur, tax_eur, fee_eur, interest_eur = eur("dividends"), eur("withholding"), eur("fees"), eur("interest")

    # Withholding is booked as its own line; it belongs to the dividend of the same
    # instrument, day and currency.
    withheld: dict[tuple[date, str, str], list[tuple[Decimal, dict[str, str]]]] = {}
    for day, currency, amount, row in _dated_rows(tables.get("withholding")):
        _symbol, isin = _instrument_of(str(row.get("description") or ""))
        withheld.setdefault((day, isin, currency), []).append((amount, row))

    for day, currency, amount, row in _dated_rows(tables.get("dividends")):
        description = str(row.get("description") or "")
        symbol, isin = _instrument_of(description)
        taxes = withheld.pop((day, isin, currency), []) if isin else []
        tax_native = -sum((value for value, _row in taxes), ZERO)
        gross = dividend_eur(amount, currency, day)
        tax = tax_eur(tax_native, currency, day) if tax_native else ZERO
        if gross is None or tax is None:
            continue
        asset = names.get(isin) or by_symbol.get(symbol, {}).get("asset") or symbol or "Unknown"
        identity = _identity("dividend", day, isin or symbol, currency, amount, seen)
        movements.append(
            {
                "occurred_on": day,
                "event_type": "dividend",
                "broker": BROKER,
                "asset": asset,
                "isin": isin,
                "description": "Dividend",
                "currency": "EUR",
                "amount": gross - tax,
                "tax": tax,
                "metadata": {
                    "transaction_id": identity,
                    "native_currency": currency,
                    "native_amount": str(amount),
                    "native_tax": str(tax_native),
                    "statement_description": description,
                },
            }
        )
        if tax:
            movements.append(
                {
                    "occurred_on": day,
                    "event_type": "dividend_tax",
                    "broker": BROKER,
                    "description": f"Dividend withholding - {asset}",
                    "currency": "EUR",
                    "amount": tax,
                    "metadata": {"transaction_id": f"{identity}:tax"},
                }
            )

    # Withholding with no dividend beside it (on credit interest, or a later
    # adjustment) is still tax paid.
    for (day, isin, currency), taxes in withheld.items():
        for amount, row in taxes:
            tax = tax_eur(-amount, currency, day)
            if tax is None:
                continue
            movements.append(
                {
                    "occurred_on": day,
                    "event_type": "tax",
                    "broker": BROKER,
                    "description": str(row.get("description") or "Withholding tax"),
                    "currency": "EUR",
                    "amount": tax,
                    "metadata": {"transaction_id": _identity("tax", day, isin, currency, amount, seen)},
                }
            )

    # A charge is a positive cost; a fee refunded is a negative one.
    for day, currency, amount, row in _dated_rows(tables.get("fees")):
        cost = fee_eur(-amount, currency, day)
        if cost is None:
            continue
        _symbol, isin = _instrument_of(str(row.get("description") or ""))
        movements.append(
            {
                "occurred_on": day,
                "event_type": "cost",
                "broker": BROKER,
                "description": str(row.get("description") or "Fee"),
                "currency": "EUR",
                "amount": cost,
                "metadata": {"transaction_id": _identity("fee", day, isin, currency, amount, seen)},
            }
        )

    for day, currency, amount, row in _dated_rows(tables.get("interest")):
        value = interest_eur(amount, currency, day)
        if value is None:
            continue
        movements.append(
            {
                "occurred_on": day,
                "event_type": "interest",
                "account": BROKER,
                "description": str(row.get("description") or "Cash Interest"),
                "currency": "EUR",
                "amount": value,
                "metadata": {"gross_eur": value, "transaction_id": _identity("interest", day, "", currency, amount, seen)},
            }
        )

    for section, label in (("deposits", "deposits and withdrawals"), ("corporate_actions", "corporate actions")):
        if tables.get(section) and tables[section].rows:
            report_import_issue(SKIPPED_ROW, f"Interactive Brokers {label} are not imported yet")
    return movements
