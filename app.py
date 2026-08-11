from __future__ import annotations

import csv
import email.utils
import html
import io
import json
import math
import os
import re
import subprocess
import threading
import time
import urllib.parse
import urllib.request
import warnings
import xml.etree.ElementTree as ET
from bisect import bisect_right
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request, send_file
from openpyxl import Workbook, load_workbook

from src.portfolio_dashboard.config import get_settings
from src.portfolio_dashboard.domain import (
    EUR,
    ZERO,
    Dividend,
    ExpenseRule,
    FrictionEvent,
    Trade,
    decimal_to_float,
    money,
    parse_decimal,
)
from src.portfolio_dashboard.ingest import BrokerAdapter, FunctionBrokerAdapter

try:
    import yfinance as yf
except Exception:  # pragma: no cover - handled at runtime in the dashboard
    yf = None


SETTINGS = get_settings()
APP_DIR = SETTINGS.project_dir
ROOT_DIR = SETTINGS.source_dir
PRIMARY_PORTFOLIO_ID = SETTINGS.primary_portfolio_id.lower()
PRIMARY_PORTFOLIO_NAME = SETTINGS.primary_portfolio_name
TRADES_CSV = ROOT_DIR / SETTINGS.manual_trades_file
TRADE_REPUBLIC_PATTERN = SETTINGS.trade_republic_pattern
FINECO_PATTERN = SETTINGS.fineco_pattern
IB_PATTERN = SETTINGS.interactive_brokers_pattern
ETORO_PATTERN = SETTINGS.etoro_pattern
REVOLUT_PATTERN = SETTINGS.revolut_pattern
REVOLUT_DOWNLOADS_PATTERN = SETTINGS.revolut_downloads_pattern
INTESA_OPERATIONS_PATTERN = SETTINGS.intesa_pattern
INTESA_DOWNLOADS_PATTERN = SETTINGS.intesa_downloads_pattern
FAMILY_PORTFOLIOS = SETTINGS.family_portfolios
MAPPINGS_CSV = SETTINGS.data_path("asset_mappings.csv")
EXPOSURES_CSV = SETTINGS.data_path("asset_exposures.csv")
ETF_DOCUMENTS_JSON = APP_DIR / "data" / "etf_documents.json"
BERKSHIRE_HOLDINGS_CSV = APP_DIR / "data" / "berkshire_holdings.csv"
BERKSHIRE_ISIN = "US0846707026"
PROXY_EXPOSURES_CSV = APP_DIR / "data" / "proxy_exposures.csv"
CRYPTO_WALLETS_CSV = SETTINGS.data_path("crypto_wallets.csv")
CRYPTO_WALLET_POSITIONS_CSV = SETTINGS.data_path("crypto_wallet_positions.csv")
CRYPTO_WALLET_TRANSACTIONS_CSV = SETTINGS.data_path("crypto_wallet_transactions.csv")
EXPENSE_RULES_CSV = SETTINGS.data_path("expense_category_rules.csv")
PROXY_ISSUERS = {
    "IE00BK5BQT80": "Vanguard",
    "LU1681045370": "Amundi",
    "IE00BKM4GZ66": "iShares",
    "NL0011683594": "VanEck",
    "IE00B2NLMV86": "Mediolanum",
    "IE00BYZ2Y955": "Mediolanum",
    "IT0001019329": "Mediolanum",
    "IT0001280541": "Eurizon",
    "IT0005285157": "Eurizon",
    "IT0005104424": "Eurizon",
    "LU0497415702": "Eurizon",
    "IT0004896715": "Anima",
    "LU2146152231": "JPMorgan",
    "LU0129441100": "JPMorgan",
    "LU0109394709": "Franklin Templeton",
    "LU0195953079": "Franklin Templeton",
    "LU0755218046": "Fidelity",
    "LU0106239527": "Schroders",
}
PROXY_SOURCE_URLS = {
    "IE00BK5BQT80": "https://companiesmarketcap.com/vanguard-ftse-all-world-ucits-etf-usd-accumulation/holdings/",
    "LU1681045370": "https://www.ishares.com/uk/individual/en/products/264659/fund/1506575576011.ajax?fileType=csv&fileName=EIMI_holdings&dataType=fund",
    "IE00BKM4GZ66": "https://www.ishares.com/uk/individual/en/products/264659/fund/1506575576011.ajax?fileType=csv&fileName=EIMI_holdings&dataType=fund",
    "NL0011683594": "https://companiesmarketcap.com/vaneck-morningstar-developed-markets-dividend-leaders-ucits-etf/holdings/",
    "IE00B2NLMV86": "https://www.ishares.com/uk/individual/en/products/251882/ishares-msci-world-ucits-etf-acc-fund",
    "IE00BYZ2Y955": "https://companiesmarketcap.com/vaneck-morningstar-developed-markets-dividend-leaders-ucits-etf/holdings/",
    "LU0755218046": "https://www.ishares.com/uk/individual/en/products/251900/ishares-core-sp-500-ucits-etf-acc-fund",
}
PROXY_MESSAGES = {
    "IE00BK5BQT80": "Non-official 1,500-row constituent proxy normalized to 100%; switch to Official only to hide it.",
    "LU1681045370": "Official iShares MSCI EM IMI holdings used as an economic proxy and normalized to 100%; switch to Official only to hide it.",
    "IE00BKM4GZ66": "Official iShares MSCI EM IMI holdings normalized to 100%; switch to Official only to hide it.",
    "NL0011683594": "Non-official 101-row constituent proxy; switch to Official only to hide it.",
    "IE00B2NLMV86": "Official iShares MSCI World holdings used as a global equity fund proxy and normalized to 100%; switch to Official only to hide it.",
    "IE00BYZ2Y955": "Non-official VanEck Developed Markets Dividend Leaders holdings used as a value equity proxy and normalized to 100%; switch to Official only to hide it.",
    "IT0001019329": "Mock PIR-compliant proxy (70% top Italian equities, 30% cash/gov bonds) normalized to 100%; switch to Official only to hide it.",
    "IT0001280541": "Mock Euro High Yield Corporate Bond proxy (80% corporate bonds, 20% short-term gov bonds) normalized to 100%; switch to Official only to hide it.",
    "IT0005285157": "Mock Defensive Profilo Flessibile proxy (10% MSCI World, 60% Eurozone gov bonds, 30% cash) normalized to 100%; switch to Official only to hide it.",
    "IT0005104424": "Mock Short-term Gov Bond proxy (70% Eurozone short-term gov bonds, 30% cash) normalized to 100%; switch to Official only to hide it.",
    "LU0497415702": "Mock Flexible Equity Strategy proxy (55% MSCI World, 30% Eurozone bonds, 15% cash) normalized to 100%; switch to Official only to hide it.",
    "IT0004896715": "Mock Balanced proxy (60% MSCI World, 40% Euro cash/bonds) normalized to 100%; switch to Official only to hide it.",
    "LU2146152231": "Mock MSCI Europe Index proxy using top 9 European equity giants normalized to 100%; switch to Official only to hide it.",
    "LU0129441100": "Mock MSCI Europe Index proxy using top 9 European equity giants normalized to 100%; switch to Official only to hide it.",
    "LU0109394709": "Mock Biotechnology Index proxy using top 5 biotech leaders normalized to 100%; switch to Official only to hide it.",
    "LU0195953079": "Mock Global Bond Index proxy (40% US, 40% Eurozone, 20% Japan) normalized to 100%; switch to Official only to hide it.",
    "LU0755218046": "Official iShares S&P 500 holdings used as an economic proxy and normalized to 100%; switch to Official only to hide it.",
    "LU0106239527": "Mock Italian Equity Index proxy using top 6 Italian leaders normalized to 100%; switch to Official only to hide it.",
}
FULL_OFFICIAL_COMPOSITION_STATUSES = {"ok", "cached", "cash_equivalent", "official_sec_13f"}
SYMBOL_CACHE = SETTINGS.cache_path("price-symbols.json")
PRICE_CACHE = SETTINGS.cache_path("prices.json")
HISTORY_CACHE = SETTINGS.cache_path("history.json")
NEWS_CACHE = SETTINGS.cache_path("news.json")
PRICE_TTL_SECONDS = 15 * 60
HISTORY_TTL_SECONDS = 12 * 60 * 60
NEWS_TTL_SECONDS = 60 * 60

FINECO_DIVIDEND_NET_RATE = Decimal("0.74")
_CACHE_WRITE_LOCK = threading.RLock()

app = Flask(__name__)


def parse_trade_date(day_value: str, year_value: str) -> date:
    raw = day_value.strip()
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass

    parts = raw.split("/")
    if len(parts) == 2 and year_value.strip():
        day, month = parts
        return date(int(year_value.strip()), int(month), int(day))

    raise ValueError(f"Unsupported trade date: {day_value!r}")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_json(path: Path, payload: Any) -> None:
    encoded = json.dumps(payload, indent=2, sort_keys=True)
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    with _CACHE_WRITE_LOCK:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path.write_text(encoded, encoding="utf-8")
            tmp_path.replace(path)
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass


def configured_path_label(path: Path) -> str:
    """Return a stable path label without exposing an absolute local path."""

    for prefix, base in (
        ("private", SETTINGS.data_dir),
        ("sources", ROOT_DIR),
        ("public", APP_DIR),
        ("cache", SETTINGS.cache_dir),
    ):
        try:
            return str(Path(prefix) / path.relative_to(base))
        except ValueError:
            continue
    return path.name


def latest_trade_republic_export() -> Path | None:
    files = sorted(ROOT_DIR.glob(TRADE_REPUBLIC_PATTERN))
    family_markers = {
        (profile.trade_republic_name or portfolio_id).lower()
        for portfolio_id, profile in SETTINGS.portfolios.items()
        if portfolio_id.lower() != PRIMARY_PORTFOLIO_ID
    }
    files = [path for path in files if not any(marker in path.name.lower() for marker in family_markers)]
    return files[-1] if files else None


def latest_family_trade_republic_export(person: str) -> Path | None:
    files = sorted(ROOT_DIR.glob(TRADE_REPUBLIC_PATTERN))
    profile = SETTINGS.portfolios.get(person.lower())
    marker = (profile.trade_republic_name if profile else None) or person
    files = [f for f in files if marker.lower() in f.name.lower()]
    return files[-1] if files else None


def latest_fineco_export() -> Path | None:
    files = sorted(ROOT_DIR.glob(FINECO_PATTERN))
    return files[-1] if files else None


def latest_ib_export() -> Path | None:
    files = sorted(ROOT_DIR.glob(IB_PATTERN))
    return files[-1] if files else None


def latest_etoro_export() -> Path | None:
    files = sorted(ROOT_DIR.glob(ETORO_PATTERN))
    return files[-1] if files else None


def intesa_operations_sort_key(path: Path) -> tuple[date, float, str]:
    match = re.search(r"(\d{8})", path.stem)
    export_date = date.min
    if match:
        try:
            export_date = datetime.strptime(match.group(1), "%d%m%Y").date()
        except ValueError:
            export_date = date.min
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0.0
    return export_date, mtime, path.name


def intesa_operations_files() -> list[Path]:
    candidates: dict[Path, Path] = {}
    for path in ROOT_DIR.glob(INTESA_OPERATIONS_PATTERN):
        candidates[path.resolve()] = path
    downloads = Path.home() / "Downloads"
    if downloads.exists():
        for path in downloads.glob(INTESA_DOWNLOADS_PATTERN):
            candidates[path.resolve()] = path
    return sorted(candidates.values(), key=intesa_operations_sort_key)


def latest_intesa_operations_export() -> Path | None:
    files = intesa_operations_files()
    return files[-1] if files else None


def parse_revolut_datetime(value: str | None) -> datetime | None:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def revolut_statement_profile(path: Path) -> tuple[tuple[str, ...], date, int] | None:
    currencies: set[str] = set()
    latest_date: date | None = None
    completed_rows = 0
    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                if row.get("State") != "COMPLETATO":
                    continue
                event_time = parse_revolut_datetime(row.get("Data di completamento")) or parse_revolut_datetime(row.get("Data di inizio"))
                if event_time is None:
                    continue
                currencies.add(normalize_currency_code(row.get("Valuta") or "EUR"))
                latest_date = max(latest_date or event_time.date(), event_time.date())
                completed_rows += 1
    except OSError:
        return None
    if not completed_rows or latest_date is None:
        return None
    return tuple(sorted(currencies)), latest_date, completed_rows


def revolut_statement_files() -> list[Path]:
    candidates: list[Path] = []
    candidates.extend(ROOT_DIR.glob(REVOLUT_PATTERN))
    downloads = Path.home() / "Downloads"
    if downloads.exists():
        candidates.extend(downloads.glob(REVOLUT_DOWNLOADS_PATTERN))

    best_by_currency: dict[tuple[str, ...], tuple[date, int, float, Path]] = {}
    for path in candidates:
        profile = revolut_statement_profile(path)
        if profile is None:
            continue
        currencies, latest_date, completed_rows = profile
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = 0.0
        candidate = (latest_date, completed_rows, mtime, path)
        current = best_by_currency.get(currencies)
        if current is None or candidate[:3] > current[:3]:
            best_by_currency[currencies] = candidate

    return sorted((item[3] for item in best_by_currency.values()), key=lambda item: item.name)


def broker_adapters() -> tuple[BrokerAdapter, ...]:
    return (
        FunctionBrokerAdapter("Trade Republic", latest_trade_republic_export, read_trade_republic_trades),
        FunctionBrokerAdapter("Fineco", latest_fineco_export, read_fineco_trades),
        FunctionBrokerAdapter("Interactive Brokers", latest_ib_export, read_interactive_brokers_trades),
        FunctionBrokerAdapter("eToro", latest_etoro_export, read_etoro_trades),
    )


def read_trades() -> tuple[list[Trade], dict[str, Any]]:
    broker_sources: list[dict[str, Any]] = []
    trades: list[Trade] = []

    for adapter in broker_adapters():
        export_path = adapter.discover()
        if export_path is None:
            continue
        trades.extend(adapter.parse(export_path))
        broker_sources.append(
            {
                "path": export_path,
                "kind": adapter.name,
                "relative_path": configured_path_label(export_path),
            }
        )

    if broker_sources:
        return sorted(trades, key=lambda item: (item.date, item.broker, item.asset, item.action)), {
            "kind": " + ".join(source["kind"] for source in broker_sources),
            "relative_path": ", ".join(source["relative_path"] for source in broker_sources),
            "sources": broker_sources,
        }

    if not TRADES_CSV.exists():
        raise FileNotFoundError(f"Missing trades file: {TRADES_CSV}")
    trades = read_manual_trades(TRADES_CSV)
    return trades, {
        "path": TRADES_CSV,
        "kind": "Manual spreadsheet",
        "relative_path": TRADES_CSV.name,
    }


def read_manual_trades(path: Path) -> list[Trade]:
    trades: list[Trade] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        header = next(reader, None)
        if not header or len(header) < 17:
            raise ValueError("Trades CSV does not match the expected 17-column export.")

        for line_number, row in enumerate(reader, start=2):
            if len(row) != len(header):
                raise ValueError(f"Invalid column count on row {line_number}.")
            if not row[0].strip():
                continue

            trade_date = parse_trade_date(row[5], row[7])
            grand_total_raw = row[16].strip()
            trades.append(
                Trade(
                    asset=row[0].strip(),
                    isin="",
                    broker="Manual",
                    action=row[2].strip(),
                    currency_hint=(row[3].strip() or "E").upper(),
                    cash_currency="EUR",
                    date=trade_date,
                    price=parse_decimal(row[9]),
                    quantity=parse_decimal(row[10]),
                    quantity_diff=parse_decimal(row[11]),
                    total_spend=parse_decimal(row[13]),
                    fees=parse_decimal(row[14]),
                    tax=parse_decimal(row[15]),
                    grand_total=parse_decimal(grand_total_raw),
                    grand_total_present=bool(grand_total_raw),
                    source="manual",
                )
            )

    return sorted(trades, key=lambda item: (item.date, item.asset, item.action))


def read_trade_republic_trades(path: Path) -> list[Trade]:
    trades: list[Trade] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            if row.get("type") not in {"BUY", "SELL"}:
                continue
            if row.get("category") != "TRADING" or not row.get("shares"):
                continue

            raw_fee = parse_decimal(row.get("fee"))
            raw_tax = parse_decimal(row.get("tax"))
            cash_effect = parse_decimal(row.get("amount")) + raw_fee + raw_tax
            trade_type = row["type"]
            trades.append(
                Trade(
                    asset=(row.get("name") or row.get("symbol") or "Unknown").strip(),
                    isin=(row.get("symbol") or "").strip().upper(),
                    broker="Trade Republic",
                    action="Acquisto" if trade_type == "BUY" else "Vendita",
                    currency_hint=(row.get("currency") or "EUR").strip().upper(),
                    cash_currency="EUR",
                    date=datetime.strptime(row["date"], "%Y-%m-%d").date(),
                    price=parse_decimal(row.get("price")),
                    quantity=abs(parse_decimal(row.get("shares"))),
                    quantity_diff=parse_decimal(row.get("shares")),
                    total_spend=cash_effect,
                    fees=-raw_fee,
                    tax=-raw_tax,
                    grand_total=cash_effect,
                    grand_total_present=True,
                    source="trade_republic",
                )
            )

    return sorted(trades, key=lambda item: (item.date, item.asset, item.action))


def parse_fineco_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value).strip(), "%d/%m/%Y").date()


def fineco_decimal(value: Any) -> Decimal:
    if value is None:
        return ZERO
    return parse_decimal(str(value))


def fineco_dividend_tax_from_net(net_amount: Decimal) -> Decimal:
    if net_amount <= ZERO:
        return ZERO
    gross = net_amount / FINECO_DIVIDEND_NET_RATE
    return gross - net_amount


def fineco_capital_gain_tax_from_net_gain(net_gain: Decimal) -> Decimal:
    if net_gain <= ZERO:
        return ZERO
    gross_gain = net_gain / FINECO_DIVIDEND_NET_RATE
    return gross_gain - net_gain


def read_fineco_trades(path: Path) -> list[Trade]:
    workbook = load_workbook(path, data_only=True, read_only=True)
    sheet = workbook["Movimenti Dossier Titoli"]
    trades: list[Trade] = []

    for row in sheet.iter_rows(min_row=8, values_only=True):
        if not row or row[2] != "Compravendita titoli":
            continue
        sign = str(row[5] or "").strip().upper()
        if sign not in {"A", "V"}:
            continue

        quantity = abs(fineco_decimal(row[6]))
        value_eur = fineco_decimal(row[10])
        commission = fineco_decimal(row[14])
        is_buy = sign == "A"
        cash_effect = -(value_eur + commission) if is_buy else value_eur - commission
        trades.append(
            Trade(
                asset=str(row[3]).strip(),
                isin=str(row[4] or "").strip().upper(),
                broker="Fineco",
                action="Acquisto" if is_buy else "Vendita",
                currency_hint=str(row[7] or "EUR").strip().upper(),
                cash_currency="EUR",
                date=parse_fineco_date(row[0]),
                price=fineco_decimal(row[8]),
                quantity=quantity,
                quantity_diff=quantity if is_buy else -quantity,
                total_spend=cash_effect,
                fees=commission,
                tax=ZERO,
                grand_total=cash_effect,
                grand_total_present=True,
                source="fineco",
            )
        )

    return sorted(trades, key=lambda item: (item.date, item.asset, item.action))


def pdf_text(path: Path) -> str:
    result = subprocess.run(["pdftotext", "-layout", str(path), "-"], check=True, capture_output=True, text=True)
    return result.stdout


def parse_ib_instruments(text: str) -> dict[str, dict[str, str]]:
    instruments: dict[str, dict[str, str]] = {}
    for line in text.splitlines():
        match = re.match(r"^\s*([A-Z0-9.]+)\s+(.+?)\s+(\d+)\s+([A-Z]{2}[A-Z0-9]{10})\s+([A-Z0-9.]+)\s+([A-Z]+)", line)
        if not match:
            continue
        symbol, description, _, isin, _, exchange = match.groups()
        if symbol == "EUR.USD":
            continue
        instruments[symbol] = {
            "asset": re.sub(r"\s+", " ", description).strip(),
            "isin": isin,
            "exchange": exchange,
        }
    return instruments


def read_interactive_brokers_trades(path: Path) -> list[Trade]:
    text = pdf_text(path)
    instruments = parse_ib_instruments(text)
    trades: list[Trade] = []
    section_currency = "EUR"
    stock_section = False
    pattern = re.compile(
        r"^U16961051\s+(\S+)\s+(\d{4}-\d{2}-\d{2}),\s+\d{2}:\d{2}:\d{2}\s+"
        r"(\d{4}-\d{2}-\d{2})\s+-\s+(BUY|SELL)\s+(-?\d+(?:\.\d+)?)\s+"
        r"(\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)"
    )

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if stripped == "Azioni":
            stock_section = True
            continue
        if stripped == "Forex":
            stock_section = False
            continue
        if stock_section and stripped in {"EUR", "USD", "GBP"}:
            section_currency = stripped
            continue
        if not stock_section:
            continue

        match = pattern.match(line)
        if not match:
            continue
        symbol, trade_date, _, side, quantity, price, proceeds, commission, tax = match.groups()
        if "." in symbol:
            continue
        instrument = instruments.get(symbol, {})
        qty = parse_decimal(quantity)
        cash_effect = parse_decimal(proceeds) + parse_decimal(commission) + parse_decimal(tax)
        is_buy = side == "BUY"
        trades.append(
            Trade(
                asset=instrument.get("asset") or symbol,
                isin=instrument.get("isin", ""),
                broker="Interactive Brokers",
                action="Acquisto" if is_buy else "Vendita",
                currency_hint=section_currency,
                cash_currency=section_currency,
                date=datetime.strptime(trade_date, "%Y-%m-%d").date(),
                price=parse_decimal(price),
                quantity=abs(qty),
                quantity_diff=abs(qty) if is_buy else -abs(qty),
                total_spend=cash_effect,
                fees=abs(parse_decimal(commission)),
                tax=abs(parse_decimal(tax)),
                grand_total=cash_effect,
                grand_total_present=True,
                source="interactive_brokers",
            )
        )

    return sorted(trades, key=lambda item: (item.date, item.asset, item.action))


def read_etoro_trades(path: Path) -> list[Trade]:
    workbook = load_workbook(path, data_only=True, read_only=True)
    dividends = workbook["Dividendi"]
    position_isins: dict[str, str] = {}
    for row in dividends.iter_rows(min_row=2, values_only=True):
        position_id = str(row[11] or "").strip()
        isin = str(row[13] or "").strip().upper()
        if position_id and isin:
            position_isins[position_id] = isin

    activity = workbook["Attività account"]
    trades: list[Trade] = []
    for row in activity.iter_rows(min_row=2, values_only=True):
        if not row or row[1] != "Apri posizione":
            continue
        opened_at = datetime.strptime(str(row[0]), "%d/%m/%Y %H:%M:%S").date()
        detail = str(row[2] or "").strip()
        position_id = str(row[8] or "").strip()
        amount = fineco_decimal(row[3])
        units = fineco_decimal(row[4])
        isin = position_isins.get(position_id, "")
        asset = detail.split("/")[0]
        trades.append(
            Trade(
                asset=asset,
                isin=isin,
                broker="eToro",
                action="Acquisto",
                currency_hint="USD",
                cash_currency="USD",
                date=opened_at,
                price=amount / units if units else ZERO,
                quantity=units,
                quantity_diff=units,
                total_spend=-amount,
                fees=ZERO,
                tax=ZERO,
                grand_total=-amount,
                grand_total_present=True,
                source="etoro",
            )
        )

    return sorted(trades, key=lambda item: (item.date, item.asset, item.action))


def read_dividends() -> list[Dividend]:
    dividends: list[Dividend] = []
    tr_file = latest_trade_republic_export()
    fineco_file = latest_fineco_export()
    etoro_file = latest_etoro_export()
    if tr_file:
        dividends.extend(read_trade_republic_dividends(tr_file))
    if fineco_file:
        dividends.extend(read_fineco_dividends(fineco_file))
    if etoro_file:
        dividends.extend(read_etoro_dividends(etoro_file))
    return sorted(dividends, key=lambda item: (item.date, item.broker, item.asset))


def read_portfolio_dividends(person: str = PRIMARY_PORTFOLIO_ID) -> list[Dividend]:
    person = (person or PRIMARY_PORTFOLIO_ID).lower()
    if person == PRIMARY_PORTFOLIO_ID:
        return read_dividends()
    tr_file = latest_family_trade_republic_export(person)
    if not tr_file:
        return []
    return sorted(read_trade_republic_dividends(tr_file), key=lambda item: (item.date, item.broker, item.asset))


def read_trade_republic_dividends(path: Path) -> list[Dividend]:
    dividends: list[Dividend] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            if row.get("type") != "DIVIDEND":
                continue
            dividends.append(
                Dividend(
                    broker="Trade Republic",
                    asset=(row.get("name") or row.get("symbol") or "Unknown").strip(),
                    isin=(row.get("symbol") or "").strip().upper(),
                    date=datetime.strptime(row["date"], "%Y-%m-%d").date(),
                    amount_eur=parse_decimal(row.get("amount")),
                    tax_eur=abs(parse_decimal(row.get("tax"))),
                )
            )
    return dividends


def read_fineco_dividends(path: Path) -> list[Dividend]:
    workbook = load_workbook(path, data_only=True, read_only=True)
    sheet = workbook["Movimenti Dossier Titoli"]
    dividends: list[Dividend] = []
    for row in sheet.iter_rows(min_row=8, values_only=True):
        if not row or row[2] != "Dividendo":
            continue
        net_amount = fineco_decimal(row[10])
        dividends.append(
            Dividend(
                broker="Fineco",
                asset=str(row[3]).strip(),
                isin=str(row[4] or "").strip().upper(),
                date=parse_fineco_date(row[0]),
                amount_eur=net_amount,
                tax_eur=fineco_dividend_tax_from_net(net_amount),
            )
        )
    return dividends


def read_etoro_dividends(path: Path) -> list[Dividend]:
    workbook = load_workbook(path, data_only=True, read_only=True)
    sheet = workbook["Dividendi"]
    dividends: list[Dividend] = []
    for row in sheet.iter_rows(min_row=2, values_only=True):
        if not row or not row[0]:
            continue
        dividends.append(
            Dividend(
                broker="eToro",
                asset=str(row[1] or "").strip(),
                isin=str(row[13] or "").strip().upper(),
                date=datetime.strptime(str(row[0]), "%d/%m/%Y").date(),
                amount_eur=fineco_decimal(row[7]),
                tax_eur=fineco_decimal(row[10]),
            )
        )
    return dividends


def summarize_dividends(dividends: list[Dividend]) -> dict[str, Any]:
    by_asset: dict[str, Decimal] = {}
    by_broker: dict[str, Decimal] = {}
    total = ZERO
    tax = ZERO
    gross_total = ZERO
    rows = []
    for dividend in dividends:
        gross = dividend.amount_eur + dividend.tax_eur
        total += dividend.amount_eur
        tax += dividend.tax_eur
        gross_total += gross
        by_asset[dividend.asset] = by_asset.get(dividend.asset, ZERO) + dividend.amount_eur
        by_broker[dividend.broker] = by_broker.get(dividend.broker, ZERO) + dividend.amount_eur
        rows.append(
            {
                "date": dividend.date.isoformat(),
                "broker": dividend.broker,
                "asset": dividend.asset,
                "isin": dividend.isin,
                "amount_eur": money(dividend.amount_eur),
                "tax_eur": money(dividend.tax_eur),
                "gross_eur": money(gross),
            }
        )
    return {
        "rows": sorted(rows, key=lambda item: item["date"], reverse=True),
        "total_eur": money(total),
        "tax_eur": money(tax),
        "gross_eur": money(gross_total),
        "count": len(dividends),
        "by_asset": [{"asset": key, "amount_eur": money(value)} for key, value in sorted(by_asset.items())],
        "by_broker": [{"broker": key, "amount_eur": money(value)} for key, value in sorted(by_broker.items())],
    }


def read_cash_interests(person: str = PRIMARY_PORTFOLIO_ID) -> list[dict[str, Any]]:
    interests: list[dict[str, Any]] = []
    person = person.lower()
    
    # 1. Load Trade Republic Interest
    tr_file = None
    if person == PRIMARY_PORTFOLIO_ID:
        tr_file = latest_trade_republic_export()
    else:
        tr_file = latest_family_trade_republic_export(person)
        
    if tr_file and tr_file.exists():
        try:
            with tr_file.open(newline="", encoding="utf-8-sig") as handle:
                for row in csv.DictReader(handle):
                    if row.get("type") == "INTEREST_PAYMENT":
                        amount = parse_decimal(row.get("amount"))
                        tax = abs(parse_decimal(row.get("tax") or "0"))
                        interests.append({
                            "broker": "Trade Republic",
                            "date": datetime.strptime(row["date"], "%Y-%m-%d").date(),
                            "net_eur": amount - tax,
                            "tax_eur": tax,
                            "gross_eur": amount,
                            "description": row.get("description", "Cash Interest").strip() or "Cash Interest"
                        })
        except Exception:
            pass
                    
    # 2. Load primary-portfolio BBVA interest.
    if person == PRIMARY_PORTFOLIO_ID:
        bbva_files = sorted(ROOT_DIR.glob(SETTINGS.bbva_pattern))
        if bbva_files:
            bbva_file = bbva_files[-1]
            import shutil
            import tempfile
            temp_dir = tempfile.gettempdir()
            temp_xlsx = Path(temp_dir) / "bbva_temp.xlsx"
            try:
                shutil.copy(bbva_file, temp_xlsx)
                import openpyxl
                wb = openpyxl.load_workbook(temp_xlsx, read_only=True)
                sheet = wb.active
                for row in sheet.iter_rows(values_only=True):
                    if len(row) < 7:
                        continue
                    val_date_str, op_date_str, causale, mov, ben, imp = row[1:7]
                    if causale and "INTERESSI" in str(causale).upper() and imp:
                        try:
                            op_date = datetime.strptime(str(op_date_str).strip(), "%d/%m/%Y").date()
                        except Exception:
                            op_date = date.today()
                        try:
                            clean_imp = str(imp).replace(" EUR", "").replace(",", ".").strip()
                            amount = Decimal(clean_imp)
                        except Exception:
                            amount = ZERO
                        
                        net_val = amount
                        gross_val = net_val / Decimal("0.74") if net_val > ZERO else ZERO
                        tax_val = gross_val - net_val
                        
                        interests.append({
                            "broker": "BBVA",
                            "date": op_date,
                            "net_eur": net_val,
                            "tax_eur": tax_val,
                            "gross_eur": gross_val,
                            "description": str(causale).strip()
                        })
            except Exception:
                pass
            finally:
                if temp_xlsx.exists():
                    try:
                        temp_xlsx.unlink()
                    except Exception:
                        pass
                    
    return sorted(interests, key=lambda x: x["date"], reverse=True)


def is_revolut_internal_movement(row: dict[str, str]) -> bool:
    description = (row.get("Descrizione") or "").strip().lower()
    movement_type = (row.get("Tipo") or "").strip().lower()
    if not description and not movement_type:
        return False
    if movement_type == "cambia valuta" or description.startswith("conversione in "):
        return True
    if "balance migration to another region or legal entity" in description:
        return True
    if description == "closing transaction":
        return True
    if description.startswith("prelievo da pocket"):
        return True
    if re.fullmatch(r"to [a-z]{3}", description):
        return True
    if description.startswith("accredita ") and " da " in description:
        return True
    return False


def read_revolut_cash_events(paths: list[Path] | None = None) -> list[dict[str, Any]]:
    source_paths = paths if paths is not None else revolut_statement_files()
    events: list[dict[str, Any]] = []

    for path in source_paths:
        try:
            handle = path.open(newline="", encoding="utf-8-sig")
        except OSError:
            continue
        with handle:
            for row in csv.DictReader(handle):
                if row.get("State") != "COMPLETATO":
                    continue
                event_time = parse_revolut_datetime(row.get("Data di completamento")) or parse_revolut_datetime(row.get("Data di inizio"))
                if event_time is None:
                    continue
                amount = parse_decimal(row.get("Importo"))
                fee = abs(parse_decimal(row.get("Costo")))
                cash_change_native = amount - fee
                if cash_change_native == ZERO:
                    continue
                currency = normalize_currency_code(row.get("Valuta") or "EUR")
                contrib_change_native = ZERO if is_revolut_internal_movement(row) else cash_change_native
                events.append(
                    {
                        "datetime": event_time,
                        "date": event_time.date(),
                        "cash_change": cash_change_native,
                        "contrib_change": contrib_change_native,
                        "currency": currency,
                    }
                )

    return sorted(events, key=lambda item: item["datetime"])


def add_revolut_fx_histories(
    revolut_events: list[dict[str, Any]],
    start: date,
    end: date,
    fx_histories: dict[str, dict[str, Any]],
    refresh: bool = False,
) -> None:
    event_dates = [event["date"] for event in revolut_events if event.get("date")]
    if not event_dates:
        return
    history_start = min(min(event_dates), start) - timedelta(days=10)
    history_end = max(max(event_dates), end)
    currencies = {fx_base_currency(event.get("currency") or "EUR") for event in revolut_events}
    for currency in sorted(currencies):
        if not currency or currency == "EUR":
            continue
        symbol, _ = fx_symbol_for(currency)
        if symbol not in fx_histories:
            fx_histories[symbol] = fetch_history(symbol, history_start, history_end, refresh=refresh)


def revolut_cash_balance_eur(
    revolut_events: list[dict[str, Any]],
    target: date,
    fx_histories: dict[str, dict[str, Any]],
    live_fx_prices: dict[str, dict[str, Any]] | None = None,
) -> Decimal:
    balances: dict[str, Decimal] = {}
    for event in revolut_events:
        event_date = event.get("date")
        if not event_date or event_date > target:
            continue
        currency = normalize_currency_code(event.get("currency") or "EUR")
        balances[currency] = balances.get(currency, ZERO) + Decimal(str(event.get("cash_change") or 0))

    total = ZERO
    for currency, balance in balances.items():
        if balance == ZERO:
            continue
        rate = historical_fx_rate(currency, fx_histories, target, live_fx_prices=live_fx_prices)
        if rate is None:
            if fx_base_currency(currency) != "EUR":
                continue
            rate = 1.0
        total += balance * Decimal(str(rate))
    return total


def revolut_contributions_eur(
    revolut_events: list[dict[str, Any]],
    target: date,
    fx_histories: dict[str, dict[str, Any]],
) -> Decimal:
    total = ZERO
    for event in revolut_events:
        event_date = event.get("date")
        if not event_date or event_date > target:
            continue
        contrib_change = Decimal(str(event.get("contrib_change") or 0))
        if contrib_change == ZERO:
            continue
        currency = normalize_currency_code(event.get("currency") or "EUR")
        rate = historical_fx_rate(currency, fx_histories, event_date)
        if rate is None:
            if fx_base_currency(currency) != "EUR":
                continue
            rate = 1.0
        total += contrib_change * Decimal(str(rate))
    return total


def read_revolut_cash_history(paths: list[Path] | None = None) -> list[tuple[date, Decimal, Decimal]]:
    events = read_revolut_cash_events(paths)
    if not events:
        return []
    fx_histories: dict[str, dict[str, Any]] = {}
    event_dates = [event["date"] for event in events]
    add_revolut_fx_histories(events, min(event_dates), max(event_dates), fx_histories)
    cash_history: list[tuple[date, Decimal, Decimal]] = []
    for event in events:
        rate = historical_fx_rate(event["currency"], fx_histories, event["date"])
        if rate is None:
            if fx_base_currency(event["currency"]) != "EUR":
                continue
            rate = 1.0
        rate_dec = Decimal(str(rate))
        cash_history.append((event["date"], event["cash_change"] * rate_dec, event["contrib_change"] * rate_dec))
    return cash_history


EXPENSE_CATEGORIES = {
    "Groceries",
    "Dining",
    "Transport & Fuel",
    "Travel & Lodging",
    "Shopping",
    "Subscriptions & Digital",
    "Housing & Utilities",
    "Health & Personal Care",
    "Entertainment",
    "Education",
    "Cash Withdrawals",
    "Fees",
    "Personal Transfers",
    "Investments",
    "Credits",
    "Income",
    "Uncategorized",
}
TR_EXPENSE_TYPES = {"CARD_TRANSACTION", "CARD_TRANSACTION_INTERNATIONAL", "CARD_ORDERING_FEE"}
SELF_TRANSFER_NAMES = SETTINGS.self_transfer_names


def normalize_expense_source(value: str | None) -> str:
    raw = (value or "all").strip().lower().replace("-", "_").replace(" ", "_")
    if raw in {"trade_republic", "traderepublic", "tr"}:
        return "trade_republic"
    if raw in {"revolut", "rv"}:
        return "revolut"
    if raw in {"intesa", "intesasanpaolo", "intesa_sanpaolo"}:
        return "intesa"
    return raw or "all"


def expense_source_label(source: str) -> str:
    if source == "trade_republic":
        return "Trade Republic"
    if source == "revolut":
        return "Revolut"
    if source == "intesa":
        return "Intesa"
    return source.replace("_", " ").title()


def normalize_expense_category(value: str | None) -> str:
    category = (value or "").strip()
    return category if category in EXPENSE_CATEGORIES else "Uncategorized"


def expense_default_category(flow_kind: str) -> str:
    if flow_kind == "income":
        return "Income"
    if flow_kind == "investment":
        return "Investments"
    if flow_kind == "credit":
        return "Credits"
    if flow_kind == "personal_transfer":
        return "Personal Transfers"
    if flow_kind == "cash_withdrawal":
        return "Cash Withdrawals"
    if flow_kind == "fee":
        return "Fees"
    return "Uncategorized"


def is_self_giroconto_expense(source_category: str, merchant: str, description: str, flow_kind: str) -> bool:
    combined = f"{source_category} {merchant} {description}".lower()
    if re.search(r"\brevolut\*\*\d+\*", combined):
        return True
    if not any(name in combined for name in SELF_TRANSFER_NAMES):
        return False
    category = source_category.lower()
    if "bonific" in category or "giroconto" in category:
        return True
    return flow_kind in {"personal_transfer", "income"}


def read_expense_category_rules(path: Path = EXPENSE_RULES_CSV) -> list[ExpenseRule]:
    if not path.exists():
        return []
    rules: list[ExpenseRule] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for index, row in enumerate(csv.DictReader(handle), start=1):
            enabled = (row.get("enabled") or "1").strip().lower()
            if enabled in {"0", "false", "no", "off"}:
                continue
            try:
                priority = int((row.get("priority") or index).strip())
            except ValueError:
                priority = index
            rules.append(
                ExpenseRule(
                    priority=priority,
                    source=normalize_expense_source(row.get("source") or "all"),
                    match_field=(row.get("match_field") or "description").strip().lower(),
                    match_type=(row.get("match_type") or "contains").strip().lower(),
                    pattern=(row.get("pattern") or "").strip(),
                    category=normalize_expense_category(row.get("category")),
                    subcategory=(row.get("subcategory") or "").strip(),
                    merchant=(row.get("merchant") or "").strip(),
                )
            )
    return sorted(rules, key=lambda item: item.priority)


def expense_match_text(event: dict[str, Any], field: str) -> str:
    if field == "all":
        parts = [
            event.get("source", ""),
            event.get("merchant", ""),
            event.get("description", ""),
            event.get("flow_kind", ""),
            event.get("category", ""),
            event.get("subcategory", ""),
            event.get("source_category", ""),
            str(event.get("native_amount") or ""),
            str(event.get("amount_eur") or ""),
        ]
        return " ".join(str(part or "") for part in parts)
    return str(event.get(field) or "")


def expense_rule_matches(event: dict[str, Any], rule: ExpenseRule) -> bool:
    if rule.source not in {"", "all", normalize_expense_source(str(event.get("source") or ""))}:
        return False
    pattern = rule.pattern
    if not pattern:
        return False
    value = expense_match_text(event, rule.match_field)
    if rule.match_type == "exact":
        return value.strip().lower() == pattern.strip().lower()
    if rule.match_type == "regex":
        try:
            return re.search(pattern, value, flags=re.IGNORECASE) is not None
        except re.error:
            return False
    return pattern.lower() in value.lower()


def classify_expense_event(event: dict[str, Any], rules: list[ExpenseRule]) -> dict[str, Any]:
    classified = dict(event)
    classified["category"] = normalize_expense_category(classified.get("category"))
    classified.setdefault("subcategory", "")
    classified.setdefault("confidence", 0.35)
    for rule in rules:
        if not expense_rule_matches(classified, rule):
            continue
        classified["category"] = rule.category
        classified["subcategory"] = rule.subcategory
        if rule.merchant:
            classified["merchant"] = rule.merchant
        classified["confidence"] = 0.95
        break
    if classified["category"] == "Credits":
        classified["flow_kind"] = "credit"
    return classified


def make_expense_event(
    *,
    event_date: date,
    source: str,
    merchant: str,
    description: str,
    flow_kind: str,
    amount_eur: Decimal,
    currency: str,
    native_amount: Decimal,
    rules: list[ExpenseRule],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event = {
        "date": event_date,
        "source": normalize_expense_source(source),
        "merchant": (merchant or description or "Unknown").strip() or "Unknown",
        "description": (description or merchant or "").strip(),
        "flow_kind": flow_kind,
        "category": expense_default_category(flow_kind),
        "subcategory": "",
        "amount_eur": amount_eur,
        "currency": normalize_currency_code(currency),
        "native_amount": native_amount,
        "confidence": 0.65 if flow_kind != "spend" else 0.35,
    }
    if extra:
        event.update(extra)
    return classify_expense_event(event, rules)


def revolut_expense_flow_kind(row: dict[str, str], cash_change_native: Decimal) -> str:
    movement_type = (row.get("Tipo") or "").strip().lower()
    description = (row.get("Descrizione") or "").strip().lower()
    if is_revolut_internal_movement(row):
        return ""
    if "al conto di investimento" in description:
        return "investment"
    if movement_type == "pagamento con carta":
        return "income" if cash_change_native > ZERO else "spend"
    if movement_type in {"rimborso su carta", "cashback"}:
        return "income"
    if movement_type == "prelievo" and cash_change_native < ZERO:
        return "cash_withdrawal"
    if movement_type == "commissione" and cash_change_native < ZERO:
        return "fee"
    if movement_type == "pagamento" and cash_change_native < ZERO:
        return "personal_transfer"
    return ""


def expense_amount_to_eur(
    signed_native_amount: Decimal,
    currency: str,
    event_date: date,
    fx_histories: dict[str, dict[str, Any]],
) -> Decimal | None:
    currency = normalize_currency_code(currency)
    rate = historical_fx_rate(currency, fx_histories, event_date)
    if rate is None:
        if fx_base_currency(currency) != "EUR":
            return None
        rate = 1.0
    return abs(signed_native_amount) * Decimal(str(rate))


def read_revolut_expense_events(
    paths: list[Path] | None = None,
    rules: list[ExpenseRule] | None = None,
    fx_histories: dict[str, dict[str, Any]] | None = None,
    refresh: bool = False,
) -> list[dict[str, Any]]:
    source_paths = paths if paths is not None else revolut_statement_files()
    active_rules = rules if rules is not None else read_expense_category_rules()
    raw_events: list[dict[str, Any]] = []

    for path in source_paths:
        try:
            handle = path.open(newline="", encoding="utf-8-sig")
        except OSError:
            continue
        with handle:
            for row in csv.DictReader(handle):
                if row.get("State") != "COMPLETATO":
                    continue
                event_time = parse_revolut_datetime(row.get("Data di completamento")) or parse_revolut_datetime(row.get("Data di inizio"))
                if event_time is None:
                    continue
                amount = parse_decimal(row.get("Importo"))
                fee = abs(parse_decimal(row.get("Costo")))
                cash_change_native = amount - fee
                if cash_change_native == ZERO:
                    continue
                flow_kind = revolut_expense_flow_kind(row, cash_change_native)
                if not flow_kind:
                    continue
                merchant = (row.get("Descrizione") or "").strip() or (row.get("Tipo") or "Revolut").strip()
                description = (row.get("Descrizione") or row.get("Tipo") or "").strip()
                if is_self_giroconto_expense("", merchant, description, flow_kind):
                    continue
                raw_events.append(
                    {
                        "date": event_time.date(),
                        "datetime": event_time,
                        "source": "revolut",
                        "merchant": merchant,
                        "description": description,
                        "flow_kind": flow_kind,
                        "currency": normalize_currency_code(row.get("Valuta") or "EUR"),
                        "native_amount": cash_change_native,
                    }
                )

    if not raw_events:
        return []

    histories = fx_histories if fx_histories is not None else {}
    event_dates = [event["date"] for event in raw_events]
    add_revolut_fx_histories(raw_events, min(event_dates), max(event_dates), histories, refresh=refresh)

    events: list[dict[str, Any]] = []
    for raw_event in raw_events:
        amount_eur = expense_amount_to_eur(
            Decimal(str(raw_event["native_amount"])),
            raw_event["currency"],
            raw_event["date"],
            histories,
        )
        if amount_eur is None:
            continue
        events.append(
            make_expense_event(
                event_date=raw_event["date"],
                source=raw_event["source"],
                merchant=raw_event["merchant"],
                description=raw_event["description"],
                flow_kind=raw_event["flow_kind"],
                amount_eur=amount_eur,
                currency=raw_event["currency"],
                native_amount=raw_event["native_amount"],
                rules=active_rules,
            )
        )
    return sorted(events, key=lambda item: (item["date"], item["source"], item["merchant"]))


def read_trade_republic_expense_events(path: Path, rules: list[ExpenseRule] | None = None) -> list[dict[str, Any]]:
    active_rules = rules if rules is not None else read_expense_category_rules()
    events: list[dict[str, Any]] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            t_type = (row.get("type") or "").strip()
            if t_type not in TR_EXPENSE_TYPES:
                continue
            event_date_raw = row.get("date")
            if not event_date_raw:
                continue
            event_date = datetime.strptime(event_date_raw, "%Y-%m-%d").date()
            amount = parse_decimal(row.get("amount"))
            fee = parse_decimal(row.get("fee"))
            tax = parse_decimal(row.get("tax"))
            cash_change = amount + fee + tax
            if cash_change == ZERO:
                continue
            original_currency = normalize_currency_code(row.get("original_currency") or "")
            native_currency = original_currency if original_currency not in {"", "EUR"} else normalize_currency_code(row.get("currency") or "EUR")
            original_amount = parse_decimal(row.get("original_amount"))
            native_amount = original_amount if original_amount != ZERO and native_currency != "EUR" else cash_change
            merchant = (row.get("name") or row.get("description") or row.get("type") or "Trade Republic").strip()
            description = (row.get("description") or merchant or t_type).strip()
            if t_type == "CARD_ORDERING_FEE":
                flow_kind = "fee"
                merchant = merchant if merchant != t_type else "Trade Republic Card"
            else:
                flow_kind = "income" if cash_change > ZERO else "spend"
            if is_self_giroconto_expense("", merchant, description, flow_kind):
                continue
            events.append(
                make_expense_event(
                    event_date=event_date,
                    source="trade_republic",
                    merchant=merchant,
                    description=description,
                    flow_kind=flow_kind,
                    amount_eur=abs(cash_change),
                    currency=native_currency,
                    native_amount=native_amount,
                    rules=active_rules,
                )
            )
    return sorted(events, key=lambda item: (item["date"], item["source"], item["merchant"]))


def intesa_cell_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def parse_intesa_expense_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = intesa_cell_text(value)
    if not raw:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    return None


def intesa_expense_flow_kind(source_category: str, merchant: str, description: str, amount: Decimal) -> str:
    if amount > ZERO:
        return "income"
    category = source_category.strip().lower()
    combined = f"{merchant} {description}".lower()
    if "preliev" in category or "preliev" in combined:
        return "cash_withdrawal"
    if "imposte" in category or "commission" in category or "commission" in combined or "interessi debitori" in combined:
        return "fee"
    if "bonifici in uscita" in category or "giroconto in uscita" in category:
        return "personal_transfer"
    return "spend"


def read_intesa_expense_events(
    path: Path,
    rules: list[ExpenseRule] | None = None,
    fx_histories: dict[str, dict[str, Any]] | None = None,
    refresh: bool = False,
) -> list[dict[str, Any]]:
    active_rules = rules if rules is not None else read_expense_category_rules()
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Print area cannot be set*", category=UserWarning)
        workbook = load_workbook(path, data_only=True, read_only=True)
    sheet = workbook["Lista Operazione"] if "Lista Operazione" in workbook.sheetnames else workbook[workbook.sheetnames[0]]

    header_row_number: int | None = None
    headers: list[str] = []
    required_headers = {"Data", "Operazione", "Importo"}
    for row_number, row in enumerate(sheet.iter_rows(values_only=True), start=1):
        candidate = [intesa_cell_text(value) for value in row]
        if required_headers.issubset(set(candidate)):
            header_row_number = row_number
            headers = candidate
            break
    if header_row_number is None:
        return []

    raw_events: list[dict[str, Any]] = []
    for row in sheet.iter_rows(min_row=header_row_number + 1, values_only=True):
        if not row or not any(intesa_cell_text(value) for value in row):
            continue
        record = {
            header: row[index] if index < len(row) else None
            for index, header in enumerate(headers)
            if header
        }
        accounted = intesa_cell_text(record.get("Contabilizzazione")).upper()
        if accounted and not (accounted.startswith("S") or accounted in {"YES", "Y", "TRUE", "1"}):
            continue
        event_date = parse_intesa_expense_date(record.get("Data"))
        if event_date is None:
            continue
        amount = fineco_decimal(record.get("Importo"))
        if amount == ZERO:
            continue
        source_category = intesa_cell_text(record.get("Categoria"))
        merchant = intesa_cell_text(record.get("Operazione"))
        description = intesa_cell_text(record.get("Dettagli")) or merchant
        currency = normalize_currency_code(record.get("Valuta") or "EUR")
        flow_kind = intesa_expense_flow_kind(source_category, merchant, description, amount)
        if is_self_giroconto_expense(source_category, merchant, description, flow_kind):
            continue
        raw_events.append(
            {
                "date": event_date,
                "source": "intesa",
                "merchant": merchant or description or "Intesa",
                "description": description,
                "flow_kind": flow_kind,
                "currency": currency,
                "native_amount": amount,
                "source_category": source_category,
            }
        )

    if not raw_events:
        return []

    histories = fx_histories if fx_histories is not None else {}
    event_dates = [event["date"] for event in raw_events]
    add_revolut_fx_histories(raw_events, min(event_dates), max(event_dates), histories, refresh=refresh)

    events: list[dict[str, Any]] = []
    for raw_event in raw_events:
        amount_eur = expense_amount_to_eur(
            Decimal(str(raw_event["native_amount"])),
            raw_event["currency"],
            raw_event["date"],
            histories,
        )
        if amount_eur is None:
            continue
        events.append(
            make_expense_event(
                event_date=raw_event["date"],
                source=raw_event["source"],
                merchant=raw_event["merchant"],
                description=raw_event["description"],
                flow_kind=raw_event["flow_kind"],
                amount_eur=amount_eur,
                currency=raw_event["currency"],
                native_amount=raw_event["native_amount"],
                rules=active_rules,
                extra={"source_category": raw_event["source_category"]},
            )
        )
    return sorted(events, key=lambda item: (item["date"], item["source"], item["merchant"]))


def read_bbva_expense_events(
    paths: list[Path] | None = None,
    rules: list[ExpenseRule] | None = None,
    fx_histories: dict[str, dict[str, Any]] | None = None,
    refresh: bool = False,
) -> list[dict[str, Any]]:
    active_rules = rules if rules is not None else read_expense_category_rules()
    bbva_files = paths if paths is not None else sorted(ROOT_DIR.glob(SETTINGS.bbva_pattern))
    if not bbva_files:
        return []

    raw_events: list[dict[str, Any]] = []
    seen_keys = set()

    import shutil
    import tempfile
    import os
    import threading

    for bbva_file in bbva_files:
        temp_xlsx = Path(tempfile.gettempdir()) / f"bbva_temp_{os.getpid()}_{threading.get_ident()}.xlsx"
        try:
            shutil.copy(bbva_file, temp_xlsx)
            wb = load_workbook(temp_xlsx, read_only=True)
            sheet = wb.active
            for row in sheet.iter_rows(values_only=True):
                if len(row) < 7:
                    continue
                # columns B to G (index 1 to 6)
                data_valuta = row[1]
                op_date_str = row[2]
                causale = row[3]
                movimento = row[4]
                beneficiario = row[5]
                imp = row[6]

                if causale and causale != "Causale" and imp:
                    try:
                        op_date = datetime.strptime(str(op_date_str).strip(), "%d/%m/%Y").date()
                    except Exception:
                        continue
                    try:
                        clean_imp = str(imp).replace(" EUR", "").replace(",", ".").strip()
                        amount = Decimal(clean_imp)
                    except Exception:
                        continue

                    if amount == ZERO:
                        continue

                    # Clean counterparty / beneficiary
                    benef = ""
                    if beneficiario:
                        benef = str(beneficiario).split("\n")[0].strip()
                        if benef == "-":
                            benef = ""

                    # Dedup check
                    key = (op_date, str(causale), str(movimento), benef, amount)
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)

                    flow_kind = "spend"
                    if amount > 0:
                        flow_kind = "income"
                    else:
                        causale_upper = str(causale).upper()
                        if "COMMISS" in causale_upper or "SPESE" in causale_upper:
                            flow_kind = "fee"

                    merchant = benef if benef else (str(movimento).strip() if movimento else (str(causale).strip() if causale else "BBVA"))
                    description = str(movimento).strip() if movimento else (str(causale).strip() if causale else "")
                    source_category = str(causale).strip() if causale else ""

                    if is_self_giroconto_expense(source_category, merchant, description, flow_kind):
                        continue

                    raw_events.append(
                        {
                            "date": op_date,
                            "source": "bbva",
                            "merchant": merchant,
                            "description": description,
                            "flow_kind": flow_kind,
                            "currency": "EUR",
                            "native_amount": amount,
                            "source_category": source_category,
                        }
                    )
        except Exception:
            pass
        finally:
            if temp_xlsx.exists():
                try:
                    temp_xlsx.unlink()
                except OSError:
                    pass

    if not raw_events:
        return []

    histories = fx_histories if fx_histories is not None else {}
    events: list[dict[str, Any]] = []
    for raw_event in raw_events:
        amount_eur = expense_amount_to_eur(
            Decimal(str(raw_event["native_amount"])),
            raw_event["currency"],
            raw_event["date"],
            histories,
        )
        if amount_eur is None:
            continue
        events.append(
            make_expense_event(
                event_date=raw_event["date"],
                source=raw_event["source"],
                merchant=raw_event["merchant"],
                description=raw_event["description"],
                flow_kind=raw_event["flow_kind"],
                amount_eur=amount_eur,
                currency=raw_event["currency"],
                native_amount=raw_event["native_amount"],
                rules=active_rules,
                extra={"source_category": raw_event["source_category"]},
            )
        )
    return sorted(events, key=lambda item: (item["date"], item["source"], item["merchant"]))


def read_expense_events(person: str = PRIMARY_PORTFOLIO_ID, refresh: bool = False) -> list[dict[str, Any]]:
    if (person or PRIMARY_PORTFOLIO_ID).lower() != PRIMARY_PORTFOLIO_ID:
        return []
    rules = read_expense_category_rules()
    events: list[dict[str, Any]] = []
    tr_file = latest_trade_republic_export()
    if tr_file:
        try:
            events.extend(read_trade_republic_expense_events(tr_file, rules=rules))
        except Exception:
            pass
    intesa_file = latest_intesa_operations_export()
    if intesa_file:
        try:
            events.extend(read_intesa_expense_events(intesa_file, rules=rules, refresh=refresh))
        except Exception:
            pass
    try:
        events.extend(read_revolut_expense_events(rules=rules, refresh=refresh))
    except Exception:
        pass
    try:
        events.extend(read_bbva_expense_events(rules=rules, refresh=refresh))
    except Exception:
        pass
    return sorted(events, key=lambda item: (item["date"], item["source"], item["merchant"]))


def expense_row_kind(row: dict[str, Any]) -> str:
    flow_kind = str(row.get("flow_kind") or "")
    category = str(row.get("category") or "")
    if flow_kind == "income" or category == "Income":
        return "income"
    if flow_kind == "credit" or category == "Credits":
        return "credits"
    if flow_kind == "investment" or category == "Investments":
        return "investments"
    if flow_kind == "personal_transfer" or category == "Personal Transfers":
        return "transfers"
    return "spend"


def expense_event_payload(event: dict[str, Any]) -> dict[str, Any]:
    event_date = event.get("date")
    if isinstance(event_date, date):
        date_value = event_date.isoformat()
    else:
        date_value = str(event_date or "")
    return {
        "date": date_value,
        "source": event.get("source") or "",
        "source_label": expense_source_label(str(event.get("source") or "")),
        "merchant": event.get("merchant") or "Unknown",
        "description": event.get("description") or "",
        "flow_kind": event.get("flow_kind") or "spend",
        "category": normalize_expense_category(str(event.get("category") or "")),
        "subcategory": event.get("subcategory") or "",
        "amount_eur": money(Decimal(str(event.get("amount_eur") or 0))),
        "currency": normalize_currency_code(event.get("currency") or "EUR"),
        "native_amount": decimal_to_float(Decimal(str(event.get("native_amount") or 0))),
        "confidence": round(float(event.get("confidence") or 0), 2),
    }


def summarize_expense_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [expense_event_payload(event) for event in sorted(events, key=lambda item: item["date"], reverse=True)]
    spend = ZERO
    income = ZERO
    transfers = ZERO
    investments = ZERO
    credits = ZERO
    by_category: dict[str, dict[str, Any]] = {}
    by_source: dict[str, dict[str, Any]] = {}
    by_month: dict[str, dict[str, Decimal]] = {}
    by_merchant: dict[str, dict[str, Any]] = {}
    credit_rows: list[dict[str, Any]] = []

    for row in rows:
        amount = Decimal(str(row.get("amount_eur") or 0))
        kind = expense_row_kind(row)
        if kind == "income":
            income += amount
        elif kind == "credits":
            credits += amount
            credit_rows.append(row)
        elif kind == "investments":
            investments += amount
        elif kind == "transfers":
            transfers += amount
        else:
            spend += amount

        category = normalize_expense_category(str(row.get("category") or ""))
        cat_bucket = by_category.setdefault(category, {"category": category, "amount": ZERO, "count": 0})
        cat_bucket["amount"] += amount
        cat_bucket["count"] += 1

        source = row.get("source_label") or expense_source_label(str(row.get("source") or ""))
        source_bucket = by_source.setdefault(str(source), {"source": str(source), "spend": ZERO, "income": ZERO, "transfers": ZERO, "investments": ZERO, "credits": ZERO, "count": 0})
        source_bucket[kind if kind != "spend" else "spend"] += amount
        source_bucket["count"] += 1

        month = str(row.get("date") or "")[:7]
        if month:
            month_bucket = by_month.setdefault(month, {"month": month, "spend": ZERO, "income": ZERO, "transfers": ZERO, "investments": ZERO, "credits": ZERO, "count": 0})
            month_bucket[kind if kind != "spend" else "spend"] += amount
            month_bucket["count"] += 1

        if kind not in {"income", "credits"}:
            merchant = str(row.get("merchant") or "Unknown")
            merch_bucket = by_merchant.setdefault(merchant, {"merchant": merchant, "category": category, "amount": ZERO, "count": 0})
            merch_bucket["amount"] += amount
            merch_bucket["count"] += 1

    net_outflow = spend + investments - income
    total_outflow = spend + investments
    category_rows = [
        {
            "category": values["category"],
            "amount_eur": money(values["amount"]),
            "count": values["count"],
            "share_pct": float((values["amount"] / total_outflow * Decimal("100")).quantize(Decimal("0.01"))) if total_outflow and values["category"] not in {"Income", "Credits", "Personal Transfers"} else None,
        }
        for values in by_category.values()
        if values["category"] not in {"Income", "Credits", "Personal Transfers"}
    ]
    source_rows = [
        {
            "source": values["source"],
            "spend_eur": money(values["spend"]),
            "income_eur": money(values["income"]),
            "transfers_eur": money(values["transfers"]),
            "investments_eur": money(values["investments"]),
            "credits_eur": money(values["credits"]),
            "net_outflow_eur": money(values["spend"] + values["investments"] - values["income"]),
            "count": values["count"],
        }
        for values in by_source.values()
    ]
    month_rows = [
        {
            "month": values["month"],
            "spend_eur": money(values["spend"]),
            "income_eur": money(values["income"]),
            "transfers_eur": money(values["transfers"]),
            "investments_eur": money(values["investments"]),
            "credits_eur": money(values["credits"]),
            "net_outflow_eur": money(values["spend"] + values["investments"] - values["income"]),
            "count": values["count"],
        }
        for values in by_month.values()
    ]
    merchant_rows = [
        {
            "merchant": values["merchant"],
            "category": values["category"],
            "amount_eur": money(values["amount"]),
            "count": values["count"],
        }
        for values in by_merchant.values()
    ]

    return {
        "status": "available" if rows else "empty",
        "summary": {
            "spend_eur": money(spend),
            "income_eur": money(income),
            "transfers_eur": money(transfers),
            "investments_eur": money(investments),
            "credits_eur": money(credits),
            "net_outflow_eur": money(net_outflow),
            "rows_count": len(rows),
        },
        "by_category": sorted(category_rows, key=lambda item: float(item.get("amount_eur") or 0), reverse=True),
        "by_source": sorted(source_rows, key=lambda item: abs(float(item.get("net_outflow_eur") or 0)), reverse=True),
        "by_month": sorted(month_rows, key=lambda item: item["month"]),
        "top_merchants": sorted(merchant_rows, key=lambda item: float(item.get("amount_eur") or 0), reverse=True)[:20],
        "credits": sorted(credit_rows, key=lambda item: item["date"], reverse=True),
        "recent_rows": rows[:30],
        "rows": rows,
        "rules_file": configured_path_label(EXPENSE_RULES_CSV),
    }


def empty_expenses(message: str = "No expense data available for this selection.") -> dict[str, Any]:
    return {
        "status": "empty",
        "message": message,
        "summary": {
            "spend_eur": 0.0,
            "income_eur": 0.0,
            "transfers_eur": 0.0,
            "investments_eur": 0.0,
            "credits_eur": 0.0,
            "net_outflow_eur": 0.0,
            "rows_count": 0,
        },
        "by_category": [],
        "by_source": [],
        "by_month": [],
        "top_merchants": [],
        "credits": [],
        "recent_rows": [],
        "rows": [],
        "rules_file": configured_path_label(EXPENSE_RULES_CSV),
    }


def summarize_cash_interests(interests: list[dict[str, Any]]) -> dict[str, Any]:
    total_net = ZERO
    total_tax = ZERO
    total_gross = ZERO
    
    by_broker_dict = {}
    for item in interests:
        total_net += item["net_eur"]
        total_tax += item["tax_eur"]
        total_gross += item["gross_eur"]
        
        b = item["broker"]
        by_broker_dict.setdefault(b, {"net_eur": ZERO, "tax_eur": ZERO, "gross_eur": ZERO, "count": 0})
        by_broker_dict[b]["net_eur"] += item["net_eur"]
        by_broker_dict[b]["tax_eur"] += item["tax_eur"]
        by_broker_dict[b]["gross_eur"] += item["gross_eur"]
        by_broker_dict[b]["count"] += 1
        
    by_broker = []
    for b, vals in sorted(by_broker_dict.items()):
        by_broker.append({
            "broker": b,
            "net_eur": money(vals["net_eur"]),
            "tax_eur": money(vals["tax_eur"]),
            "gross_eur": money(vals["gross_eur"]),
            "payments_count": vals["count"]
        })
        
    payments = []
    for item in interests:
        payments.append({
            "broker": item["broker"],
            "date": item["date"].isoformat(),
            "net_eur": money(item["net_eur"]),
            "tax_eur": money(item["tax_eur"]),
            "gross_eur": money(item["gross_eur"]),
            "description": item["description"]
        })
        
    return {
        "summary": {
            "total_net_eur": money(total_net),
            "total_tax_eur": money(total_tax),
            "total_gross_eur": money(total_gross),
            "payments_count": len(interests),
        },
        "by_broker": by_broker,
        "payments": payments
    }


def summarize_net_contributions(trades: list[Trade]) -> dict[str, Any]:
    by_broker: dict[str, dict[str, Decimal]] = {}
    by_date: dict[str, dict[str, Decimal]] = {}
    total_buys = ZERO
    total_sells = ZERO

    for trade in trades:
        amount, _ = trade_cash_amount(trade)
        broker = trade.broker
        day = trade.date.isoformat()
        by_broker.setdefault(broker, {"buys": ZERO, "sells": ZERO})
        by_date.setdefault(day, {"buys": ZERO, "sells": ZERO})
        if trade.quantity_diff >= ZERO:
            total_buys += amount
            by_broker[broker]["buys"] += amount
            by_date[day]["buys"] += amount
        else:
            total_sells += amount
            by_broker[broker]["sells"] += amount
            by_date[day]["sells"] += amount

    total_net = total_buys - total_sells
    broker_rows = []
    for broker, values in sorted(by_broker.items()):
        net = values["buys"] - values["sells"]
        broker_rows.append(
            {
                "broker": broker,
                "buys_eur": money(values["buys"]),
                "sells_eur": money(values["sells"]),
                "net_eur": money(net),
                "share_pct": float((net / total_net * Decimal("100")).quantize(Decimal("0.01"))) if total_net else None,
            }
        )

    date_rows = []
    for day, values in sorted(by_date.items(), reverse=True):
        net = values["buys"] - values["sells"]
        if net == ZERO:
            continue
        date_rows.append(
            {
                "date": day,
                "buys_eur": money(values["buys"]),
                "sells_eur": money(values["sells"]),
                "net_eur": money(net),
            }
        )

    return {
        "total_buys_eur": money(total_buys),
        "total_sells_eur": money(total_sells),
        "net_eur": money(total_net),
        "by_broker": broker_rows,
        "by_date": date_rows,
    }


def trade_friction_events(trades: list[Trade]) -> list[FrictionEvent]:
    events: list[FrictionEvent] = []
    for trade in trades:
        if trade.fees:
            amount, _ = convert_cash_to_eur(trade.fees, trade.cash_currency, trade.date)
            if amount:
                events.append(
                    FrictionEvent(
                        broker=trade.broker,
                        event_type="cost",
                        date=trade.date,
                        amount_eur=amount,
                        description=f"{trade.action} commission - {trade.asset}",
                    )
                )
        if trade.tax:
            amount, _ = convert_cash_to_eur(trade.tax, trade.cash_currency, trade.date)
            if amount:
                events.append(
                    FrictionEvent(
                        broker=trade.broker,
                        event_type="tax",
                        date=trade.date,
                        amount_eur=amount,
                        description=f"{trade.action} tax - {trade.asset}",
                    )
                )
    return events


def inferred_fineco_sell_tax_events(trades: list[Trade]) -> list[FrictionEvent]:
    quantities: dict[str, Decimal] = {}
    cost_basis: dict[str, Decimal] = {}
    events: list[FrictionEvent] = []

    for trade in trades:
        asset_key = trade.isin or trade.asset
        quantities.setdefault(asset_key, ZERO)
        cost_basis.setdefault(asset_key, ZERO)
        amount, _ = trade_cash_amount(trade)

        if trade.quantity_diff >= ZERO:
            quantities[asset_key] += trade.quantity_diff
            cost_basis[asset_key] += amount
            continue

        sell_quantity = abs(trade.quantity_diff)
        previous_quantity = quantities[asset_key]
        previous_cost = cost_basis[asset_key]
        if previous_quantity > ZERO and sell_quantity > ZERO:
            removed_cost = min(previous_cost, previous_cost * sell_quantity / previous_quantity)
        else:
            removed_cost = ZERO

        net_gain = amount - removed_cost
        if trade.broker == "Fineco" and trade.tax == ZERO and net_gain > ZERO:
            tax = fineco_capital_gain_tax_from_net_gain(net_gain)
            if tax:
                events.append(
                    FrictionEvent(
                        broker="Fineco",
                        event_type="tax",
                        date=trade.date,
                        amount_eur=tax,
                        description=f"Implied capital gain tax - {trade.asset}",
                    )
                )

        cost_basis[asset_key] = max(ZERO, previous_cost - removed_cost)
        quantities[asset_key] = previous_quantity - sell_quantity

    return events


def read_trade_republic_tax_events(path: Path) -> list[FrictionEvent]:
    events: list[FrictionEvent] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            if row.get("type") not in {"TAX_OPTIMIZATION", "DIVIDEND"}:
                continue
            raw_tax = parse_decimal(row.get("tax"))
            if not raw_tax:
                continue
            paid_tax = -raw_tax
            event_date = datetime.strptime(row["date"], "%Y-%m-%d").date()
            events.append(
                FrictionEvent(
                    broker="Trade Republic",
                    event_type="dividend_tax" if row.get("type") == "DIVIDEND" else "tax",
                    date=event_date,
                    amount_eur=paid_tax,
                    description=(row.get("description") or row.get("name") or row.get("type") or "Tax").strip(),
                )
            )
    return events


def read_fineco_friction_events(path: Path) -> list[FrictionEvent]:
    workbook = load_workbook(path, data_only=True, read_only=True)
    sheet = workbook["Movimenti Dossier Titoli"]
    events: list[FrictionEvent] = []
    for row in sheet.iter_rows(min_row=8, values_only=True):
        if not row or row[2] != "Dividendo":
            continue
        net_amount = fineco_decimal(row[10])
        tax = fineco_dividend_tax_from_net(net_amount)
        if not tax:
            continue
        events.append(
            FrictionEvent(
                broker="Fineco",
                event_type="dividend_tax",
                date=parse_fineco_date(row[0]),
                amount_eur=tax,
                description=f"Implied dividend withholding - {str(row[3] or '').strip()}",
            )
        )
    return events


def read_etoro_friction_events(path: Path) -> list[FrictionEvent]:
    workbook = load_workbook(path, data_only=True, read_only=True)
    events: list[FrictionEvent] = []

    if "Dividendi" in workbook.sheetnames:
        dividends = workbook["Dividendi"]
        for row in dividends.iter_rows(min_row=2, values_only=True):
            if not row or not row[0]:
                continue
            tax = fineco_decimal(row[10])
            if not tax:
                continue
            events.append(
                FrictionEvent(
                    broker="eToro",
                    event_type="dividend_tax",
                    date=datetime.strptime(str(row[0]), "%d/%m/%Y").date(),
                    amount_eur=tax,
                    description=f"Dividend withholding - {str(row[1] or '').strip()}",
                )
            )

    if "Posizioni chiuse" in workbook.sheetnames:
        closed = workbook["Posizioni chiuse"]
        for row in closed.iter_rows(min_row=2, values_only=True):
            if not row or not row[6]:
                continue
            closed_at = datetime.strptime(str(row[6]), "%d/%m/%Y %H:%M:%S").date()
            asset = str(row[1] or "Closed position").strip()
            spread_usd = abs(fineco_decimal(row[8]))
            overnight_usd = abs(fineco_decimal(row[18]))
            for label, amount_usd in (("Spread fee", spread_usd), ("Overnight fee/dividend", overnight_usd)):
                if not amount_usd:
                    continue
                amount_eur, _ = convert_cash_to_eur(amount_usd, "USD", closed_at)
                events.append(
                    FrictionEvent(
                        broker="eToro",
                        event_type="cost",
                        date=closed_at,
                        amount_eur=amount_eur,
                        description=f"{label} - {asset}",
                    )
                )
    return events


def read_extra_friction_events() -> list[FrictionEvent]:
    events: list[FrictionEvent] = []
    tr_file = latest_trade_republic_export()
    fineco_file = latest_fineco_export()
    etoro_file = latest_etoro_export()
    if tr_file:
        events.extend(read_trade_republic_tax_events(tr_file))
    if fineco_file:
        events.extend(read_fineco_friction_events(fineco_file))
    if etoro_file:
        events.extend(read_etoro_friction_events(etoro_file))
    return events


def summarize_frictions(events: list[FrictionEvent], market_value: Decimal | float | int | None) -> dict[str, Any]:
    costs = ZERO
    trade_taxes = ZERO
    dividend_taxes = ZERO
    by_broker: dict[str, dict[str, Decimal]] = {}
    rows = []

    for event in sorted(events, key=lambda item: (item.date, item.broker, item.description), reverse=True):
        by_broker.setdefault(event.broker, {"costs": ZERO, "taxes": ZERO, "dividend_tax": ZERO})
        if event.event_type == "cost":
            costs += event.amount_eur
            by_broker[event.broker]["costs"] += event.amount_eur
            type_label = "Cost"
        elif event.event_type == "dividend_tax":
            dividend_taxes += event.amount_eur
            by_broker[event.broker]["dividend_tax"] += event.amount_eur
            type_label = "Dividend tax"
        else:
            trade_taxes += event.amount_eur
            by_broker[event.broker]["taxes"] += event.amount_eur
            type_label = "Tax"
        rows.append(
            {
                "date": event.date.isoformat(),
                "broker": event.broker,
                "type": event.event_type,
                "type_label": type_label,
                "description": event.description,
                "amount_eur": money(event.amount_eur),
            }
        )

    tax_total = trade_taxes + dividend_taxes
    total_drag = costs + tax_total
    market = Decimal(str(market_value)) if market_value is not None else ZERO
    broker_rows = []
    for broker, values in sorted(by_broker.items()):
        taxes = values["taxes"] + values["dividend_tax"]
        total = values["costs"] + taxes
        if not total:
            continue
        broker_rows.append(
            {
                "broker": broker,
                "costs_eur": money(values["costs"]),
                "taxes_eur": money(taxes),
                "dividend_tax_eur": money(values["dividend_tax"]),
                "total_eur": money(total),
            }
        )

    return {
        "status": "available",
        "message": "",
        "total_costs_eur": money(costs),
        "total_taxes_eur": money(tax_total),
        "trade_taxes_eur": money(trade_taxes),
        "dividend_tax_eur": money(dividend_taxes),
        "total_drag_eur": money(total_drag),
        "net_liquidation_eur": money(market - total_drag),
        "by_broker": broker_rows,
        "rows": rows,
    }


def empty_frictions(status: str = "unavailable", message: str = "") -> dict[str, Any]:
    return {
        "status": status,
        "message": message,
        "total_costs_eur": 0.0,
        "total_taxes_eur": 0.0,
        "trade_taxes_eur": 0.0,
        "dividend_tax_eur": 0.0,
        "total_drag_eur": 0.0,
        "net_liquidation_eur": None,
        "by_broker": [],
        "rows": [],
    }


def latest_family_file(person: str) -> Path | None:
    config = FAMILY_PORTFOLIOS.get(person)
    if not config:
        return None
    files = sorted(ROOT_DIR.glob(config["pattern"]))
    return files[-1] if files else None


def csv_number(value: str | None) -> Decimal | None:
    raw = (value or "").strip()
    if not raw or raw == "#N/A":
        return None
    if "," not in raw and "." in raw:
        parts = raw.split(".")
        if len(parts) > 1 and all(len(part) == 3 for part in parts[1:]):
            raw = "".join(parts)
    return parse_decimal(raw)


def parse_snapshot_date(value: str) -> date:
    return datetime.strptime(value.strip(), "%d/%m/%Y").date()


def read_family_snapshot(person: str) -> dict[str, Any]:
    path = latest_family_file(person)
    if not path:
        raise FileNotFoundError(f"Missing family portfolio CSV for {person}.")

    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.reader(handle))
    header = rows[0]
    date_cols = [(idx, parse_snapshot_date(label)) for idx, label in enumerate(header) if "/" in label]

    data_rows = []
    for row in rows[2:]:
        name = (row[0] if row else "").strip()
        if name in {"NW", "NW Change", "NW Change %", "USD/EUR"}:
            break
        if len(row) < 7:
            continue
        broker = row[1].strip() if len(row) > 1 else ""
        isin = row[2].strip().upper() if len(row) > 2 else ""
        ticker = row[3].strip() if len(row) > 3 else ""
        if not name or not broker:
            continue
        values = {}
        for idx, dt in date_cols:
            if idx < len(row):
                parsed = csv_number(row[idx])
                if parsed is not None:
                    values[dt] = parsed
        if values:
            data_rows.append(
                {
                    "asset": name,
                    "broker": broker,
                    "isin": isin,
                    "ticker": ticker,
                    "quantity": csv_number(row[4]) or ZERO,
                    "cost_price": csv_number(row[5]) or ZERO,
                    "currency": (row[6].strip() if len(row) > 6 else ""),
                    "values": values,
                }
            )

    totals_by_date: dict[date, Decimal] = {}
    counts_by_date: dict[date, int] = {}
    for _, dt in date_cols:
        values = [row["values"].get(dt, ZERO) for row in data_rows]
        total = sum(values, ZERO)
        count = sum(1 for value in values if value > ZERO)
        if total > ZERO:
            totals_by_date[dt] = total
            counts_by_date[dt] = count

    if not totals_by_date:
        raise ValueError(f"No portfolio values found in {path.name}.")
    max_count = max(counts_by_date.values())
    min_complete_count = max(1, math.ceil(max_count * 0.8))
    complete_totals_by_date = {
        dt: value for dt, value in totals_by_date.items() if counts_by_date.get(dt, 0) >= min_complete_count
    }
    latest_date = max(complete_totals_by_date)
    current_total = totals_by_date[latest_date]
    first_date = min(complete_totals_by_date)
    first_total = totals_by_date[first_date]
    profit = current_total - first_total
    return_pct = (profit / first_total * Decimal("100")) if first_total > ZERO else ZERO

    positions = []
    for row in data_rows:
        value = row["values"].get(latest_date, ZERO)
        if value <= ZERO:
            continue
        cost_basis = row["quantity"] * row["cost_price"] if row["quantity"] and row["cost_price"] else ZERO
        pl = value - cost_basis if cost_basis > ZERO else ZERO
        positions.append(
            {
                "asset": row["asset"],
                "broker": row["broker"],
                "isin": row["isin"],
                "symbol": row["ticker"],
                "quantity": decimal_to_float(row["quantity"]),
                "cost_price": decimal_to_float(row["cost_price"]) if row["cost_price"] else None,
                "price": None,
                "price_currency": row["currency"],
                "market_value_eur": money(value),
                "cost_basis_eur": money(cost_basis),
                "is_open": True,
                "display_pl_eur": money(pl) if cost_basis > ZERO else None,
                "display_pl_pct": float((pl / cost_basis * Decimal("100")).quantize(Decimal("0.01"))) if cost_basis > ZERO else None,
                "pricing_status": "snapshot",
            }
        )

    valuation_series = []
    for dt in sorted(complete_totals_by_date):
        value = totals_by_date[dt]
        point_profit = value - first_total
        point_return = (point_profit / first_total * Decimal("100")) if first_total > ZERO else ZERO
        valuation_series.append(
            {
                "date": dt.isoformat(),
                "market_value": money(value),
                "net_contributions": money(first_total),
                "profit": money(point_profit),
                "return_pct": float(point_return.quantize(Decimal("0.01"))),
                "priced_positions": len(positions),
                "unpriced_positions": 0,
            }
        )

    return {
        "path": path,
        "person_name": FAMILY_PORTFOLIOS[person]["name"],
        "latest_date": latest_date,
        "first_date": first_date,
        "positions": sorted(positions, key=lambda item: item["market_value_eur"], reverse=True),
        "valuation_series": valuation_series,
        "totals": {
            "market_value": money(current_total),
            "return_pct": float(return_pct.quantize(Decimal("0.01"))),
            "open_cost_basis": None,
            "unrealized_pl": None,
            "realized_pl": None,
            "net_contributions": None,
            "historical_profit": money(profit),
            "priced_assets": len(positions),
            "unpriced_assets": 0,
        },
    }


def empty_money_table() -> dict[str, Any]:
    return {
        "rows": [],
        "total_eur": 0.0,
        "tax_eur": 0.0,
        "count": 0,
        "by_asset": [],
        "by_broker": [],
    }


def empty_contributions() -> dict[str, Any]:
    return {
        "total_buys_eur": 0.0,
        "total_sells_eur": 0.0,
        "net_eur": 0.0,
        "by_broker": [],
        "by_date": [],
    }


def normalize_berkshire_mode(value: str | None) -> str:
    return "lookthrough" if value == "lookthrough" else "stock"


def normalize_proxy_mode(value: str | None) -> str:
    return "off" if value == "off" else "on"


def configured_trade(adjustment: Any, history_start: date) -> Trade:
    event_date = history_start if adjustment.use_history_start else adjustment.date
    if event_date is None:
        raise ValueError(f"Configured trade for {adjustment.asset} has no date.")
    total = adjustment.total if adjustment.total is not None else adjustment.price * adjustment.quantity
    quantity_diff = adjustment.quantity if adjustment.action.upper() == "BUY" else -adjustment.quantity
    return Trade(
        asset=adjustment.asset,
        isin=adjustment.isin,
        broker=adjustment.broker,
        action=adjustment.action.upper(),
        currency_hint=adjustment.currency,
        cash_currency=adjustment.currency,
        date=event_date,
        price=adjustment.price,
        quantity=adjustment.quantity,
        quantity_diff=quantity_diff,
        total_spend=total,
        fees=adjustment.fees,
        tax=adjustment.tax,
        grand_total=total,
        grand_total_present=True,
        source=adjustment.source,
    )


def family_dashboard_payload(
    person: str,
    refresh: bool = False,
    berkshire_mode: str = "stock",
    proxy_mode: str = "on",
    broker: str = "all",
    live_only: str = "off",
) -> dict[str, Any]:
    profile = SETTINGS.portfolios.get(person.lower())
    if profile is None:
        raise KeyError(f"Unknown portfolio: {person}")
    proxy_mode = normalize_proxy_mode(proxy_mode)
    broker = (broker or "all").strip().lower()
    snapshot = read_family_snapshot(person)
    mappings = read_mappings()

    # Filter snapshot positions by live_only
    if live_only == "on":
        filtered_positions = []
        for pos in snapshot["positions"]:
            symbol = pos["isin"] or pos["symbol"]
            mapping = mapping_for(pos["asset"], symbol, mappings)
            direct_symbol = yahoo_symbol_from_mapping(mapping.get("ticker", ""), mapping.get("exchange", ""))
            if not direct_symbol and symbol:
                direct_symbol = resolve_isin(symbol).get("symbol", "")
            is_crypto = pos.get("broker", "").lower() == "crypto wallet"
            if direct_symbol or is_crypto:
                filtered_positions.append(pos)
        snapshot = {
            **snapshot,
            "positions": filtered_positions
        }
    first_date = profile.history_start or snapshot["first_date"]

    tr_file = latest_family_trade_republic_export(person)
    has_tr = tr_file is not None

    # Get all brokers first (unfiltered)
    snap_brokers = set()
    for pos in snapshot["positions"]:
        b = pos.get("broker")
        if b:
            snap_brokers.add(b)
    if has_tr:
        snap_brokers.add("Trade Republic")
    all_brokers = sorted(list(snap_brokers))

    # Filter snapshot positions by broker at the start
    if broker != "all":
        snapshot = {
            **snapshot,
            "positions": [pos for pos in snapshot["positions"] if str(pos.get("broker", "")).strip().lower() == broker]
        }

    fake_trades = []
    for pos in snapshot["positions"]:
        if has_tr and str(pos.get("broker", "")).strip().lower() == "trade republic":
            continue

        quantity = Decimal(str(pos["quantity"]))
        cost_basis = Decimal(str(pos["cost_basis_eur"]))
        
        configured_quantity = profile.position_quantity_overrides.get(pos["asset"])
        if configured_quantity is not None:
            quantity = configured_quantity
            cost_basis = quantity * Decimal(str(pos["cost_price"]))
        
        if quantity <= ZERO and pos.get("market_value_eur") is not None:
            snapshot_val = Decimal(str(pos["market_value_eur"]))
            symbol = pos["isin"] or pos["symbol"]
            mapping = mapping_for(pos["asset"], symbol, mappings)
            direct_symbol = yahoo_symbol_from_mapping(mapping.get("ticker", ""), mapping.get("exchange", ""))
            
            if not direct_symbol and symbol:
                direct_symbol = resolve_isin(symbol).get("symbol", "")
            
            computed_quantity = None
            if direct_symbol:
                from datetime import timedelta
                # Use latest_date to find true quantity based on latest snapshot value
                latest_date = snapshot["latest_date"]
                
                # Fetch all history from first_date up to latest_date to find both start and latest prices
                history = fetch_history(direct_symbol, first_date, latest_date + timedelta(days=5))
                prices = history.get("prices", {})
                
                latest_price = previous_price(prices, latest_date)
                
                if latest_price:
                    computed_quantity = snapshot_val / Decimal(str(latest_price))
                    
                    # Find earliest available price on or after first_date
                    sorted_dates = sorted(prices.keys())
                    start_price = None
                    for d in sorted_dates:
                        if d >= first_date.isoformat():
                            start_price = prices[d]
                            break
                            
                    if start_price:
                        # Normalize cost basis to start date (or IPO date) to track true growth
                        cost_basis = computed_quantity * Decimal(str(start_price))
                    else:
                        cost_basis = snapshot_val
            
            if computed_quantity:
                quantity = computed_quantity
            else:
                quantity = Decimal("1")
                cost_basis = snapshot_val
            
        if quantity > ZERO:
            price = cost_basis / quantity
            fake_trades.append(
                Trade(
                    asset=pos["asset"],
                    isin=pos["isin"] or pos["symbol"],
                    broker=pos["broker"],
                    action="BUY",
                    currency_hint=pos.get("price_currency") or "EUR",
                    cash_currency="EUR",
                    date=first_date,
                    price=price,
                    quantity=quantity,
                    quantity_diff=quantity,
                    total_spend=cost_basis,
                    fees=ZERO,
                    tax=ZERO,
                    grand_total=cost_basis,
                    grand_total_present=True,
                    source="snapshot",
                )
            )

    if has_tr and (broker == "all" or broker == "trade republic"):
        fake_trades.extend(read_trade_republic_trades(tr_file))

    fake_trades.extend(configured_trade(adjustment, first_date) for adjustment in profile.extra_trades)

    if broker != "all":
        fake_trades = [t for t in fake_trades if t.broker.lower() == broker]

    summary = summarize_trades(fake_trades)
    
    # Re-inject aggregate snapshot market values so enrich_positions fallback works correctly
    snapshot_values = {}
    for pos in snapshot["positions"]:
        val = pos.get("market_value_eur")
        if val is not None:
            snapshot_values[pos["asset"]] = snapshot_values.get(pos["asset"], ZERO) + Decimal(str(val))
            
    for pos in summary["positions"]:
        if pos["asset"] in snapshot_values:
            pos["market_value_eur"] = float(snapshot_values[pos["asset"]])

    priced = enrich_positions(summary["positions"], mappings, refresh=refresh)
    distribution = calculate_distribution(
        priced["positions"],
        read_exposures(berkshire_mode=berkshire_mode, proxy_mode=proxy_mode),
        berkshire_mode=berkshire_mode,
        proxy_mode=proxy_mode,
    )
    valuation = calculate_valuation_series(fake_trades, mappings, refresh=refresh, person=person, broker=broker)
    
    trade_assets = {trade.asset for trade in fake_trades}
    mapped_assets = set(mappings)
    assets_without_isin = {
        position["asset"]
        for position in summary["positions"]
        if position["is_open"] and not position.get("isin") and not mapping_for(position["asset"], "", mappings).get("isin")
    }

    # Load dividends and cash interests to compute final total returns
    dividends = read_portfolio_dividends(person)
    interests = read_cash_interests(person)
    if broker != "all":
        dividends = [d for d in dividends if d.broker.lower() == broker]
        interests = [i for i in interests if i.get("broker", "").lower() == broker]
    accumulated_dividends = sum((d.amount_eur for d in dividends), ZERO)
    accumulated_interest = sum((Decimal(str(i["net_eur"])) for i in interests), ZERO)
    total_market_value = Decimal(str(priced["market_value"])) + accumulated_dividends + accumulated_interest

    totals = {
        **summary["totals"],
        "market_value": priced["market_value"],
        "total_market_value": float(total_market_value.quantize(Decimal("0.01"))),
        "unrealized_pl": priced["unrealized_pl"],
        "estimated_total_value": money(Decimal(str(priced["market_value"]))),
        "priced_assets": priced["priced_assets"],
        "unpriced_assets": priced["unpriced_assets"],
    }
    if valuation["series"]:
        totals["return_pct"] = valuation["series"][-1]["return_pct"]
        totals["total_return_pct"] = valuation["series"][-1]["total_return_pct"]
        totals["historical_profit"] = valuation["series"][-1]["profit"]
        totals["historical_total_profit"] = valuation["series"][-1]["total_profit"]
        totals["total_market_value"] = valuation["series"][-1]["total_market_value"]
        totals["total_net_contributions"] = valuation["series"][-1]["total_net_contributions"]
    totals["variations"] = valuation.get("variations", {})

    f_events = trade_friction_events(fake_trades)
    f_events.extend(
        FrictionEvent(
            broker=adjustment.broker,
            event_type=adjustment.event_type,
            date=adjustment.date,
            amount_eur=adjustment.amount_eur,
            description=adjustment.description,
        )
        for adjustment in profile.extra_frictions
    )
    if has_tr and (broker == "all" or broker == "trade republic"):
        f_events.extend(read_trade_republic_tax_events(tr_file))

    if has_tr or profile.extra_frictions:
        frictions_payload = summarize_frictions(f_events, priced["market_value"])
    else:
        frictions_payload = empty_frictions(
            "snapshot_unavailable",
            "Taxes, broker costs, and net liquidation are not available from monthly snapshot CSV files.",
        )

    tax_losses = [
        {
            "year": item.year,
            "amount_eur": money(item.amount_eur),
            "expires_year": item.expires_year,
            "broker": item.broker,
        }
        for item in profile.tax_losses
    ]

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "person": person,
        "person_name": snapshot["person_name"],
        "berkshire_mode": berkshire_mode,
        "proxy_mode": proxy_mode,
        "trade_file": configured_path_label(snapshot["path"]),
        "trade_source": f"{snapshot['person_name']} CSV snapshot",
        "mapping_file": configured_path_label(MAPPINGS_CSV),
        "trade_count": len(fake_trades),
        "asset_count": len(trade_assets),
        "date_range": {
            "start": min(trade.date for trade in fake_trades).isoformat() if fake_trades else None,
            "end": valuation["series"][-1]["date"] if valuation["series"] else snapshot["latest_date"].isoformat(),
        },
        "totals": totals,
        "series": summary["series"],
        "valuation_series": valuation["series"],
        "valuation_status": {
            "status": valuation["status"],
            "symbols": valuation.get("symbols", []),
        },
        "positions": priced["positions"],
        "distribution": distribution,
        "dividends": summarize_dividends(dividends) if dividends else empty_money_table(),
        "cash_interests": summarize_cash_interests(read_cash_interests(person)),
        "todo_items": profile.todo_items,
        "expenses": empty_expenses("Expense classification is currently available for the primary portfolio only."),
        "net_contributions": summarize_net_contributions(fake_trades),
        "frictions": frictions_payload,
        "tax_losses": tax_losses,
        "mapping_status": {
            "missing_in_mapping": sorted(assets_without_isin),
            "extra_in_mapping": sorted(mapped_assets - trade_assets),
            "filled_isins": sum(1 for value in mappings.values() if value.get("isin")),
            "total_rows": len(mappings),
        },
        "brokers": all_brokers,
        "stats": calculate_portfolio_statistics(
            fake_trades,
            mappings,
            person=person,
            broker=broker,
            history_context=valuation.get("_history_context", {}),
        ),
    }
    payload["news_symbols"] = news_symbols_from_payload(payload)
    return payload


def read_mappings() -> dict[str, dict[str, str]]:
    mappings: dict[str, dict[str, str]] = {}
    if not MAPPINGS_CSV.exists():
        return mappings

    with MAPPINGS_CSV.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            asset = (row.get("asset_name") or "").strip()
            isin = (row.get("isin") or "").strip().upper()
            if asset:
                mappings[asset] = {
                    "isin": isin,
                    "ticker": (row.get("Ticker") or row.get("ticker") or "").strip(),
                    "exchange": (row.get("Borsa") or row.get("exchange") or "").strip(),
                }
    return mappings


def read_crypto_wallet_positions(person: str = PRIMARY_PORTFOLIO_ID) -> list[dict[str, Any]]:
    if not CRYPTO_WALLET_POSITIONS_CSV.exists():
        return []
    positions: list[dict[str, Any]] = []
    with CRYPTO_WALLET_POSITIONS_CSV.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            if (row.get("person") or PRIMARY_PORTFOLIO_ID).strip().lower() != person.lower():
                continue
            quantity = parse_decimal(row.get("quantity"))
            if quantity <= ZERO:
                continue
            market_value = parse_decimal(row.get("market_value_eur"))
            cost_basis = parse_decimal(row.get("cost_basis_eur"))
            position = {
                "asset": (row.get("asset") or row.get("symbol") or "").strip(),
                "isin": "",
                "quantity": float(quantity),
                "cost_basis_eur": float(cost_basis),
                "is_open": True,
                "realized_pl_eur": 0.0,
                "realized_pl_pct": None,
                "broker": (row.get("broker") or "Crypto Wallet").strip(),
                "symbol": (row.get("symbol") or "").strip(),
                "asset_class": (row.get("asset_class") or "Crypto").strip() or "Crypto",
                "sector": (row.get("sector") or "Crypto").strip() or "Crypto",
                "geo": (row.get("geo") or "Global").strip() or "Global",
                "wallet_label": (row.get("wallet_label") or "").strip(),
                "wallet_address": (row.get("wallet_address") or "").strip(),
                "chain": (row.get("chain") or "").strip(),
                "source": (row.get("source") or "crypto_wallet").strip(),
            }
            if market_value > ZERO:
                position["market_value_eur"] = float(market_value)
            positions.append(position)
    return positions


def crypto_wallet_transaction_start_date() -> date:
    path = CRYPTO_WALLET_TRANSACTIONS_CSV
    if not path.exists():
        return date.today() - timedelta(days=30)
    dates: list[date] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            raw = (row.get("created_at") or "").strip()
            if not raw:
                continue
            try:
                dates.append(datetime.fromisoformat(raw.replace("Z", "+00:00")).date())
            except ValueError:
                continue
    return min(dates) if dates else date.today() - timedelta(days=30)


def crypto_wallet_valuation(wallet_positions: list[dict[str, Any]]) -> dict[str, Any]:
    if not wallet_positions:
        return {"series": [], "status": "empty", "symbols": [], "variations": {}}
    events = read_crypto_events()
    today = date.today()
    if not events:
        market_value = sum((Decimal(str(position.get("market_value_eur") or 0)) for position in wallet_positions), ZERO)
        cost_basis = sum((Decimal(str(position.get("cost_basis_eur") or 0)) for position in wallet_positions), ZERO)
        net_contributions = cost_basis if cost_basis > ZERO else market_value
        profit = market_value - net_contributions
        return_pct = profit / net_contributions * Decimal("100") if net_contributions > ZERO else ZERO
        return {
            "series": [
                {
                    "date": today.isoformat(),
                    "market_value": money(market_value),
                    "total_market_value": money(market_value),
                    "net_contributions": money(net_contributions),
                    "total_net_contributions": money(net_contributions),
                    "profit": money(profit),
                    "total_profit": money(profit),
                    "return_pct": float(return_pct.quantize(Decimal("0.01"))),
                    "total_return_pct": float(return_pct.quantize(Decimal("0.01"))),
                    "priced_positions": len(wallet_positions),
                    "unpriced_positions": 0,
                    "msci_return_pct": 0.0,
                    "xeon_return_pct": 0.0,
                    "inflation_return_pct": 0.0,
                }
            ],
            "status": "crypto_wallet_snapshot",
            "symbols": sorted({str(position.get("symbol") or "") for position in wallet_positions if position.get("symbol")}),
            "variations": {"1d": {"amount": 0.0, "pct": 0.0, "past_date": today.isoformat()}, "1w": {"amount": 0.0, "pct": 0.0, "past_date": today.isoformat()}, "1m": {"amount": 0.0, "pct": 0.0, "past_date": today.isoformat()}},
        }

    start = events[0]["date"]
    recent_dates = {today - timedelta(days=i) for i in range(35) if today - timedelta(days=i) >= start}
    dates = sorted(month_end_dates(start, today) | {event["date"] for event in events} | recent_dates)
    histories = {
        asset: fetch_crypto_eur_history(asset, start, today, refresh=False)
        for asset in {"BTC", "ETH", "TON", "USDC"}
        if any(event["asset"] == asset for event in events)
    }
    latest_quantities = {
        str(position.get("asset") or "").upper(): Decimal(str(position.get("quantity") or 0))
        for position in wallet_positions
    }
    latest_values = {
        str(position.get("asset") or "").upper(): Decimal(str(position.get("market_value_eur") or 0))
        for position in wallet_positions
    }
    latest_cost_basis = sum((Decimal(str(position.get("cost_basis_eur") or 0)) for position in wallet_positions), ZERO)

    # Fetch MSCI World prices for comparison
    msci_prices = {}
    for sym in ["SWDA.MI", "EUNL.DE", "URTH"]:
        h = fetch_history(sym, start, today, refresh=False)
        if h and h.get("status") == "priced" and h.get("prices"):
            msci_prices = h["prices"]
            break

    p0 = None
    if msci_prices:
        p0 = previous_price(msci_prices, start)
        if p0 is None:
            sorted_msci_dates = sorted(msci_prices.keys())
            if sorted_msci_dates:
                p0 = msci_prices[sorted_msci_dates[0]]

    # Fetch XEON prices for comparison
    xeon_prices = {}
    h_xeon = fetch_history("XEON.DE", start, today, refresh=False)
    if h_xeon and h_xeon.get("status") == "priced" and h_xeon.get("prices"):
        xeon_prices = h_xeon["prices"]

    xeon_p0 = None
    if xeon_prices:
        xeon_p0 = previous_price(xeon_prices, start)
        if xeon_p0 is None:
            sorted_xeon_dates = sorted(xeon_prices.keys())
            if sorted_xeon_dates:
                xeon_p0 = xeon_prices[sorted_xeon_dates[0]]

    # Load CPI data for inflation comparison
    cpi_data = fetch_eurostat_cpi()
    
    def get_cpi_value(d: date) -> float | None:
        if not cpi_data:
            return None
        label = f"{d.year:04d}-{d.month:02d}"
        if label in cpi_data:
            return cpi_data[label]
        sorted_labels = sorted(cpi_data.keys())
        best_val = None
        for l in sorted_labels:
            if l <= label:
                best_val = cpi_data[l]
            else:
                break
        if best_val is not None:
            return best_val
        return cpi_data[sorted_labels[-1]] if sorted_labels else None

    start_cpi = get_cpi_value(start)

    holdings: dict[str, Decimal] = {}
    cost_basis_by_asset: dict[str, Decimal] = {}
    invested = ZERO
    event_index = 0
    series = []
    for point_date in dates:
        while event_index < len(events) and events[event_index]["date"] <= point_date:
            event = events[event_index]
            asset = event["asset"]
            quantity = event["quantity"]
            cash_eur = event["cash_eur"]
            holdings[asset] = holdings.get(asset, ZERO) + quantity
            if cash_eur > ZERO and quantity > ZERO:
                invested += cash_eur
                cost_basis_by_asset[asset] = cost_basis_by_asset.get(asset, ZERO) + cash_eur
            elif quantity < ZERO:
                previous_quantity = holdings.get(asset, ZERO) - quantity
                if previous_quantity > ZERO:
                    previous_cost = cost_basis_by_asset.get(asset, ZERO)
                    removed_cost = min(previous_cost, previous_cost * abs(quantity) / previous_quantity)
                    cost_basis_by_asset[asset] = max(ZERO, previous_cost - removed_cost)
            event_index += 1

        if point_date == today:
            for asset, quantity in latest_quantities.items():
                holdings[asset] = quantity

        market_value = ZERO
        priced = 0
        unpriced = 0
        for asset, quantity in holdings.items():
            if quantity <= ZERO:
                continue
            if point_date == today and asset in latest_values and latest_values[asset] > ZERO:
                market_value += latest_values[asset]
                priced += 1
                continue
            price = previous_price((histories.get(asset) or {}).get("prices", {}), point_date)
            if price is None:
                unpriced += 1
                market_value += cost_basis_by_asset.get(asset, ZERO)
                continue
            market_value += quantity * Decimal(str(price))
            priced += 1

        net_contributions = sum(cost_basis_by_asset.values(), ZERO)
        if point_date == today and latest_cost_basis > ZERO:
            net_contributions = latest_cost_basis
        profit = market_value - net_contributions
        return_pct = profit / net_contributions * Decimal("100") if net_contributions > ZERO else ZERO
        msci_return = 0.0
        if p0 and p0 > 0:
            price_t = previous_price(msci_prices, point_date)
            if price_t is not None:
                msci_return = float((Decimal(str(price_t)) - Decimal(str(p0))) / Decimal(str(p0)) * 100)

        xeon_return = 0.0
        if xeon_p0 and xeon_p0 > 0:
            price_t = previous_price(xeon_prices, point_date)
            if price_t is not None:
                xeon_return = float((Decimal(str(price_t)) - Decimal(str(xeon_p0))) / Decimal(str(xeon_p0)) * 100)

        inflation_return = 0.0
        if start_cpi and start_cpi > 0:
            cpi_t = get_cpi_value(point_date)
            if cpi_t:
                inflation_return = float((Decimal(str(cpi_t)) - Decimal(str(start_cpi))) / Decimal(str(start_cpi)) * 100)
        else:
            days_since_start = (point_date - start).days
            inflation_return = float(((Decimal("1.02") ** (Decimal(str(days_since_start)) / Decimal("365.25"))) - 1) * 100)

        series.append(
            {
                "date": point_date.isoformat(),
                "market_value": money(market_value),
                "total_market_value": money(market_value),
                "net_contributions": money(net_contributions),
                "total_net_contributions": money(net_contributions),
                "profit": money(profit),
                "total_profit": money(profit),
                "return_pct": float(return_pct.quantize(Decimal("0.01"))),
                "total_return_pct": float(return_pct.quantize(Decimal("0.01"))),
                "priced_positions": priced,
                "unpriced_positions": unpriced,
                "msci_return_pct": round(msci_return, 2),
                "xeon_return_pct": round(xeon_return, 2),
                "inflation_return_pct": round(inflation_return, 2),
            }
        )

    return {
        "series": series,
        "status": "crypto_wallet_reconstructed",
        "symbols": sorted({str(position.get("symbol") or "") for position in wallet_positions if position.get("symbol")}),
        "variations": calculate_variations(series),
    }


def crypto_wallet_contributions(wallet_positions: list[dict[str, Any]]) -> dict[str, Any]:
    net = sum((Decimal(str(position.get("cost_basis_eur") or 0)) for position in wallet_positions), ZERO)
    if net <= ZERO:
        net = sum((Decimal(str(position.get("market_value_eur") or 0)) for position in wallet_positions), ZERO)
    return {
        "total_buys_eur": money(net),
        "total_sells_eur": 0.0,
        "net_eur": money(net),
        "by_broker": [
            {
                "broker": "Crypto Wallet",
                "buys_eur": money(net),
                "sells_eur": 0.0,
                "net_eur": money(net),
                "share_pct": 100.0 if net > ZERO else None,
            }
        ],
        "by_date": [
            {
                "date": crypto_wallet_transaction_start_date().isoformat(),
                "buys_eur": money(net),
                "sells_eur": 0.0,
                "net_eur": money(net),
            }
        ]
        if net > ZERO
        else [],
    }


def parse_binance_time(value: str) -> date:
    raw = (value or "").strip()
    for fmt in ("%y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return date.today()


def latest_binance_transaction_history() -> Path | None:
    files = sorted(Path.home().joinpath("Downloads").glob("Binance-Transaction-History-*.csv"))
    return files[-1] if files else None


def read_crypto_events() -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    if CRYPTO_WALLET_TRANSACTIONS_CSV.exists():
        with CRYPTO_WALLET_TRANSACTIONS_CSV.open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                if (row.get("person") or PRIMARY_PORTFOLIO_ID).strip().lower() != PRIMARY_PORTFOLIO_ID:
                    continue
                asset = (row.get("asset") or "").strip().upper()
                quantity = parse_decimal(row.get("quantity"))
                native = parse_decimal(row.get("native_amount"))
                if not asset or quantity == ZERO:
                    continue
                try:
                    event_date = datetime.fromisoformat((row.get("created_at") or "").replace("Z", "+00:00")).date()
                except ValueError:
                    continue
                events.append(
                    {
                        "date": event_date,
                        "asset": asset,
                        "quantity": quantity,
                        "cash_eur": native,
                        "source": "coinbase_account",
                    }
                )

    binance_file = latest_binance_transaction_history()
    if binance_file:
        rows: list[dict[str, str]] = []
        with binance_file.open(newline="", encoding="utf-8-sig") as handle:
            rows = [{key: (value or "").strip() for key, value in row.items()} for row in csv.DictReader(handle)]
        used_targets: set[int] = set()
        for index, row in enumerate(rows):
            if row.get("Operation") != "Binance Convert" or row.get("Coin") != "EUR":
                continue
            eur_spend = abs(parse_decimal(row.get("Change")))
            if eur_spend <= ZERO:
                continue
            target_index = None
            for candidate_index in (index - 1, index + 1, index - 2, index + 2):
                if candidate_index < 0 or candidate_index >= len(rows) or candidate_index in used_targets:
                    continue
                candidate = rows[candidate_index]
                coin = (candidate.get("Coin") or "").strip().upper()
                if candidate.get("Operation") == "Binance Convert" and coin and coin != "EUR" and parse_decimal(candidate.get("Change")) > ZERO:
                    target_index = candidate_index
                    break
            if target_index is None:
                continue
            used_targets.add(target_index)
            target = rows[target_index]
            events.append(
                {
                    "date": parse_binance_time(target.get("Time") or row.get("Time") or ""),
                    "asset": (target.get("Coin") or "").strip().upper(),
                    "quantity": parse_decimal(target.get("Change")),
                    "cash_eur": eur_spend,
                    "source": "binance_convert",
                }
            )
    return sorted(events, key=lambda item: item["date"])


def calculate_variations(series: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    if not series:
        return {
            "1d": {"amount": 0.0, "pct": 0.0, "msci_pct": None, "vs_msci_pct": None, "past_date": None},
            "1w": {"amount": 0.0, "pct": 0.0, "msci_pct": None, "vs_msci_pct": None, "past_date": None},
            "1m": {"amount": 0.0, "pct": 0.0, "msci_pct": None, "vs_msci_pct": None, "past_date": None},
        }
    latest = series[-1]
    latest_date = date.fromisoformat(latest["date"])

    def find_entry_for_date(target: date):
        best_entry = None
        for entry in series:
            entry_date = date.fromisoformat(entry["date"])
            if entry_date <= target:
                best_entry = entry
            else:
                break
        return best_entry

    variations = {}
    for key, target_date in {
        "1d": latest_date - timedelta(days=1),
        "1w": latest_date - timedelta(days=7),
        "1m": latest_date - timedelta(days=30),
    }.items():
        past = find_entry_for_date(target_date)
        if past and past["date"] != latest["date"]:
            amount = latest["profit"] - past["profit"]
            past_val = past["market_value"]
            pct_val = (amount / past_val * 100) if past_val > 0 else 0.0
            msci_pct = benchmark_delta(latest, past, "msci")
            variations[key] = {
                "amount": round(amount, 2),
                "pct": round(pct_val, 2),
                "msci_pct": round(msci_pct, 2) if msci_pct is not None else None,
                "vs_msci_pct": round(float(pct_val) - msci_pct, 2) if msci_pct is not None else None,
                "past_date": past["date"],
            }
        else:
            variations[key] = {"amount": 0.0, "pct": 0.0, "msci_pct": None, "vs_msci_pct": None, "past_date": latest["date"]}
    return variations


def exposure_key(asset_name: str, isin: str) -> str:
    normalized_isin = (isin or "").strip().upper()
    if normalized_isin:
        return f"isin:{normalized_isin}"
    return f"asset:{(asset_name or '').strip().casefold()}"


def exposure_row_item(row: dict[str, Any], default_asset_name: str = "", default_isin: str = "") -> dict[str, Any] | None:
    asset_name = (row.get("asset_name") or default_asset_name).strip()
    isin = (row.get("isin") or default_isin).strip().upper()
    if not asset_name and not isin:
        return None
    weight = parse_decimal(row.get("weight_pct"))
    if weight <= ZERO:
        return None
    return {
        "asset_name": asset_name,
        "isin": isin,
        "holding_name": (row.get("holding_name") or asset_name or isin).strip(),
        "holding_ticker": (row.get("holding_ticker") or "").strip(),
        "weight_pct": weight,
        "sector": (row.get("sector") or "Unclassified").strip() or "Unclassified",
        "geo": (row.get("geo") or "Unclassified").strip() or "Unclassified",
        "asset_class": (row.get("asset_class") or "Equity").strip() or "Equity",
    }


def load_berkshire_lookthrough_rows() -> list[dict[str, Any]]:
    if not BERKSHIRE_HOLDINGS_CSV.exists():
        return []
    rows: list[dict[str, Any]] = []
    with BERKSHIRE_HOLDINGS_CSV.open(newline="", encoding="utf-8-sig") as handle:
        for raw in csv.DictReader(handle):
            item = exposure_row_item(raw, "Berkshire Hathaway (B)", BERKSHIRE_ISIN)
            if item:
                rows.append(item)
    return rows


def read_berkshire_metadata() -> dict[str, Any]:
    if not BERKSHIRE_HOLDINGS_CSV.exists():
        return {}
    with BERKSHIRE_HOLDINGS_CSV.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return {}
    weight_sum = sum((parse_decimal(row.get("weight_pct")) for row in rows), ZERO)
    first = rows[0]
    return {
        "issuer": "Berkshire Hathaway",
        "status": "official_sec_13f",
        "fetched_at": first.get("filing_date") or "",
        "holdings_url": first.get("source_url") or "",
        "rows": len(rows),
        "weight_sum": str(weight_sum.quantize(Decimal("0.0001")).normalize()),
        "message": f"SEC 13F-HR public equity holdings, report date {first.get('report_date') or 'unknown'}.",
    }


def load_proxy_exposure_rows() -> dict[str, list[dict[str, Any]]]:
    if not PROXY_EXPOSURES_CSV.exists():
        return {}
    rows_by_isin: dict[str, list[dict[str, Any]]] = {}
    with PROXY_EXPOSURES_CSV.open(newline="", encoding="utf-8-sig") as handle:
        for raw in csv.DictReader(handle):
            item = exposure_row_item(raw)
            if not item or item["isin"] not in PROXY_ISSUERS:
                continue
            rows_by_isin.setdefault(item["isin"], []).append(item)
            
    # Dynamically copy LU1681045370 (Amundi EM proxy) rows to IE00BKM4GZ66 (Core MSCI EM IMI)
    if "LU1681045370" in rows_by_isin and "IE00BKM4GZ66" in PROXY_ISSUERS:
        rows_by_isin["IE00BKM4GZ66"] = [
            {**row, "asset_name": "Core MSCI EM IMI USD (Acc)", "isin": "IE00BKM4GZ66"}
            for row in rows_by_isin["LU1681045370"]
        ]
        
    # Dynamically copy NL0011683594 (VanEck proxy) rows to IE00BYZ2Y955 (MBB Dynamic International Value Opportunity LA EUR)
    value_isin = "IE00BYZ2Y955"
    value_name = "MBB Dynamic International Value Opportunity LA EUR"
    if "NL0011683594" in rows_by_isin and value_isin in PROXY_ISSUERS:
        rows_by_isin[value_isin] = [
            {**row, "asset_name": value_name, "isin": value_isin}
            for row in rows_by_isin["NL0011683594"]
        ]

    # Dynamically copy/construct rows using MSCI World (IE00B4L5Y983) and S&P 500 (IE00B5BMR087)
    world_isin = "IE00B4L5Y983"
    ms_isin = "IE00B2NLMV86"
    ms_name = "MBB Mediolanum Morgan Stanley Global Selection LHA EUR"
    difesa_isin = "IT0005285157"
    difesa_name = "Eurizon Profilo Flessibile Difesa II"
    flexible_eq_isin = "LU0497415702"
    flexible_eq_name = "Eurizon Flexible Equity Strategy R EUR"

    # Configured funds that reuse existing public exposure compositions.
    anima_isin = "IT0004896715"
    anima_name = "Anima Fondo Trading F"
    fidelity_america_isin = "LU0755218046"
    fidelity_name = "Fidelity America Y acc Eur"
    sp500_isin = "IE00B5BMR087"
    
    if EXPOSURES_CSV.exists() and (
        ms_isin in PROXY_ISSUERS or 
        difesa_isin in PROXY_ISSUERS or 
        flexible_eq_isin in PROXY_ISSUERS or 
        anima_isin in PROXY_ISSUERS or 
        fidelity_america_isin in PROXY_ISSUERS
    ):
        msci_rows = []
        sp500_rows = []
        with EXPOSURES_CSV.open(newline="", encoding="utf-8-sig") as handle:
            for raw in csv.DictReader(handle):
                item = exposure_row_item(raw)
                if item:
                    if item["isin"] == world_isin:
                        msci_rows.append(item)
                    elif item["isin"] == sp500_isin:
                        sp500_rows.append(item)
        
        # Populate Morgan Stanley Global Selection (100% MSCI World)
        if msci_rows and ms_isin in PROXY_ISSUERS:
            rows_by_isin[ms_isin] = [
                {**row, "asset_name": ms_name, "isin": ms_isin}
                for row in msci_rows
            ]

        # Anima Fondo Trading F: 60% MSCI World, 40% Euro Cash / Bonds
        if msci_rows and anima_isin in PROXY_ISSUERS:
            anima_rows = [
                {
                    **row,
                    "asset_name": anima_name,
                    "isin": anima_isin,
                    "weight_pct": row["weight_pct"] * Decimal("0.6")
                }
                for row in msci_rows
            ]
            equity_sum = sum(row["weight_pct"] for row in anima_rows)
            anima_rows.append({
                "asset_name": anima_name,
                "isin": anima_isin,
                "holding_name": "Euro Cash / Bonds",
                "holding_ticker": "",
                "weight_pct": Decimal("100") - equity_sum,
                "sector": "Cash / Money Market",
                "geo": "Eurozone",
                "asset_class": "Cash equivalent",
            })
            rows_by_isin[anima_isin] = anima_rows

        # Fidelity America: 100% S&P 500
        if sp500_rows and fidelity_america_isin in PROXY_ISSUERS:
            sp500_sum = sum(row["weight_pct"] for row in sp500_rows)
            fidelity_rows = []
            accumulated_weight = Decimal("0")
            for i, row in enumerate(sp500_rows):
                if i == len(sp500_rows) - 1:
                    weight = Decimal("100") - accumulated_weight
                else:
                    weight = (row["weight_pct"] * Decimal("100") / sp500_sum).quantize(Decimal("0.000001"))
                    accumulated_weight += weight
                fidelity_rows.append({
                    **row,
                    "asset_name": fidelity_name,
                    "isin": fidelity_america_isin,
                    "weight_pct": weight
                })
            rows_by_isin[fidelity_america_isin] = fidelity_rows
                    # Eurizon Profilo Flessibile Difesa II: 10% MSCI World, 60% Eurozone Gov Bonds, rest Cash
        if msci_rows and difesa_isin in PROXY_ISSUERS:
            difesa_rows = [
                {
                    **row,
                    "asset_name": difesa_name,
                    "isin": difesa_isin,
                    "weight_pct": row["weight_pct"] * Decimal("0.1")
                }
                for row in msci_rows
            ]
            equity_sum = sum(row["weight_pct"] for row in difesa_rows)
            difesa_rows.append({
                "asset_name": difesa_name,
                "isin": difesa_isin,
                "holding_name": "Eurozone Gov Bonds",
                "holding_ticker": "",
                "weight_pct": Decimal("60"),
                "sector": "Fixed Income",
                "geo": "Eurozone",
                "asset_class": "Fixed Income",
            })
            difesa_rows.append({
                "asset_name": difesa_name,
                "isin": difesa_isin,
                "holding_name": "Euro Cash / Deposits",
                "holding_ticker": "",
                "weight_pct": Decimal("40") - equity_sum,
                "sector": "Cash / Money Market",
                "geo": "Eurozone",
                "asset_class": "Cash equivalent",
            })
            rows_by_isin[difesa_isin] = difesa_rows
            
        # Eurizon Flexible Equity Strategy: 55% MSCI World, 30% Eurozone Gov Bonds, rest Cash
        if msci_rows and flexible_eq_isin in PROXY_ISSUERS:
            flex_rows = [
                {
                    **row,
                    "asset_name": flexible_eq_name,
                    "isin": flexible_eq_isin,
                    "weight_pct": row["weight_pct"] * Decimal("0.55")
                }
                for row in msci_rows
            ]
            equity_sum = sum(row["weight_pct"] for row in flex_rows)
            flex_rows.append({
                "asset_name": flexible_eq_name,
                "isin": flexible_eq_isin,
                "holding_name": "Eurozone Gov Bonds",
                "holding_ticker": "",
                "weight_pct": Decimal("30"),
                "sector": "Fixed Income",
                "geo": "Eurozone",
                "asset_class": "Fixed Income",
            })
            flex_rows.append({
                "asset_name": flexible_eq_name,
                "isin": flexible_eq_isin,
                "holding_name": "Euro Cash / Deposits",
                "holding_ticker": "",
                "weight_pct": Decimal("70") - equity_sum,
                "sector": "Cash / Money Market",
                "geo": "Eurozone",
                "asset_class": "Cash equivalent",
            })
            rows_by_isin[flexible_eq_isin] = flex_rows

    # Eurizon Obbligazioni Euro High Yield: 80% High Yield Corporate Bonds, 20% Gov Bonds/BOTs
    hy_isin = "IT0001280541"
    hy_name = "Eurizon Obbligazioni Euro High Yield"
    if hy_isin in PROXY_ISSUERS:
        rows_by_isin[hy_isin] = [
            {
                "asset_name": hy_name,
                "isin": hy_isin,
                "holding_name": "Euro Corporate Bonds - Financials",
                "holding_ticker": "",
                "weight_pct": Decimal("30"),
                "sector": "Financials",
                "geo": "Europe",
                "asset_class": "Fixed Income",
            },
            {
                "asset_name": hy_name,
                "isin": hy_isin,
                "holding_name": "Euro Corporate Bonds - Industrials",
                "holding_ticker": "",
                "weight_pct": Decimal("30"),
                "sector": "Industrials",
                "geo": "Europe",
                "asset_class": "Fixed Income",
            },
            {
                "asset_name": hy_name,
                "isin": hy_isin,
                "holding_name": "Euro Corporate Bonds - Utilities",
                "holding_ticker": "",
                "weight_pct": Decimal("20"),
                "sector": "Utilities",
                "geo": "Europe",
                "asset_class": "Fixed Income",
            },
            {
                "asset_name": hy_name,
                "isin": hy_isin,
                "holding_name": "Eurozone Gov Bonds / Short-term debt",
                "holding_ticker": "",
                "weight_pct": Decimal("20"),
                "sector": "Cash / Money Market",
                "geo": "Eurozone",
                "asset_class": "Cash equivalent",
            },
        ]

    # Eurizon Riserva 2 Anni Classe A: 70% Short-term Eurozone Gov Bonds, 30% Cash/Deposits
    riserva_isin = "IT0005104424"
    riserva_name = "Eurizon Riserva 2 Anni Classe A"
    if riserva_isin in PROXY_ISSUERS:
        rows_by_isin[riserva_isin] = [
            {
                "asset_name": riserva_name,
                "isin": riserva_isin,
                "holding_name": "Eurozone Short-term Government Bonds",
                "holding_ticker": "",
                "weight_pct": Decimal("70"),
                "sector": "Fixed Income",
                "geo": "Eurozone",
                "asset_class": "Fixed Income",
            },
            {
                "asset_name": riserva_name,
                "isin": riserva_isin,
                "holding_name": "Euro Cash / Deposits",
                "holding_ticker": "",
                "weight_pct": Decimal("30"),
                "sector": "Cash / Money Market",
                "geo": "Eurozone",
                "asset_class": "Cash equivalent",
            },
        ]

    # Dynamically construct mock PIR-compliant rows for IT0001019329 (SMFI - Mediolanum Flessibile Futuro Italia LA PIR Acc EUR)
    pir_isin = "IT0001019329"
    pir_name = "SMFI - Mediolanum Flessibile Futuro Italia LA PIR Acc EUR"
    if pir_isin in PROXY_ISSUERS:
        rows_by_isin[pir_isin] = [
            {
                "asset_name": pir_name,
                "isin": pir_isin,
                "holding_name": "Enel Spa",
                "holding_ticker": "ENEL.MI",
                "weight_pct": Decimal("15"),
                "sector": "Utilities",
                "geo": "Italy",
                "asset_class": "Equity",
            },
            {
                "asset_name": pir_name,
                "isin": pir_isin,
                "holding_name": "Intesa Sanpaolo Spa",
                "holding_ticker": "ISP.MI",
                "weight_pct": Decimal("15"),
                "sector": "Financials",
                "geo": "Italy",
                "asset_class": "Equity",
            },
            {
                "asset_name": pir_name,
                "isin": pir_isin,
                "holding_name": "UniCredit Spa",
                "holding_ticker": "UCG.MI",
                "weight_pct": Decimal("15"),
                "sector": "Financials",
                "geo": "Italy",
                "asset_class": "Equity",
            },
            {
                "asset_name": pir_name,
                "isin": pir_isin,
                "holding_name": "Ferrari N.V.",
                "holding_ticker": "RACE.MI",
                "weight_pct": Decimal("10"),
                "sector": "Consumer Discretionary",
                "geo": "Italy",
                "asset_class": "Equity",
            },
            {
                "asset_name": pir_name,
                "isin": pir_isin,
                "holding_name": "Stellantis N.V.",
                "holding_ticker": "STLAM.MI",
                "weight_pct": Decimal("10"),
                "sector": "Consumer Discretionary",
                "geo": "Italy",
                "asset_class": "Equity",
            },
            {
                "asset_name": pir_name,
                "isin": pir_isin,
                "holding_name": "Nexi S.p.A.",
                "holding_ticker": "NEXI.MI",
                "weight_pct": Decimal("5"),
                "sector": "Financials",
                "geo": "Italy",
                "asset_class": "Equity",
            },
            {
                "asset_name": pir_name,
                "isin": pir_isin,
                "holding_name": "Italian Gov Bonds",
                "holding_ticker": "",
                "weight_pct": Decimal("30"),
                "sector": "Cash / Money Market",
                "geo": "Italy",
                "asset_class": "Cash equivalent",
            },
        ]

    # JPM Europe Equity (I and C)
    jpm_eur_i_isin = "LU2146152231"
    jpm_eur_i_name = "JPM Europe Equity I acc EUR"
    jpm_eur_c_isin = "LU0129441100"
    jpm_eur_c_name = "JPM Europe Equity C acc EUR"
    jpm_europe_constituents = [
        {"holding_name": "ASML Holding NV", "holding_ticker": "ASML.AS", "weight_pct": Decimal("15"), "sector": "Information Technology", "geo": "Europe", "asset_class": "Equity"},
        {"holding_name": "Novo Nordisk A/S", "holding_ticker": "NOVO-B.CO", "weight_pct": Decimal("15"), "sector": "Health Care", "geo": "Europe", "asset_class": "Equity"},
        {"holding_name": "Nestle SA", "holding_ticker": "NESN.SW", "weight_pct": Decimal("15"), "sector": "Consumer Staples", "geo": "Europe", "asset_class": "Equity"},
        {"holding_name": "Roche Holding AG", "holding_ticker": "ROG.SW", "weight_pct": Decimal("10"), "sector": "Health Care", "geo": "Europe", "asset_class": "Equity"},
        {"holding_name": "Novartis AG", "holding_ticker": "NOVN.SW", "weight_pct": Decimal("10"), "sector": "Health Care", "geo": "Europe", "asset_class": "Equity"},
        {"holding_name": "LVMH Moet Hennessy Louis Vuitton SE", "holding_ticker": "MC.PA", "weight_pct": Decimal("10"), "sector": "Consumer Discretionary", "geo": "Europe", "asset_class": "Equity"},
        {"holding_name": "AstraZeneca PLC", "holding_ticker": "AZN.L", "weight_pct": Decimal("10"), "sector": "Health Care", "geo": "Europe", "asset_class": "Equity"},
        {"holding_name": "Shell PLC", "holding_ticker": "SHEL.L", "weight_pct": Decimal("10"), "sector": "Energy", "geo": "Europe", "asset_class": "Equity"},
        {"holding_name": "SAP SE", "holding_ticker": "SAP.DE", "weight_pct": Decimal("5"), "sector": "Information Technology", "geo": "Europe", "asset_class": "Equity"},
    ]
    if jpm_eur_i_isin in PROXY_ISSUERS:
        rows_by_isin[jpm_eur_i_isin] = [
            {**const, "asset_name": jpm_eur_i_name, "isin": jpm_eur_i_isin}
            for const in jpm_europe_constituents
        ]
    if jpm_eur_c_isin in PROXY_ISSUERS:
        rows_by_isin[jpm_eur_c_isin] = [
            {**const, "asset_name": jpm_eur_c_name, "isin": jpm_eur_c_isin}
            for const in jpm_europe_constituents
        ]

    # Franklin Biotechnology
    franklin_biotech_isin = "LU0109394709"
    franklin_biotech_name = "Franklin Biotechnology Discv A acc USD"
    if franklin_biotech_isin in PROXY_ISSUERS:
        rows_by_isin[franklin_biotech_isin] = [
            {"asset_name": franklin_biotech_name, "isin": franklin_biotech_isin, "holding_name": "Amgen Inc.", "holding_ticker": "AMGN", "weight_pct": Decimal("20"), "sector": "Health Care", "geo": "United States", "asset_class": "Equity"},
            {"asset_name": franklin_biotech_name, "isin": franklin_biotech_isin, "holding_name": "Gilead Sciences Inc.", "holding_ticker": "GILD", "weight_pct": Decimal("20"), "sector": "Health Care", "geo": "United States", "asset_class": "Equity"},
            {"asset_name": franklin_biotech_name, "isin": franklin_biotech_isin, "holding_name": "Regeneron Pharmaceuticals Inc.", "holding_ticker": "REGN", "weight_pct": Decimal("20"), "sector": "Health Care", "geo": "United States", "asset_class": "Equity"},
            {"asset_name": franklin_biotech_name, "isin": franklin_biotech_isin, "holding_name": "Vertex Pharmaceuticals Inc.", "holding_ticker": "VRTX", "weight_pct": Decimal("20"), "sector": "Health Care", "geo": "United States", "asset_class": "Equity"},
            {"asset_name": franklin_biotech_name, "isin": franklin_biotech_isin, "holding_name": "Moderna Inc.", "holding_ticker": "MRNA", "weight_pct": Decimal("20"), "sector": "Health Care", "geo": "United States", "asset_class": "Equity"},
        ]

    # Templeton Global Bond
    templeton_bond_isin = "LU0195953079"
    templeton_bond_name = "Templeton Global Bond I acc EUR"
    if templeton_bond_isin in PROXY_ISSUERS:
        rows_by_isin[templeton_bond_isin] = [
            {"asset_name": templeton_bond_name, "isin": templeton_bond_isin, "holding_name": "US Government Bonds", "holding_ticker": "", "weight_pct": Decimal("40"), "sector": "Fixed Income", "geo": "United States", "asset_class": "Fixed Income"},
            {"asset_name": templeton_bond_name, "isin": templeton_bond_isin, "holding_name": "Eurozone Government Bonds", "holding_ticker": "", "weight_pct": Decimal("40"), "sector": "Fixed Income", "geo": "Eurozone", "asset_class": "Fixed Income"},
            {"asset_name": templeton_bond_name, "isin": templeton_bond_isin, "holding_name": "Japan Government Bonds", "holding_ticker": "", "weight_pct": Decimal("20"), "sector": "Fixed Income", "geo": "Japan", "asset_class": "Fixed Income"},
        ]

    # Schroder ISF Italian Equity
    schroder_italy_isin = "LU0106239527"
    schroder_italy_name = "Schroder ISF Italian Equity C acc Eur"
    if schroder_italy_isin in PROXY_ISSUERS:
        rows_by_isin[schroder_italy_isin] = [
            {"asset_name": schroder_italy_name, "isin": schroder_italy_isin, "holding_name": "Enel Spa", "holding_ticker": "ENEL.MI", "weight_pct": Decimal("20"), "sector": "Utilities", "geo": "Italy", "asset_class": "Equity"},
            {"asset_name": schroder_italy_name, "isin": schroder_italy_isin, "holding_name": "Intesa Sanpaolo Spa", "holding_ticker": "ISP.MI", "weight_pct": Decimal("20"), "sector": "Financials", "geo": "Italy", "asset_class": "Equity"},
            {"asset_name": schroder_italy_name, "isin": schroder_italy_isin, "holding_name": "UniCredit Spa", "holding_ticker": "UCG.MI", "weight_pct": Decimal("20"), "sector": "Financials", "geo": "Italy", "asset_class": "Equity"},
            {"asset_name": schroder_italy_name, "isin": schroder_italy_isin, "holding_name": "Ferrari N.V.", "holding_ticker": "RACE.MI", "weight_pct": Decimal("15"), "sector": "Consumer Discretionary", "geo": "Italy", "asset_class": "Equity"},
            {"asset_name": schroder_italy_name, "isin": schroder_italy_isin, "holding_name": "Stellantis N.V.", "holding_ticker": "STLAM.MI", "weight_pct": Decimal("15"), "sector": "Consumer Discretionary", "geo": "Italy", "asset_class": "Equity"},
            {"asset_name": schroder_italy_name, "isin": schroder_italy_isin, "holding_name": "Nexi S.p.A.", "holding_ticker": "NEXI.MI", "weight_pct": Decimal("10"), "sector": "Financials", "geo": "Italy", "asset_class": "Equity"},
        ]

    return rows_by_isin


def read_proxy_metadata() -> dict[str, dict[str, Any]]:
    rows_by_isin = load_proxy_exposure_rows()
    if not rows_by_isin:
        return {}
    try:
        fetched_at = datetime.fromtimestamp(PROXY_EXPOSURES_CSV.stat().st_mtime).isoformat(timespec="seconds")
    except OSError:
        fetched_at = ""
    metadata: dict[str, dict[str, Any]] = {}
    for isin, rows in rows_by_isin.items():
        weight_sum = sum((row["weight_pct"] for row in rows), ZERO)
        metadata[isin] = {
            "issuer": PROXY_ISSUERS.get(isin, ""),
            "status": "proxy_exposure",
            "fetched_at": fetched_at,
            "holdings_url": PROXY_SOURCE_URLS.get(isin) or configured_path_label(PROXY_EXPOSURES_CSV),
            "rows": len(rows),
            "weight_sum": str(weight_sum.quantize(Decimal("0.0001")).normalize()),
            "message": PROXY_MESSAGES.get(isin) or "Non-official proxy composition for visualization; switch to Official only to hide it.",
        }
    return metadata


def read_exposures(berkshire_mode: str = "stock", proxy_mode: str = "on") -> dict[str, list[dict[str, Any]]]:
    exposures: dict[str, list[dict[str, Any]]] = {}
    if not EXPOSURES_CSV.exists():
        return exposures
    documents = read_etf_documents() if proxy_mode == "on" else {}

    with EXPOSURES_CSV.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            item = exposure_row_item(row)
            if not item:
                continue
            asset_name = item["asset_name"]
            isin = item["isin"]
            exposures.setdefault(exposure_key(asset_name, isin), []).append(item)
            if asset_name and isin:
                exposures.setdefault(exposure_key(asset_name, ""), []).append(item)

    if berkshire_mode == "lookthrough":
        rows = load_berkshire_lookthrough_rows()
        if rows:
            exposures[exposure_key("Berkshire Hathaway (B)", BERKSHIRE_ISIN)] = rows
            exposures[exposure_key("Berkshire Hathaway (B)", "")] = rows
    if proxy_mode == "on":
        for isin, rows in load_proxy_exposure_rows().items():
            if not rows:
                continue
            if exposure_key("", isin) in exposures and is_full_official_composition(documents.get(isin)):
                continue
            asset_name = rows[0]["asset_name"]
            exposures[exposure_key(asset_name, isin)] = rows
            exposures[exposure_key(asset_name, "")] = rows
    return exposures


def determine_asset_type_from_class(asset_class: str) -> str:
    ac = (asset_class or "").lower()
    if ac in ["single share", "equities", "equity"]:
        return "STOCK"
    if ac in ["cash", "cash equivalent", "cash collateral and margins", "currency", "fx"]:
        return "CUR"
    if ac in ["etf", "etf underlying", "commodity", "commodities", "gold"]:
        return "ETF"
    return "STOCK"


def determine_asset_type(asset: str, isin: str, symbol: str, broker: str, exposures: dict) -> str:
    asset_lower = asset.lower()
    broker_lower = (broker or "").lower()
    symbol_str = (symbol or "")
    
    # 1. Currency / Crypto
    if (
        broker_lower == "crypto wallet" 
        or symbol_str.endswith("-USD") 
        or asset_lower in ["btc", "eth", "ton", "usdc", "usdt"]
    ):
        return "CUR"
        
    # 2. Check exposures
    key1 = exposure_key(asset, isin)
    key2 = exposure_key(asset, "")
    rows = exposures.get(key1) or exposures.get(key2)
    if rows:
        if all(r.get("asset_class") == "Single share" for r in rows):
            return "STOCK"
        if all(r.get("asset_class") in ["Cash", "Cash equivalent", "Cash Collateral and Margins"] for r in rows):
            return "CUR"
        return "ETF"
            
    # 3. Fallback based on name keywords
    etf_keywords = ["etf", "acc", "dist", "swap", "ucits", "index", "msci", "ftse", "stoxx", "leveraged", "lev"]
    if any(k in asset_lower for k in etf_keywords):
        return "ETF"
        
    return "STOCK"


def read_etf_documents() -> dict[str, dict[str, Any]]:
    if not ETF_DOCUMENTS_JSON.exists():
        return {}
    try:
        payload = json.loads(ETF_DOCUMENTS_JSON.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if isinstance(payload, dict) and isinstance(payload.get("funds"), list):
        return {
            str(row.get("isin") or "").strip().upper(): row
            for row in payload["funds"]
            if str(row.get("isin") or "").strip()
        }
    if isinstance(payload, dict):
        return {
            str(isin).strip().upper(): row
            for isin, row in payload.items()
            if isinstance(row, dict) and str(isin).strip()
        }
    return {}


def is_full_official_composition(document: dict[str, Any] | None) -> bool:
    status = str((document or {}).get("status") or "").strip()
    return status in FULL_OFFICIAL_COMPOSITION_STATUSES


def add_distribution_amount(bucket: dict[str, Decimal], key: str, amount: Decimal) -> None:
    bucket[key] = bucket.get(key, ZERO) + amount


def composition_source_label(position: dict[str, Any], is_single_share: bool) -> str:
    if is_single_share:
        return "stock"
    symbol = str(position.get("symbol") or "").strip()
    if symbol:
        return symbol
    asset = str(position.get("asset") or "").strip()
    return asset


HOLDING_NAME_OVERRIDES = {
    "ADVANCED MICRO DEVICES": "Advanced Micro Devices",
    "ADVANCED MICRO DEVICES INC": "Advanced Micro Devices",
    "ALIBABA GROUP HOLDING": "Alibaba Group",
    "ALIBABA GROUP HOLDING LTD": "Alibaba Group",
    "ALIBABA GROUP HOLDING LTD ADR": "Alibaba Group",
    "ALIBABA GROUP HOLDING-SP ADR": "Alibaba Group",
    "ALPHABET": "Alphabet",
    "ALPHABET INC": "Alphabet",
    "ALPHABET INC CLASS A": "Alphabet",
    "ALPHABET INC CLASS C": "Alphabet",
    "AMAZON.COM": "Amazon.com",
    "AMAZON.COM INC": "Amazon.com",
    "AMERICAN EXPRESS": "American Express",
    "AMERICAN EXPRESS CO": "American Express",
    "APPLE": "Apple",
    "APPLE INC": "Apple",
    "BANK AMERICA": "Bank of America",
    "BANK AMERICA CORP": "Bank of America",
    "BERKSHIRE HATHAWAY": "Berkshire Hathaway",
    "BERKSHIRE HATHAWAY INC CLASS B": "Berkshire Hathaway",
    "BROADCOM": "Broadcom",
    "BROADCOM INC": "Broadcom",
    "CHEVRON": "Chevron",
    "CHEVRON CORPORATION": "Chevron",
    "CHUBB LTD SWITZ": "Chubb",
    "COCA COLA": "Coca-Cola",
    "COCA COLA CO": "Coca-Cola",
    "JPMORGAN CHASE": "JPMorgan Chase",
    "JPMORGAN CHASE & CO": "JPMorgan Chase",
    "KRAFT HEINZ": "Kraft Heinz",
    "KRAFT HEINZ CO": "Kraft Heinz",
    "META PLATFORMS": "Meta Platforms",
    "META PLATFORMS INC": "Meta Platforms",
    "META PLATFORMS INC CLASS A": "Meta Platforms",
    "MICROSOFT": "Microsoft",
    "MICROSOFT CORP": "Microsoft",
    "MOODYS": "Moody's",
    "MOODYS CORP": "Moody's",
    "NVIDIA": "NVIDIA",
    "NVIDIA CORP": "NVIDIA",
    "OCCIDENTAL PETE": "Occidental Petroleum",
    "OCCIDENTAL PETE CORP": "Occidental Petroleum",
    "TAIWAN SEMICONDUCTOR MANUFACTURING": "Taiwan Semiconductor Manufacturing",
    "TAIWAN SEMICONDUCTOR MANUFACTURING CO LTD": "Taiwan Semiconductor Manufacturing",
    "TAIWAN SEMICONDUCTOR MANUFACTURING CO LTD ADR": "Taiwan Semiconductor Manufacturing",
    "TESLA": "Tesla",
    "TESLA INC": "Tesla",
}


LEGAL_SUFFIX_RE = re.compile(
    r"\b("
    r"INC|INCORPORATED|CORP|CORPORATION|CO|COMPANY|LTD|LIMITED|PLC|SA|SE|NV|AG|SPA|"
    r"ORD|ORDINARY SHARES?|COMMON STOCK|REGISTERED SHARES?|REG|ADR|ADS|"
    r"CLASS [A-Z]|CL [A-Z]|[A-Z]-SHS|[A-Z] SHS"
    r")\b\.?",
    flags=re.I,
)


def title_holding_name(value: str) -> str:
    words = []
    acronyms = {"AMD", "ASML", "BP", "BYD", "IBM", "ING", "JPMORGAN", "LVMH", "NVIDIA", "SK", "TSMC"}
    for word in re.split(r"(\s+|&|-)", value.lower()):
        upper = word.upper()
        if upper in acronyms:
            words.append(upper if upper != "JPMORGAN" else "JPMorgan")
        elif word in {" ", "-", "&"} or word.isspace():
            words.append(word)
        elif word:
            words.append(word[:1].upper() + word[1:])
        else:
            words.append(word)
    return "".join(words).strip()


def canonical_holding_name(name: str) -> str:
    raw = re.sub(r"\s+", " ", (name or "").strip())
    if not raw:
        return "Unclassified"
    if raw.startswith("Other issuer holdings"):
        return raw
    if raw.startswith("Other proxy holdings"):
        return raw
    if raw.startswith("EUR overnight cash equivalent"):
        return raw

    normalized = raw.upper().replace(".", "")
    normalized = normalized.replace(" AND ", " & ")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    override = HOLDING_NAME_OVERRIDES.get(normalized)
    if override:
        return override

    compact = LEGAL_SUFFIX_RE.sub(" ", normalized)
    compact = re.sub(r"\s+", " ", compact).strip(" -")
    override = HOLDING_NAME_OVERRIDES.get(compact)
    if override:
        return override
    if compact:
        return title_holding_name(compact)
    return title_holding_name(normalized)


COMMON_HOLDING_TICKERS = {
    "ALLIANZ": "ALV",
    "ZURICH INSURANCE GROUP": "ZURN.SW",
    "AXA": "CS",
    "INTEL": "INTC",
    "MICRON TECHNOLOGY": "MU",
    "SAMSUNG ELECTRONICS": "SMSN.IL",
    "MUENCHENER RUECKVER N": "MUV2.DE",
    "APPLE": "AAPL",
    "NVIDIA": "NVDA",
    "VISA": "V",
    "ALPHABET": "GOOGL",
    "SK HYNIX": "000660.KS",
    "MASTERCARD": "MA",
    "ALIBABA GROUP HOLDING REPRESEN": "BABA",
    "GENERALI": "G",
    "SWISS RE": "SREN.SW",
    "JPMORGAN CHASE": "JPM",
    "BANK OF AMERICA": "BAC",
    "MICROSOFT": "MSFT",
    "CROWDSTRIKE HOLDINGS": "CRWD",
    "PRUDENTIAL": "PRU",
    "BERKSHIRE HATHAWAY": "BRK-B",
    "TENCENT HOLDINGS": "TCEHY",
    "CISCO SYSTEMS": "CSCO",
    "META PLATFORMS": "META",
    "AMERICAN EXPRESS": "AXP",
    "DELL TECHNOLOGIES": "DELL",
    "SWISS LIFE HLDG N": "SLHN.SW",
    "CME GROUP": "CME",
    "ORACLE": "ORCL",
    "AMAZON COM": "AMZN",
    "AMAZONCOM": "AMZN",
    "AVIVA": "AV.L",
    "SAMPO": "SAMPO.HE",
    "MERCADOLIBRE": "MELI",
    "NN GROUP": "NN",
    "CHARLES SCHWAB": "SCHW",
    "INTUIT": "INTU",
    "LEGAL & GENERAL GROUP": "LGEN.L",
    "PALANTIR TECHNOLOGIES": "PLTR",
    "INTERNATIONAL BUSINESS MACHINES": "IBM",
    "GOLDMAN SACHS GROUP": "GS",
    "HSBC HOLDINGS": "HSBC",
    "APPLOVIN": "APP",
    "HANNOVER RUECK": "HNR1.DE",
    "SAP": "SAP",
    "ROYAL BANK OF CANADA": "RY",
    "BROADCOM": "AVGO",
}


BLOOMBERG_TO_YAHOO_SUFFIX = {
    "GR": ".DE",
    "US": "",
    "FP": ".PA",
    "SW": ".SW",
    "LN": ".L",
    "CN": ".TO",
    "IM": ".MI",
    "AU": ".AX",
    "SP": ".SI",
    "SM": ".MC",
    "BB": ".BR",
    "HK": ".HK",
    "JP": ".T",
    "JT": ".T",
    "IT": ".MI",
    "NO": ".OL",
    "PW": ".WA",
    "DC": ".CO",
    "AV": ".VI",
    "PL": ".LS",
    "SS": ".ST",
}


def normalize_holding_ticker(ticker: str, holding_name: str = "", geo: str = "") -> str:
    if not ticker:
        return ""
    
    ticker = ticker.strip()
    
    # Handle Bloomberg suffixes (e.g. "ALV GR")
    if " " in ticker:
        parts = ticker.split()
        if len(parts) == 2:
            symbol, suffix = parts[0], parts[1].upper()
            if suffix in BLOOMBERG_TO_YAHOO_SUFFIX:
                ticker = symbol + BLOOMBERG_TO_YAHOO_SUFFIX[suffix]
    
    # Handle trailing slashes
    if ticker.endswith("/"):
        ticker = ticker.rstrip("/")
        
    # Handle slash (e.g. "BRK/B" -> "BRK-B")
    if "/" in ticker:
        ticker = ticker.replace("/", "-")
        
    # Handle numeric tickers (e.g. "005930")
    if ticker.isdigit():
        geo_clean = (geo or "").strip().lower()
        if "korea" in geo_clean:
            ticker = ticker + ".KS"
        elif "taiwan" in geo_clean:
            ticker = ticker + ".TW"
        elif "hong kong" in geo_clean or "china" in geo_clean:
            ticker = ticker + ".HK"
        elif "japan" in geo_clean:
            ticker = ticker + ".T"
            
    return ticker


def clean_company_name(name: str) -> str:
    if not name:
        return ""
    val = re.sub(r"\s+", " ", name.strip()).upper().replace(".", "")
    val = val.replace(" AND ", " & ")
    val = LEGAL_SUFFIX_RE.sub(" ", val)
    val = re.sub(r"\s+", " ", val).strip(" -")
    return val


def resolve_ticker_by_name(holding_name: str, position_symbols: dict[str, str]) -> str:
    cleaned_holding = clean_company_name(holding_name)
    if not cleaned_holding:
        return ""
    # 1. Exact match on cleaned names
    for pos_name, symbol in position_symbols.items():
        if clean_company_name(pos_name) == cleaned_holding:
            return symbol
    # 2. Substring match (e.g. "APPLE" inside "APPLE INC" or vice versa)
    for pos_name, symbol in position_symbols.items():
        cleaned_pos = clean_company_name(pos_name)
        if not cleaned_pos:
            continue
        if cleaned_pos in cleaned_holding or cleaned_holding in cleaned_pos:
            return symbol
    return ""


SECTOR_MAPPING = {
    # Technology / IT
    "technology": "Information Technology",
    "information technology": "Information Technology",
    
    # Communication Services
    "communication": "Communication Services",
    "communication services": "Communication Services",
    "telecommunications": "Communication Services",
    
    # Financials
    "financials": "Financials",
    "diversified banks": "Financials",
    "property & casualty insurance": "Financials",
    "life & health insurance": "Financials",
    "asset management & custody banks": "Financials",
    "financial exchanges & data": "Financials",
    "multi-line insurance": "Financials",
    "transaction & payment processing services": "Financials",
    "investment banking & brokerage": "Financials",
    "regional banks": "Financials",
    "diversified financial services": "Financials",
    "insurance brokers": "Financials",
    "consumer finance": "Financials",
    "reinsurance": "Financials",
    "diversified capital markets": "Financials",
    "mortgage reits": "Financials",
    "commercial & residential mortgage finance": "Financials",
    "specialized finance": "Financials",
    
    # Cash / Currency
    "cash and/or derivatives": "Cash / Money Market",
    "cash / money market": "Cash / Money Market",
    "cash": "Cash / Money Market",
    "cash equivalent": "Cash / Money Market",
    "cash collateral and margins": "Cash / Money Market",
    "currency": "Cash / Money Market",
    "fx": "Cash / Money Market",
    
    # Unknown / Unclassified
    "unknown": "Unclassified",
    "unknown from issuer data": "Unclassified",
    "unclassified": "Unclassified",
}

def normalize_sector(name: str) -> str:
    if not name:
        return "Unclassified"
    key = name.strip().lower()
    return SECTOR_MAPPING.get(key, name.strip())


def distribution_rows(
    bucket: dict[str, Decimal],
    total: Decimal,
    name_key: str,
    source_assets: dict[str, set[str]] | None = None,
    tickers: dict[str, str] | None = None,
    asset_classes: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    rows = []
    for key, value in sorted(bucket.items(), key=lambda item: item[1], reverse=True):
        row = {
            name_key: key,
            "market_value_eur": money(value),
            "weight_pct": float((value / total * Decimal("100")).quantize(Decimal("0.01"))) if total > ZERO else 0.0,
        }
        if source_assets is not None:
            row["source_assets"] = sorted(source_assets.get(key, set()))
        if tickers is not None and key in tickers:
            row["holding_ticker"] = tickers[key]
        if asset_classes is not None and key in asset_classes:
            row["asset_class"] = asset_classes[key]
            row["asset_type"] = determine_asset_type_from_class(asset_classes[key])
        rows.append(row)
    return rows


FUND_DISPLAY_NAMES = {
    "IE00023EZQ82": "iShares Digital Entertainment and Education UCITS ETF",
    "IE000YDOORK7": "Xtrackers MSCI Fintech Innovation UCITS ETF 1C",
    "IE00B4L5Y983": "iShares Core MSCI World UCITS ETF",
    "IE00B5BMR087": "iShares Core S&P 500 UCITS ETF",
    "IE00B5MTXJ97": "Invesco STOXX Europe 600 Optimised Insurance UCITS ETF Acc",
    "IE00BGV5VN51": "Xtrackers Artificial Intelligence and Big Data UCITS ETF 1C",
    "IE00BK5BQT80": "Vanguard FTSE All-World UCITS ETF USD Accumulating",
    "IE00BKM4GZ66": "iShares Core MSCI Emerging Markets IMI UCITS ETF",
    "IE00BM67HL84": "Xtrackers MSCI World Financials UCITS ETF 1C",
    "LU0290358497": "Xtrackers II EUR Overnight Rate Swap UCITS ETF 1C",
    "LU1681045370": "Amundi MSCI Emerging Markets UCITS ETF",
    "NL0011683594": "VanEck Morningstar Developed Markets Dividend Leaders UCITS ETF",
}


def display_fund_name(asset: str, isin: str, document: dict[str, Any]) -> str:
    if isin in FUND_DISPLAY_NAMES:
        return FUND_DISPLAY_NAMES[isin]

    product_url = str(document.get("product_url") or "")
    if product_url:
        slug = urllib.parse.urlparse(product_url).path.rstrip("/").split("/")[-1]
        slug = re.sub(r"^[A-Z0-9]{12}-", "", slug)
        slug = slug.replace("ishares-", "iShares-")
        words = [word for word in slug.split("-") if word and word not in {"fund", "siteEntryPassthrough"}]
        if words:
            acronyms = {"ai", "eur", "usd", "ucits", "etf", "msci", "imi", "s&p", "stoxx", "ftse"}
            pretty_words = []
            for word in words:
                lower = word.lower()
                if lower in acronyms:
                    pretty_words.append(lower.upper())
                elif lower == "ishares":
                    pretty_words.append("iShares")
                elif lower == "xtrackers":
                    pretty_words.append("Xtrackers")
                elif lower == "vaneck":
                    pretty_words.append("VanEck")
                else:
                    pretty_words.append(lower.capitalize())
            return " ".join(pretty_words)

    return str(document.get("asset_name") or asset)


def composition_source_row(
    position: dict[str, Any],
    rows: list[dict[str, Any]] | None,
    document: dict[str, Any] | None,
) -> dict[str, Any] | None:
    asset = str(position.get("asset") or "").strip()
    isin = str(position.get("isin") or "").strip().upper()
    if not rows and not document:
        return None
    if rows and all(row.get("asset_class") == "Single share" for row in rows):
        return None
    if rows and all(row.get("asset_class") == "Cash equivalent" for row in rows) and not document:
        status = "cash_equivalent"
    else:
        status = str((document or {}).get("status") or ("official_metadata_missing" if rows else "official_source_not_found"))
    fund_name = display_fund_name(asset, isin, document or {})
    return {
        "asset": asset,
        "isin": isin,
        "fund_name": fund_name,
        "issuer": str((document or {}).get("issuer") or ""),
        "status": status,
        "fetched_at": str((document or {}).get("fetched_at") or ""),
        "source_url": str((document or {}).get("holdings_url") or (document or {}).get("product_url") or ""),
        "rows": int((document or {}).get("rows") or len(rows or [])),
        "weight_sum": str((document or {}).get("weight_sum") or ""),
        "message": str((document or {}).get("message") or ""),
    }


def calculate_distribution(
    positions: list[dict[str, Any]],
    exposures: dict[str, list[dict[str, Any]]],
    berkshire_mode: str = "stock",
    proxy_mode: str = "on",
) -> dict[str, Any]:
    documents = read_etf_documents()
    if berkshire_mode == "lookthrough":
        metadata = read_berkshire_metadata()
        if metadata:
            documents[BERKSHIRE_ISIN] = metadata
    if proxy_mode == "on":
        for isin, metadata in read_proxy_metadata().items():
            if is_full_official_composition(documents.get(isin)):
                continue
            documents[isin] = metadata
    position_symbols = {p["asset"]: p["symbol"] for p in positions if p.get("symbol")}
    open_positions = [
        position
        for position in positions
        if position.get("is_open") and position.get("market_value_eur") is not None and Decimal(str(position["market_value_eur"])) > ZERO
    ]
    total_value = sum((Decimal(str(position["market_value_eur"])) for position in open_positions), ZERO)
    by_holding: dict[str, Decimal] = {}
    by_holding_sources: dict[str, set[str]] = {}
    holding_tickers: dict[str, str] = {}
    holding_classes: dict[str, str] = {}
    by_sector: dict[str, Decimal] = {}
    by_sector_holdings: dict[str, dict[str, Decimal]] = {}
    by_geo: dict[str, Decimal] = {}
    by_asset_class: dict[str, Decimal] = {}
    missing = []
    covered_assets = 0
    exploded_rows = []
    composition_sources = []

    for position in open_positions:
        value = Decimal(str(position["market_value_eur"]))
        asset = str(position.get("asset") or "").strip()
        isin = str(position.get("isin") or "").strip().upper()
        rows = exposures.get(exposure_key(asset, isin)) or exposures.get(exposure_key(asset, ""))
        document = documents.get(isin)
        source_row = composition_source_row(position, rows, document)
        if source_row:
            composition_sources.append(source_row)
        if not rows:
            missing.append(
                {
                    "asset": asset,
                    "isin": isin,
                    "market_value_eur": money(value),
                    "status": str((document or {}).get("status") or "missing_exposure_row"),
                    "message": str((document or {}).get("message") or "No distribution row is available."),
                }
            )
            fallback_holding = asset or isin or "Unclassified"
            fallback_sector = normalize_sector(str(position.get("sector") or "Unclassified"))
            fallback_geo = str(position.get("geo") or "Unclassified")
            fallback_asset_class = str(position.get("asset_class") or "Unclassified")
            add_distribution_amount(by_holding, fallback_holding, value)
            add_distribution_amount(by_sector, fallback_sector, value)
            by_sector_holdings.setdefault(fallback_sector, {})[fallback_holding] = \
                by_sector_holdings.setdefault(fallback_sector, {}).get(fallback_holding, ZERO) + value
            add_distribution_amount(by_geo, fallback_geo, value)
            add_distribution_amount(by_asset_class, fallback_asset_class, value)
            fallback_ticker = normalize_holding_ticker(str(position.get("symbol") or ""), fallback_holding, fallback_geo)
            holding_tickers[fallback_holding] = fallback_ticker
            holding_classes[fallback_holding] = fallback_asset_class
            exploded_rows.append(
                {
                    "source_asset": asset,
                    "source_isin": isin,
                    "holding_name": fallback_holding,
                    "holding_ticker": fallback_ticker,
                    "market_value_eur": money(value),
                    "weight_pct": float((value / total_value * Decimal("100")).quantize(Decimal("0.01"))) if total_value > ZERO else 0.0,
                    "sector": fallback_sector,
                    "geo": fallback_geo,
                    "asset_class": fallback_asset_class,
                }
            )
            continue

        covered_assets += 1
        is_single_share = all(row.get("asset_class") == "Single share" for row in rows)
        source_label = composition_source_label(position, is_single_share)
        row_weight = sum((row["weight_pct"] for row in rows), ZERO)
        divisor = row_weight if row_weight > Decimal("100") else Decimal("100")
        allocated = ZERO
        for row in rows:
            amount = value * row["weight_pct"] / divisor
            allocated += amount
            raw_holding = row["holding_name"] or asset
            if raw_holding == "Other issuer holdings":
                holding = f"Other issuer holdings - {asset}"
            else:
                holding = canonical_holding_name(raw_holding)
            add_distribution_amount(by_holding, holding, amount)
            if source_label:
                by_holding_sources.setdefault(holding, set()).add(source_label)
            norm_sector = normalize_sector(row["sector"])
            add_distribution_amount(by_sector, norm_sector, amount)
            by_sector_holdings.setdefault(norm_sector, {})[holding] = \
                by_sector_holdings.setdefault(norm_sector, {}).get(holding, ZERO) + amount
            add_distribution_amount(by_geo, row["geo"], amount)
            add_distribution_amount(by_asset_class, row["asset_class"], amount)
            
            ticker = row["holding_ticker"]
            if not ticker:
                ticker = holding_tickers.get(holding, "")
            if not ticker:
                ticker = COMMON_HOLDING_TICKERS.get(clean_company_name(holding), "")
            if not ticker:
                ticker = resolve_ticker_by_name(holding, position_symbols)
                
            ticker = normalize_holding_ticker(ticker, holding, row["geo"])
            holding_tickers[holding] = ticker
            holding_classes[holding] = row["asset_class"]
            exploded_rows.append(
                {
                    "source_asset": asset,
                    "source_isin": isin,
                    "holding_name": holding,
                    "holding_ticker": ticker,
                    "market_value_eur": money(amount),
                    "weight_pct": float((amount / total_value * Decimal("100")).quantize(Decimal("0.01"))) if total_value > ZERO else 0.0,
                    "sector": row["sector"],
                    "geo": row["geo"],
                    "asset_class": row["asset_class"],
                }
            )

        remainder = max(ZERO, value - allocated)
        if remainder > Decimal("0.01"):
            label = f"Other issuer holdings - {asset}"
            add_distribution_amount(by_holding, label, remainder)
            if asset:
                by_holding_sources.setdefault(label, set()).add(asset)
            norm_remainder_sector = normalize_sector("Unknown from issuer data")
            add_distribution_amount(by_sector, norm_remainder_sector, remainder)
            by_sector_holdings.setdefault(norm_remainder_sector, {})[label] = \
                by_sector_holdings.setdefault(norm_remainder_sector, {}).get(label, ZERO) + remainder
            add_distribution_amount(by_geo, "Unknown from issuer data", remainder)
            add_distribution_amount(by_asset_class, "ETF underlying", remainder)
            holding_tickers[label] = ""
            holding_classes[label] = "ETF underlying"

    return {
        "source_file": configured_path_label(EXPOSURES_CSV),
        "documents_file": configured_path_label(ETF_DOCUMENTS_JSON) if ETF_DOCUMENTS_JSON.exists() else "",
        "total_value_eur": money(total_value),
        "covered_assets": covered_assets,
        "open_assets": len(open_positions),
        "missing": sorted(missing, key=lambda item: item["market_value_eur"], reverse=True),
        "composition_sources": sorted(composition_sources, key=lambda item: (item["status"] != "ok", item["asset"])),
        "composition_source_coverage": {
            "resolved": sum(
                1
                for item in composition_sources
                if item["status"]
                in {"ok", "cached", "cash_equivalent", "partial_official_holdings", "official_sec_13f", "proxy_exposure"}
            ),
            "total": len(composition_sources),
        },
        "underlying": distribution_rows(by_holding, total_value, "holding", by_holding_sources, holding_tickers, holding_classes)[:30],
        "sectors": [{
            **s_row,
            "holdings": [{
                "holding": h_name,
                "holding_ticker": holding_tickers.get(h_name, ""),
                "market_value_eur": money(h_val),
                "weight_pct": float((h_val / total_value * Decimal("100")).quantize(Decimal("0.01"))) if total_value > ZERO else 0.0,
            } for h_name, h_val in sorted(by_sector_holdings.get(s_row["sector"], {}).items(), key=lambda x: x[1], reverse=True)]
        } for s_row in distribution_rows(by_sector, total_value, "sector")],
        "geographies": distribution_rows(by_geo, total_value, "geo"),
        "asset_classes": distribution_rows(by_asset_class, total_value, "asset_class"),
        "rows": sorted(exploded_rows, key=lambda item: item["market_value_eur"], reverse=True)[:100],
        "source_rows": sorted(exploded_rows, key=lambda item: (item["source_asset"], -item["market_value_eur"])),
    }


def trade_cash_amount(trade: Trade) -> tuple[Decimal, bool]:
    if trade.grand_total_present:
        return convert_cash_to_eur(abs(trade.grand_total), trade.cash_currency, trade.date)
    if trade.total_spend:
        return convert_cash_to_eur(abs(trade.total_spend), trade.cash_currency, trade.date)
    if trade.price and trade.quantity_diff:
        return convert_cash_to_eur(abs(trade.price * trade.quantity_diff), trade.cash_currency, trade.date)
    return ZERO, False


def normalize_currency_code(currency: Any) -> str:
    raw = str(currency or "EUR").strip()
    if not raw:
        return "EUR"
    upper = raw.upper()
    if raw in {"GBp", "GBX"} or upper in {"GBX", "GBPENCE"}:
        return "GBp"
    return upper


def fx_base_currency(currency: Any) -> str:
    normalized = normalize_currency_code(currency)
    return "GBP" if normalized == "GBp" else normalized


def fx_symbol_for(currency: str) -> tuple[str, bool]:
    currency = fx_base_currency(currency)
    if currency == "USD":
        return "EURUSD=X", True
    return f"{currency}EUR=X", False


def convert_cash_to_eur(amount: Decimal, currency: str, target_date: date) -> tuple[Decimal, bool]:
    currency = fx_base_currency(currency)
    if currency in {"", "E", "EUR"}:
        return amount, False
    symbol, invert = fx_symbol_for(currency)
    history = fetch_history(symbol, target_date - timedelta(days=10), target_date, refresh=False)
    rate = previous_price(history.get("prices", {}), target_date)
    if rate is None:
        return amount, True
    if invert:
        rate = 1 / rate
    return amount * Decimal(str(rate)), False


def summarize_trades(trades: list[Trade]) -> dict[str, Any]:
    quantities: dict[str, Decimal] = {}
    cost_basis: dict[str, Decimal] = {}
    realized_by_asset: dict[str, Decimal] = {}
    realized_cost_by_asset: dict[str, Decimal] = {}
    position_names: dict[str, str] = {}
    position_isins: dict[str, str] = {}
    realized_pl = ZERO
    invested = ZERO
    proceeds = ZERO
    fees = ZERO
    taxes = ZERO
    approximate_cost_basis = ZERO
    series: list[dict[str, Any]] = []

    for trade in trades:
        asset = trade.isin or trade.asset
        position_names.setdefault(asset, trade.asset)
        position_isins.setdefault(asset, trade.isin)
        quantities.setdefault(asset, ZERO)
        cost_basis.setdefault(asset, ZERO)
        realized_by_asset.setdefault(asset, ZERO)
        realized_cost_by_asset.setdefault(asset, ZERO)
        amount, approximate = trade_cash_amount(trade)
        if approximate:
            approximate_cost_basis += amount

        fees += trade.fees
        taxes += trade.tax

        if trade.quantity_diff >= ZERO:
            invested += amount
            quantities[asset] += trade.quantity_diff
            cost_basis[asset] += amount
        else:
            sell_quantity = abs(trade.quantity_diff)
            previous_quantity = quantities[asset]
            previous_cost = cost_basis[asset]
            if previous_quantity > ZERO and sell_quantity > ZERO:
                removed_cost = min(previous_cost, previous_cost * sell_quantity / previous_quantity)
            else:
                removed_cost = ZERO
            realized_delta = amount - removed_cost
            if trade.broker == "Fineco" and trade.tax == ZERO and realized_delta > ZERO:
                taxes += fineco_capital_gain_tax_from_net_gain(realized_delta)
            proceeds += amount
            cost_basis[asset] = max(ZERO, previous_cost - removed_cost)
            quantities[asset] = previous_quantity - sell_quantity
            realized_pl += realized_delta
            realized_by_asset[asset] += realized_delta
            realized_cost_by_asset[asset] += removed_cost

        series.append(
            {
                "date": trade.date.isoformat(),
                "invested": money(invested),
                "proceeds": money(proceeds),
                "net_contributions": money(invested - proceeds),
                "open_cost_basis": money(sum(cost_basis.values(), ZERO)),
                "realized_pl": money(realized_pl),
                "fees": money(fees),
                "taxes": money(taxes),
            }
        )

    positions = []
    for asset in sorted(quantities):
        quantity = quantities[asset]
        if abs(quantity) < Decimal("0.00000001"):
            quantity = ZERO
        realized_cost = realized_cost_by_asset.get(asset, ZERO)
        realized_value = realized_by_asset.get(asset, ZERO)
        positions.append(
            {
                "asset": position_names.get(asset, asset),
                "isin": position_isins.get(asset, ""),
                "quantity": decimal_to_float(quantity),
                "cost_basis_eur": money(cost_basis[asset]),
                "is_open": quantity > ZERO,
                "realized_pl_eur": money(realized_value),
                "realized_pl_pct": float((realized_value / realized_cost * Decimal("100")).quantize(Decimal("0.01"))) if realized_cost > ZERO else None,
            }
        )

    return {
        "positions": positions,
        "series": compress_series(series),
        "totals": {
            "invested": money(invested),
            "proceeds": money(proceeds),
            "net_contributions": money(invested - proceeds),
            "open_cost_basis": money(sum(cost_basis.values(), ZERO)),
            "realized_pl": money(realized_pl),
            "fees": money(fees),
            "taxes": money(taxes),
            "approximate_cost_basis": money(approximate_cost_basis),
        },
    }


def compress_series(series: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_date: dict[str, dict[str, Any]] = {}
    for point in series:
        by_date[point["date"]] = point
    return [by_date[key] for key in sorted(by_date)]


def extract_symbol(search_result: Any) -> dict[str, str] | None:
    quotes = getattr(search_result, "quotes", None)
    if quotes is None and isinstance(search_result, dict):
        quotes = search_result.get("quotes")
    if not quotes:
        return None

    for quote in quotes:
        symbol = quote.get("symbol") if isinstance(quote, dict) else getattr(quote, "symbol", "")
        if not symbol:
            continue
        name = quote.get("shortname") if isinstance(quote, dict) else getattr(quote, "shortname", "")
        exchange = quote.get("exchange") if isinstance(quote, dict) else getattr(quote, "exchange", "")
        return {"symbol": symbol, "name": name or "", "exchange": exchange or ""}
    return None


def yahoo_symbol_from_mapping(ticker: str, exchange: str) -> str:
    ticker = (ticker or "").strip()
    exchange = (exchange or "").strip().upper()
    if not ticker:
        return ""
    if "." in ticker or "=" in ticker or "-" in ticker:
        return ticker
    if exchange in {"BVME", "BIT", "MILAN", "MILANO", "BORSA ITALIANA"}:
        return f"{ticker}.MI"
    return ticker


def mapping_for(asset: str, isin: str, mappings: dict[str, dict[str, str]]) -> dict[str, str]:
    if asset in mappings:
        return mappings[asset]
    if isin:
        for mapping in mappings.values():
            if mapping.get("isin") == isin:
                return mapping
    return {}


_symbol_cache_in_memory = None


def get_symbol_cache():
    global _symbol_cache_in_memory
    if _symbol_cache_in_memory is None:
        _symbol_cache_in_memory = load_json(SYMBOL_CACHE)
    return _symbol_cache_in_memory


_price_cache_in_memory = None


def get_price_cache():
    global _price_cache_in_memory
    if _price_cache_in_memory is None:
        _price_cache_in_memory = load_json(PRICE_CACHE)
    return _price_cache_in_memory


_news_cache_in_memory = None


def get_news_cache():
    global _news_cache_in_memory
    if _news_cache_in_memory is None:
        _news_cache_in_memory = load_json(NEWS_CACHE)
    return _news_cache_in_memory


def resolve_isin(isin: str, refresh: bool = False, direct_symbol: str = "") -> dict[str, Any]:
    if direct_symbol:
        return {"isin": isin, "symbol": direct_symbol, "status": "resolved", "source": "mapping"}
    if not isin:
        return {"status": "missing_isin"}
    if yf is None:
        return {"status": "yfinance_missing"}

    cache = get_symbol_cache()
    cached = cache.get(isin)
    if cached and not refresh:
        return {**cached, "status": cached.get("status", "resolved")}

    try:
        result = yf.Search(
            isin,
            max_results=5,
            news_count=0,
            lists_count=0,
            include_cb=False,
            include_nav_links=False,
            include_research=False,
            include_cultural_assets=False,
            timeout=5,
            raise_errors=False,
        )
        symbol = extract_symbol(result)
        if symbol:
            payload = {**symbol, "isin": isin, "status": "resolved", "resolved_at": int(time.time())}
        else:
            payload = {"isin": isin, "status": "unresolved", "resolved_at": int(time.time())}
    except Exception as exc:
        payload = {"isin": isin, "status": "lookup_error", "error": str(exc), "resolved_at": int(time.time())}

    cache[isin] = payload
    save_json(SYMBOL_CACHE, cache)
    return payload


def fast_info_value(info: Any, key: str) -> Any:
    try:
        if isinstance(info, dict):
            return info.get(key)
        return info[key]
    except Exception:
        return getattr(info, key, None)


def infer_currency(symbol: str) -> str:
    symbol = symbol.upper()
    if symbol.endswith((".DE", ".MI", ".AS", ".PA")):
        return "EUR"
    if symbol.endswith(".L"):
        return "GBp"
    if symbol.endswith("=X"):
        return "EUR"
    return "USD"


def fetch_price(symbol: str, refresh: bool = False) -> dict[str, Any]:
    if not symbol:
        return {"status": "missing_symbol"}
    if yf is None:
        return {"status": "yfinance_missing"}

    cache = get_price_cache()
    cached = cache.get(symbol)
    now = int(time.time())
    if (
        cached
        and cached.get("status") == "priced"
        and not refresh
        and now - int(cached.get("fetched_at", 0)) < PRICE_TTL_SECONDS
    ):
        return cached

    try:
        ticker = yf.Ticker(symbol)
        currency = infer_currency(symbol)
        try:
            info = ticker.fast_info
            price = fast_info_value(info, "last_price") or fast_info_value(info, "lastPrice")
            currency = fast_info_value(info, "currency") or currency
        except Exception:
            price = None
        if price is None or (isinstance(price, float) and math.isnan(price)):
            history = ticker.history(period="10d")
            if history.empty:
                raise ValueError("No last price returned.")
            price = float(history["Close"].dropna().iloc[-1])
        payload = {
            "symbol": symbol,
            "price": float(price),
            "currency": normalize_currency_code(currency),
            "status": "priced",
            "fetched_at": now,
            "price_date": date.today().isoformat(),
        }
    except Exception as exc:
        fallback = latest_cached_history_price(symbol)
        if fallback:
            cache[symbol] = fallback
            save_json(PRICE_CACHE, cache)
            return fallback
        payload = {"symbol": symbol, "status": "price_error", "error": str(exc), "fetched_at": now}

    cache[symbol] = payload
    save_json(PRICE_CACHE, cache)
    return payload


_history_cache_in_memory = None


def get_history_cache():
    global _history_cache_in_memory
    if _history_cache_in_memory is None:
        _history_cache_in_memory = load_json(HISTORY_CACHE)
    return _history_cache_in_memory


def cached_history_for_range(
    cache: dict[str, Any],
    symbol: str,
    start: date,
    end: date,
    now: int,
) -> dict[str, Any] | None:
    exact_key = f"{symbol}|{start.isoformat()}|{end.isoformat()}"
    exact = cache.get(exact_key)
    if (
        isinstance(exact, dict)
        and exact.get("status") == "priced"
        and now - int(exact.get("fetched_at", 0)) < HISTORY_TTL_SECONDS
    ):
        return exact

    for key, payload in cache.items():
        if not isinstance(payload, dict) or payload.get("status") != "priced":
            continue
        parts = key.split("|")
        if len(parts) != 3 or parts[0] != symbol:
            continue
        try:
            cached_start = date.fromisoformat(parts[1])
            cached_end = date.fromisoformat(parts[2])
        except ValueError:
            continue
        if cached_start <= start and cached_end >= end and now - int(payload.get("fetched_at", 0)) < HISTORY_TTL_SECONDS:
            return payload
    return None


def fetch_history(symbol: str, start: date, end: date, refresh: bool = False) -> dict[str, Any]:
    if not symbol:
        return {"status": "missing_symbol", "prices": {}}
    if yf is None:
        return {"status": "yfinance_missing", "prices": {}}

    cache = get_history_cache()
    now = int(time.time())
    key = f"{symbol}|{start.isoformat()}|{end.isoformat()}"
    cached = None if refresh else cached_history_for_range(cache, symbol, start, end, now)
    if cached:
        return cached

    try:
        ticker = yf.Ticker(symbol)
        history = ticker.history(start=start.isoformat(), end=(end + timedelta(days=1)).isoformat(), auto_adjust=False)
        if history.empty:
            raise ValueError("No historical prices returned.")
        prices = {
            idx.date().isoformat(): float(value)
            for idx, value in history["Close"].dropna().items()
            if value is not None and not math.isnan(float(value))
        }
        try:
            info = ticker.fast_info
            currency = normalize_currency_code(fast_info_value(info, "currency") or infer_currency(symbol))
        except Exception:
            currency = infer_currency(symbol)
        payload = {
            "symbol": symbol,
            "currency": currency,
            "prices": prices,
            "status": "priced",
            "fetched_at": now,
            "range_start": start.isoformat(),
            "range_end": end.isoformat(),
        }
    except Exception as exc:
        payload = {"symbol": symbol, "status": "history_error", "error": str(exc), "prices": {}, "fetched_at": now}

    cache[key] = payload
    save_json(HISTORY_CACHE, cache)
    return payload


_PRICE_LOOKUP_CACHE: dict[int, tuple[dict[str, float], int, tuple[date, ...], tuple[float, ...]]] = {}


def price_lookup_index(prices: dict[str, float]) -> tuple[tuple[date, ...], tuple[float, ...]]:
    cache_key = id(prices)
    cached = _PRICE_LOOKUP_CACHE.get(cache_key)
    if cached and cached[0] is prices and cached[1] == len(prices):
        return cached[2], cached[3]

    pairs: list[tuple[date, float]] = []
    for raw_date, value in prices.items():
        if value is None:
            continue
        try:
            parsed_date = date.fromisoformat(str(raw_date))
            parsed_value = float(value)
        except (TypeError, ValueError):
            continue
        if not math.isnan(parsed_value):
            pairs.append((parsed_date, parsed_value))
    pairs.sort(key=lambda item: item[0])
    dates = tuple(item[0] for item in pairs)
    values = tuple(item[1] for item in pairs)

    if len(_PRICE_LOOKUP_CACHE) > 256:
        _PRICE_LOOKUP_CACHE.clear()
    _PRICE_LOOKUP_CACHE[cache_key] = (prices, len(prices), dates, values)
    return dates, values


def previous_price_point(prices: dict[str, float], target: date) -> tuple[float, date] | None:
    dates, values = price_lookup_index(prices)
    if not dates:
        return None
    idx = bisect_right(dates, target) - 1
    if idx < 0:
        return None
    return values[idx], dates[idx]


def previous_price(prices: dict[str, float], target: date) -> float | None:
    point = previous_price_point(prices, target)
    if point is None:
        return None
    return point[0]


def price_payload_for_target(payload: dict[str, Any] | None, target: date) -> float | None:
    if not payload or payload.get("status") != "priced":
        return None
    source = payload.get("source")
    if source == "history_cache" and payload.get("price_date") != target.isoformat():
        return None
    try:
        price = float(payload["price"])
    except (KeyError, TypeError, ValueError):
        return None
    if math.isnan(price):
        return None
    return price


def price_point_for_date(
    prices: dict[str, float],
    target: date,
    current_price: dict[str, Any] | None = None,
) -> tuple[float, date] | None:
    current = price_payload_for_target(current_price, target)
    if current is not None and target == date.today():
        return current, target
    return previous_price_point(prices, target)


def current_price_overrides(
    symbol_histories: dict[str, dict[str, Any]],
    target: date,
    refresh: bool = False,
) -> dict[str, dict[str, Any]]:
    if target != date.today():
        return {}
    overrides: dict[str, dict[str, Any]] = {}
    for symbol in sorted(symbol_histories):
        history = symbol_histories.get(symbol) or {}
        if history.get("status") != "priced" or not history.get("prices"):
            continue
        price_data = fetch_price(symbol, refresh=refresh)
        if price_payload_for_target(price_data, target) is not None:
            overrides[symbol] = price_data
    return overrides


def benchmark_delta(latest: dict[str, Any], past: dict[str, Any], key: str) -> float | None:
    latest_value = latest.get(f"{key}_return_pct")
    past_value = past.get(f"{key}_return_pct")
    if latest_value is None or past_value is None:
        return None
    latest_price_date = latest.get(f"{key}_price_date")
    past_price_date = past.get(f"{key}_price_date")
    if latest_price_date is not None and past_price_date is not None and latest_price_date <= past_price_date:
        return None
    denom = 100.0 + float(past_value)
    if denom <= 0:
        return None
    return ((100.0 + float(latest_value)) / denom - 1.0) * 100.0



def fetch_crypto_eur_history(asset: str, start: date, end: date, refresh: bool = False) -> dict[str, Any]:
    asset = (asset or "").upper()
    cache = get_history_cache()
    key = f"crypto-eur:{asset}|{start.isoformat()}|{end.isoformat()}"
    cached = cache.get(key)
    now = int(time.time())
    if cached and not refresh and now - int(cached.get("fetched_at", 0)) < HISTORY_TTL_SECONDS:
        return cached

    import urllib.parse
    import urllib.request

    prices: dict[str, float] = {}
    try:
        if asset == "USDC":
            fx_history = fetch_history("EURUSD=X", start, end, refresh=refresh)
            if fx_history.get("status") == "priced" and fx_history.get("prices"):
                for d_str, val in fx_history["prices"].items():
                    if val > 0:
                        prices[d_str] = float(Decimal("1") / Decimal(str(val)))
        elif asset in {"BTC", "ETH", "TON"}:
            quote_currency = "USD" if asset == "TON" else "EUR"
            fx_history = fetch_history("EURUSD=X", start, end, refresh=refresh) if quote_currency == "USD" else {"prices": {}}
            cursor = start
            while cursor <= end:
                chunk_end = min(end, cursor + timedelta(days=299))
                params = urllib.parse.urlencode(
                    {
                        "start": datetime.combine(cursor, datetime.min.time()).replace(tzinfo=timezone.utc).isoformat(),
                        "end": datetime.combine(chunk_end, datetime.min.time()).replace(tzinfo=timezone.utc).isoformat(),
                        "granularity": "86400",
                    }
                )
                url = f"https://api.exchange.coinbase.com/products/{asset}-{quote_currency}/candles?{params}"
                req = urllib.request.Request(url, headers={"User-Agent": "portfolio-dashboard/1.0"})
                with urllib.request.urlopen(req, timeout=20) as response:
                    candles = json.loads(response.read().decode("utf-8"))
                if isinstance(candles, list):
                    for candle in candles:
                        if not isinstance(candle, list) or len(candle) < 5:
                            continue
                        candle_date = datetime.fromtimestamp(int(candle[0]), tz=timezone.utc).date()
                        close = float(candle[4])
                        if quote_currency == "USD":
                            eurusd = previous_price(fx_history.get("prices", {}), candle_date)
                            if eurusd:
                                close = close / eurusd
                            else:
                                continue
                        prices[candle_date.isoformat()] = close
                cursor = chunk_end + timedelta(days=1)
        payload = {
            "symbol": f"{asset}-EUR",
            "currency": "EUR",
            "prices": prices,
            "status": "priced" if prices else "history_error",
            "fetched_at": now,
        }
    except Exception as exc:
        payload = {"symbol": f"{asset}-EUR", "status": "history_error", "error": str(exc), "prices": {}, "fetched_at": now}

    cache[key] = payload
    save_json(HISTORY_CACHE, cache)
    return payload


def latest_cached_history_price(symbol: str) -> dict[str, Any] | None:
    cache = get_history_cache()
    best_date: str | None = None
    best_price: float | None = None
    best_currency = infer_currency(symbol)
    for key, payload in cache.items():
        if not key.startswith(f"{symbol}|") or payload.get("status") != "priced":
            continue
        prices = payload.get("prices", {})
        for price_date, price in prices.items():
            if best_date is None or price_date > best_date:
                best_date = price_date
                best_price = price
                best_currency = payload.get("currency", best_currency)
    if best_price is None:
        return None
    return {
        "symbol": symbol,
        "price": float(best_price),
        "currency": normalize_currency_code(best_currency),
        "status": "priced",
        "fetched_at": int(time.time()),
        "source": "history_cache",
        "price_date": best_date,
    }


def month_end_dates(start: date, end: date) -> set[date]:
    dates: set[date] = set()
    cursor = date(start.year, start.month, 1)
    while cursor <= end:
        if cursor.month == 12:
            next_month = date(cursor.year + 1, 1, 1)
        else:
            next_month = date(cursor.year, cursor.month + 1, 1)
        month_end = next_month - timedelta(days=1)
        if start <= month_end <= end:
            dates.add(month_end)
        cursor = next_month
    dates.add(end)
    return dates


def fx_to_eur(currency: str, refresh: bool = False) -> dict[str, Any]:
    currency = fx_base_currency(currency)
    if currency == "EUR":
        return {"rate": 1.0, "status": "native"}
    symbol, invert = fx_symbol_for(currency)
    price = fetch_price(symbol, refresh=refresh)
    if price.get("status") == "priced":
        rate = float(price["price"])
        return {"rate": 1 / rate if invert else rate, "status": "priced", "symbol": symbol}
    return {"rate": None, "status": price.get("status", "fx_error"), "symbol": symbol}


def build_instrument_refs(
    trades: list[Trade], mappings: dict[str, dict[str, str]], refresh: bool = False
) -> dict[str, dict[str, str]]:
    refs: dict[str, dict[str, str]] = {}
    for trade in trades:
        key = trade.isin or trade.asset
        if key in refs:
            continue
        mapping = mapping_for(trade.asset, trade.isin, mappings)
        direct_symbol = yahoo_symbol_from_mapping(mapping.get("ticker", ""), mapping.get("exchange", ""))
        symbol_data = resolve_isin(trade.isin or mapping.get("isin", ""), refresh=refresh, direct_symbol=direct_symbol)
        refs[key] = {
            "asset": trade.asset,
            "isin": trade.isin or mapping.get("isin", ""),
            "symbol": symbol_data.get("symbol", ""),
            "status": symbol_data.get("status", "missing_isin"),
        }
    return refs


def historical_fx_rate(
    currency: str,
    fx_histories: dict[str, dict[str, Any]],
    target: date,
    live_fx_prices: dict[str, dict[str, Any]] | None = None,
) -> float | None:
    currency = normalize_currency_code(currency)
    if currency == "EUR":
        return 1.0
    if currency == "GBp":
        currency = "GBP"
    symbol, invert = fx_symbol_for(currency)
    history = fx_histories.get(symbol, {})
    price_point = price_point_for_date(history.get("prices", {}), target, (live_fx_prices or {}).get(symbol))
    rate = price_point[0] if price_point else None
    if rate is None:
        return None
    return 1 / rate if invert else rate


EUROSTAT_CACHE_PATH = SETTINGS.cache_path("eurostat-cpi.json")

def fetch_eurostat_cpi() -> dict[str, float]:
    import urllib.request
    import json
    now = int(time.time())
    if EUROSTAT_CACHE_PATH.exists():
        try:
            with open(EUROSTAT_CACHE_PATH, "r") as f:
                cached = json.load(f)
            if now - cached.get("fetched_at", 0) < 86400:  # 24 hours TTL
                return cached.get("data", {})
        except Exception:
            pass

    try:
        url = 'https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_minr?format=JSON&lang=EN&geo=EA&coicop18=TOTAL&freq=M&unit=I15'
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as res:
            raw = json.loads(res.read().decode("utf-8"))
        
        time_dim = raw['dimension']['time']['category']
        labels = sorted(time_dim['index'].keys(), key=lambda k: time_dim['index'][k])
        values = raw['value']
        
        cpi_data = {}
        for label in labels:
            idx = str(time_dim['index'][label])
            val = values.get(idx)
            if val is not None:
                cpi_data[label] = float(val)
                
        if cpi_data:
            payload = {"fetched_at": now, "data": cpi_data}
            EUROSTAT_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            save_json(EUROSTAT_CACHE_PATH, payload)
            return cpi_data
    except Exception as e:
        print("Error fetching Eurostat HICP CPI:", e)
        
    if EUROSTAT_CACHE_PATH.exists():
        try:
            with open(EUROSTAT_CACHE_PATH, "r") as f:
                return json.load(f).get("data", {})
        except Exception:
            pass
            
    return {}


def load_cash_histories(person: str) -> tuple[list[tuple[date, Decimal, Decimal]], list[tuple[date, Decimal, Decimal]], list[tuple[date, Decimal, Decimal]]]:
    tr_cash_history: list[tuple[date, Decimal, Decimal]] = []
    tr_file = latest_trade_republic_export() if person == PRIMARY_PORTFOLIO_ID else latest_family_trade_republic_export(person)

    if tr_file and tr_file.exists():
        try:
            with tr_file.open(newline="", encoding="utf-8-sig") as handle:
                for row in csv.DictReader(handle):
                    dt_str = row.get("date")
                    if not dt_str:
                        continue
                    t_date = datetime.strptime(dt_str, "%Y-%m-%d").date()
                    amount = parse_decimal(row.get("amount"))
                    fee = parse_decimal(row.get("fee"))
                    tax = parse_decimal(row.get("tax"))
                    cash_change = amount + fee + tax

                    t_type = row.get("type", "")
                    contrib_change = ZERO
                    if t_type in {"CUSTOMER_INBOUND", "CUSTOMER_INPAYMENT", "TRANSFER_INSTANT_INBOUND", "VIBAN_TRANSFER_INBOUND"}:
                        contrib_change = cash_change
                    elif t_type in {"CUSTOMER_OUTBOUND_REQUEST", "TRANSFER_INSTANT_OUTBOUND", "CARD_TRANSACTION", "CARD_TRANSACTION_INTERNATIONAL", "CARD_ORDERING_FEE"}:
                        contrib_change = cash_change

                    tr_cash_history.append((t_date, cash_change, contrib_change))
        except Exception:
            pass
    tr_cash_history.sort(key=lambda item: item[0])

    bbva_cash_history: list[tuple[date, Decimal, Decimal]] = []
    if person == PRIMARY_PORTFOLIO_ID:
        bbva_cash_history.append((date(2024, 1, 8), Decimal("4800.00"), Decimal("4800.00")))
        bbva_files = sorted(ROOT_DIR.glob(SETTINGS.bbva_pattern))
        if bbva_files:
            bbva_file = bbva_files[-1]
            import shutil
            import tempfile

            temp_xlsx = Path(tempfile.gettempdir()) / f"bbva_temp_{os.getpid()}_{threading.get_ident()}.xlsx"
            try:
                shutil.copy(bbva_file, temp_xlsx)
                wb = load_workbook(temp_xlsx, read_only=True)
                sheet = wb.active
                for row in sheet.iter_rows(values_only=True):
                    if len(row) < 7:
                        continue
                    _, op_date_str, causale, _, _, imp = row[1:7]
                    if causale and causale != "Causale" and imp:
                        try:
                            op_date = datetime.strptime(str(op_date_str).strip(), "%d/%m/%Y").date()
                        except Exception:
                            continue
                        try:
                            clean_imp = str(imp).replace(" EUR", "").replace(",", ".").strip()
                            amount = Decimal(clean_imp)
                        except Exception:
                            continue

                        if amount != ZERO:
                            cash_change = amount
                            contrib_change = ZERO if "INTERESSI" in str(causale).upper() else amount
                            bbva_cash_history.append((op_date, cash_change, contrib_change))
            except Exception:
                pass
            finally:
                if temp_xlsx.exists():
                    try:
                        temp_xlsx.unlink()
                    except OSError:
                        pass
    bbva_cash_history.sort(key=lambda item: item[0])
    revolut_cash_history = read_revolut_cash_events() if person == PRIMARY_PORTFOLIO_ID else []
    revolut_cash_history.sort(key=lambda item: item["datetime"])
    return tr_cash_history, bbva_cash_history, revolut_cash_history


def calculate_valuation_series(
    trades: list[Trade],
    mappings: dict[str, dict[str, str]],
    refresh: bool = False,
    person: str = PRIMARY_PORTFOLIO_ID,
    broker: str = "all",
) -> dict[str, Any]:
    if not trades:
        return {"series": [], "status": "empty"}

    start = min(trade.date for trade in trades)
    
    # Load dividends and cash interests to calculate Total Return series
    dividends = read_portfolio_dividends(person)
    interests = read_cash_interests(person)
    if broker != "all":
        dividends = [d for d in dividends if d.broker.lower() == broker]
        interests = [i for i in interests if i.get("broker", "").lower() == broker]

    tr_cash_history, bbva_cash_history, revolut_cash_history = load_cash_histories(person)

    end = date.today()
    refs = build_instrument_refs(trades, mappings, refresh=refresh)
    recent_dates = {end - timedelta(days=i) for i in range(35) if end - timedelta(days=i) >= start}
    valuation_dates = month_end_dates(start, end) | {trade.date for trade in trades} | recent_dates
    sorted_dates = sorted(valuation_dates)

    histories: dict[str, dict[str, Any]] = {}
    currencies: set[str] = set()
    for ref in refs.values():
        symbol = ref.get("symbol", "")
        if not symbol:
            continue
        history = fetch_history(symbol, start, end, refresh=refresh)
        histories[symbol] = history
        if history.get("status") == "priced":
            currencies.add(normalize_currency_code(history.get("currency") or "EUR"))

    fx_histories: dict[str, dict[str, Any]] = {}
    for currency in currencies:
        normalized = fx_base_currency(currency)
        if normalized and normalized != "EUR":
            symbol, _ = fx_symbol_for(normalized)
            fx_histories[symbol] = fetch_history(symbol, start, end, refresh=refresh)
    add_revolut_fx_histories(revolut_cash_history, start, end, fx_histories, refresh=refresh)

    holdings: dict[str, Decimal] = {}
    invested_by_asset: dict[str, Decimal] = {}
    invested = ZERO
    proceeds = ZERO
    invested_tr = ZERO
    proceeds_tr = ZERO
    invested_other = ZERO
    proceeds_other = ZERO
    trade_index = 0
    ordered_trades = sorted(trades, key=lambda item: (item.date, item.broker, item.asset, item.action))
    series: list[dict[str, Any]] = []

    # Fetch MSCI World prices
    msci_prices = {}
    msci_symbol = ""
    for sym in ["SWDA.MI", "EUNL.DE", "URTH"]:
        h = fetch_history(sym, start, end, refresh=refresh)
        if h and h.get("status") == "priced" and h.get("prices"):
            msci_prices = h["prices"]
            msci_symbol = sym
            break

    p0 = None
    if msci_prices:
        p0 = previous_price(msci_prices, start)
        if p0 is None:
            sorted_msci_dates = sorted(msci_prices.keys())
            if sorted_msci_dates:
                p0 = msci_prices[sorted_msci_dates[0]]

    # Fetch XEON prices
    xeon_prices = {}
    h_xeon = fetch_history("XEON.DE", start, end, refresh=refresh)
    if h_xeon and h_xeon.get("status") == "priced" and h_xeon.get("prices"):
        xeon_prices = h_xeon["prices"]

    xeon_p0 = None
    if xeon_prices:
        xeon_p0 = previous_price(xeon_prices, start)
        if xeon_p0 is None:
            sorted_xeon_dates = sorted(xeon_prices.keys())
            if sorted_xeon_dates:
                xeon_p0 = xeon_prices[sorted_xeon_dates[0]]

    # Load Eurostat CPI
    cpi_data = fetch_eurostat_cpi()
    
    def get_cpi_value(d: date) -> float | None:
        if not cpi_data:
            return None
        label = f"{d.year:04d}-{d.month:02d}"
        if label in cpi_data:
            return cpi_data[label]
        sorted_labels = sorted(cpi_data.keys())
        best_val = None
        for l in sorted_labels:
            if l <= label:
                best_val = cpi_data[l]
            else:
                break
        if best_val is not None:
            return best_val
        return cpi_data[sorted_labels[-1]] if sorted_labels else None

    start_cpi = get_cpi_value(start)
    live_prices = current_price_overrides(histories, end, refresh=refresh)
    live_fx_prices = current_price_overrides(fx_histories, end, refresh=refresh)
    live_msci_price = {}
    if msci_symbol and msci_prices:
        live_msci_price = current_price_overrides({msci_symbol: {"status": "priced", "prices": msci_prices}}, end, refresh=refresh).get(msci_symbol, {})
    live_xeon_price = {}
    if xeon_prices:
        live_xeon_price = current_price_overrides({"XEON.DE": {"status": "priced", "prices": xeon_prices}}, end, refresh=refresh).get("XEON.DE", {})

    for valuation_date in sorted_dates:
        while trade_index < len(ordered_trades) and ordered_trades[trade_index].date <= valuation_date:
            trade = ordered_trades[trade_index]
            key = trade.isin or trade.asset
            amount, _ = trade_cash_amount(trade)
            holdings[key] = holdings.get(key, ZERO) + trade.quantity_diff
            
            is_tr = (trade.broker.lower() == "trade republic")
            if trade.quantity_diff >= ZERO:
                invested += amount
                if is_tr:
                    invested_tr += amount
                else:
                    invested_other += amount
                invested_by_asset[key] = invested_by_asset.get(key, ZERO) + amount
            else:
                proceeds += amount
                if is_tr:
                    proceeds_tr += amount
                else:
                    proceeds_other += amount
                invested_by_asset[key] = invested_by_asset.get(key, ZERO) - amount
            trade_index += 1

        market_value = ZERO
        priced_positions = 0
        unpriced_positions = 0
        for key, quantity in holdings.items():
            if quantity <= ZERO:
                continue
            ref = refs.get(key, {})
            symbol = ref.get("symbol", "")
            history = histories.get(symbol, {})
            price_point = price_point_for_date(history.get("prices", {}), valuation_date, live_prices.get(symbol))
            price = price_point[0] if price_point else None
            currency = normalize_currency_code(history.get("currency") or "EUR")
            fx_rate = historical_fx_rate(currency, fx_histories, valuation_date, live_fx_prices=live_fx_prices)
            if price is None or fx_rate is None:
                unpriced_positions += 1
                fallback_val = invested_by_asset.get(key, ZERO)
                if fallback_val > ZERO:
                    market_value += fallback_val
                continue
            if currency == "GBp":
                price = price / 100
            market_value += quantity * Decimal(str(price)) * Decimal(str(fx_rate))
            priced_positions += 1

        net_contributions = invested - proceeds
        profit = market_value - net_contributions
        return_pct = (profit / net_contributions * Decimal("100")) if net_contributions > ZERO else ZERO
        
        # Accumulate dividends and cash interest up to valuation_date by broker
        accumulated_dividends_tr = sum((d.amount_eur for d in dividends if d.date <= valuation_date and d.broker.lower() == "trade republic"), ZERO)
        accumulated_dividends_other = sum((d.amount_eur for d in dividends if d.date <= valuation_date and d.broker.lower() != "trade republic"), ZERO)
        
        accumulated_interest_tr = sum((Decimal(str(i["net_eur"])) for i in interests if i["date"] <= valuation_date and i.get("broker", "").lower() == "trade republic"), ZERO)
        accumulated_interest_bbva = sum((Decimal(str(i["net_eur"])) for i in interests if i["date"] <= valuation_date and i.get("broker", "").lower() == "bbva"), ZERO)
        accumulated_interest_other = sum((Decimal(str(i["net_eur"])) for i in interests if i["date"] <= valuation_date and i.get("broker", "").lower() not in {"trade republic", "bbva"}), ZERO)

        # Get historical cash balances
        tr_cash_bal = sum(item[1] for item in tr_cash_history if item[0] <= valuation_date)
        tr_contrib = sum(item[2] for item in tr_cash_history if item[0] <= valuation_date)
        
        bbva_cash_bal = sum(item[1] for item in bbva_cash_history if item[0] <= valuation_date)
        bbva_contrib = sum(item[2] for item in bbva_cash_history if item[0] <= valuation_date)
        revolut_cash_bal = revolut_cash_balance_eur(revolut_cash_history, valuation_date, fx_histories, live_fx_prices)
        revolut_contrib = revolut_contributions_eur(revolut_cash_history, valuation_date, fx_histories)

        broker_lower = broker.lower()
        include_tr_cash = (broker_lower == "all" or broker_lower == "trade republic")
        include_bbva_cash = (broker_lower == "all" or broker_lower == "bbva")
        include_revolut_cash = broker_lower == "all"

        # Reconstruct total market value including cash balance under total return
        total_market_value = market_value + accumulated_dividends_other + accumulated_interest_other
        if include_tr_cash:
            total_market_value += tr_cash_bal
        else:
            total_market_value += accumulated_dividends_tr + accumulated_interest_tr
            
        if include_bbva_cash:
            total_market_value += bbva_cash_bal
        else:
            total_market_value += accumulated_interest_bbva

        if include_revolut_cash:
            total_market_value += revolut_cash_bal

        # Reconstruct total net contributions (Capital at Work) under total return
        total_net_contributions = (invested_other - proceeds_other)
        if include_tr_cash:
            total_net_contributions += tr_contrib
        else:
            total_net_contributions += (invested_tr - proceeds_tr)
            
        if include_bbva_cash:
            total_net_contributions += bbva_contrib

        if include_revolut_cash:
            total_net_contributions += revolut_contrib

        total_profit = total_market_value - total_net_contributions
        total_return_pct = (total_profit / total_net_contributions * Decimal("100")) if total_net_contributions > ZERO else ZERO

        msci_return = None
        msci_price_date = None
        if p0 and p0 > 0:
            price_point = price_point_for_date(msci_prices, valuation_date, live_msci_price)
            if price_point is not None:
                price_t, price_date = price_point
                msci_price_date = price_date.isoformat()
                msci_return = float((Decimal(str(price_t)) - Decimal(str(p0))) / Decimal(str(p0)) * 100)

        xeon_return = None
        xeon_price_date = None
        if xeon_p0 and xeon_p0 > 0:
            price_point = price_point_for_date(xeon_prices, valuation_date, live_xeon_price)
            if price_point is not None:
                price_t, price_date = price_point
                xeon_price_date = price_date.isoformat()
                xeon_return = float((Decimal(str(price_t)) - Decimal(str(xeon_p0))) / Decimal(str(xeon_p0)) * 100)

        # Real Eurozone HICP inflation index
        inflation_return = 0.0
        if start_cpi and start_cpi > 0:
            cpi_t = get_cpi_value(valuation_date)
            if cpi_t:
                inflation_return = float((Decimal(str(cpi_t)) - Decimal(str(start_cpi))) / Decimal(str(start_cpi)) * 100)
        else:
            # Fallback if Eurostat is completely offline
            days_since_start = (valuation_date - start).days
            inflation_return = float(((Decimal("1.02") ** (Decimal(str(days_since_start)) / Decimal("365.25"))) - 1) * 100)

        if market_value > ZERO and (net_contributions > ZERO or market_value > ZERO):
            series.append(
                {
                    "date": valuation_date.isoformat(),
                    "market_value": money(market_value),
                    "total_market_value": money(total_market_value),
                    "net_contributions": money(net_contributions),
                    "total_net_contributions": money(total_net_contributions),
                    "profit": money(profit),
                    "total_profit": money(total_profit),
                    "return_pct": float(return_pct.quantize(Decimal("0.01"))),
                    "total_return_pct": float(total_return_pct.quantize(Decimal("0.01"))),
                    "priced_positions": priced_positions,
                    "unpriced_positions": unpriced_positions,
                    "msci_return_pct": round(msci_return, 2) if msci_return is not None else None,
                    "msci_price_date": msci_price_date,
                    "xeon_return_pct": round(xeon_return, 2) if xeon_return is not None else None,
                    "xeon_price_date": xeon_price_date,
                    "inflation_return_pct": round(inflation_return, 2),
                }
            )

    return {
        "series": series,
        "status": "priced",
        "symbols": sorted({ref.get("symbol", "") for ref in refs.values() if ref.get("symbol")}),
        "variations": calculate_variations(series),
        "_history_context": {
            "start": start,
            "end": end,
            "histories": histories,
            "fx_histories": fx_histories,
            "msci_prices": msci_prices,
            "msci_symbol": msci_symbol,
            "xeon_prices": xeon_prices,
            "live_prices": live_prices,
            "live_fx_prices": live_fx_prices,
            "live_msci_price": live_msci_price,
            "live_xeon_price": live_xeon_price,
        },
    }


def get_historical_price_in_eur(prices: dict[str, float], fx_prices: dict[str, float], target_date: date, invert: bool, currency: str) -> float | None:
    asset_price = previous_price(prices, target_date)
    if asset_price is None:
        return None
    currency = normalize_currency_code(currency)
    if currency == "GBp":
        asset_price = asset_price / 100
    if fx_prices:
        fx_rate = previous_price(fx_prices, target_date)
        if fx_rate is not None:
            rate = 1 / fx_rate if invert else fx_rate
            return float(Decimal(str(asset_price)) * Decimal(str(rate)))
        return None
    return asset_price


def compute_position_variations(
    asset: str,
    symbol: str,
    currency: str,
    quantity: Decimal,
    current_value_eur: Decimal,
    is_crypto_wallet: bool,
    refresh: bool = False
) -> dict[str, dict[str, float]]:
    res = {
        "1d": {"pct": 0.0, "amount": 0.0},
        "1w": {"pct": 0.0, "amount": 0.0},
        "1m": {"pct": 0.0, "amount": 0.0},
    }
    if quantity <= ZERO:
        return res

    today = date.today()
    start_date = today - timedelta(days=45)

    try:
        if is_crypto_wallet:
            h = fetch_crypto_eur_history(asset, start_date, today, refresh=refresh)
            prices = h.get("prices", {})
            fx_prices = {}
            invert = False
            currency = "EUR"
        else:
            if not symbol:
                return res
            h = fetch_history(symbol, start_date, today, refresh=refresh)
            prices = h.get("prices", {})
            currency = normalize_currency_code(currency or h.get("currency") or "EUR")
            if currency != "EUR":
                fx_sym, invert = fx_symbol_for(currency)
                fx_h = fetch_history(fx_sym, start_date, today, refresh=refresh)
                fx_prices = fx_h.get("prices", {})
            else:
                fx_prices = {}
                invert = False

        if not prices:
            return res

        for period, days in [("1d", 1), ("1w", 7), ("1m", 30)]:
            target_date = today - timedelta(days=days)
            past_price = get_historical_price_in_eur(prices, fx_prices, target_date, invert, currency)
            if past_price is not None and past_price > 0:
                past_val = Decimal(str(past_price)) * quantity
                amount = current_value_eur - past_val
                pct_val = (amount / past_val * Decimal("100")) if past_val > 0 else ZERO
                res[period] = {
                    "pct": float(pct_val.quantize(Decimal("0.01"))),
                    "amount": float(amount.quantize(Decimal("0.01"))),
                }
    except Exception:
        pass
    return res


def enrich_positions(positions: list[dict[str, Any]], mappings: dict[str, dict[str, str]], refresh: bool = False) -> dict[str, Any]:
    exposures = read_exposures()
    enriched = []
    market_value = ZERO
    unrealized_pl = ZERO
    priced_assets = 0
    unpriced_assets = 0

    for position in positions:
        asset = position["asset"]
        quantity = Decimal(str(position["quantity"]))
        cost = Decimal(str(position["cost_basis_eur"]))
        position_isin = position.get("isin", "")
        mapping = mapping_for(asset, position_isin, mappings)
        isin = position_isin or mapping.get("isin", "")
        
        mapping_ticker = mapping.get("ticker", "")
        mapping_exchange = mapping.get("exchange", "")
        position_symbol = position.get("symbol", "")
        
        direct_symbol = yahoo_symbol_from_mapping(mapping_ticker, mapping_exchange)
        if not direct_symbol and position_symbol and not isin:
            direct_symbol = position_symbol

        row = {**position, "isin": isin, "symbol": "", "price": None, "price_currency": "", "market_value_eur": None}
        
        # Resolve symbol upfront to support logo mappings for both open and closed positions
        search_query = isin or position_symbol
        symbol_data = {}
        if (search_query or direct_symbol) and str(position.get("broker") or "").lower() != "crypto wallet":
            symbol_data = resolve_isin(search_query, refresh=refresh, direct_symbol=direct_symbol)
            row["symbol"] = symbol_data.get("symbol", "")

        snapshot_val = position.get("market_value_eur")
        if (
            str(position.get("broker") or "").lower() == "crypto wallet"
            and snapshot_val is not None
            and Decimal(str(snapshot_val)) > ZERO
        ):
            value = Decimal(str(snapshot_val))
            pricing_status = "crypto_wallet"
            price_currency = "EUR"
            fetched_at = None

            # Try to fetch live price dynamically
            if position_symbol:
                try:
                    price_data = fetch_price(position_symbol, refresh=refresh)
                    if price_data.get("status") == "priced":
                        fx = fx_to_eur(price_data.get("currency", "EUR"), refresh=refresh)
                        if fx.get("rate") is not None:
                            price_val = Decimal(str(price_data["price"]))
                            rate_val = Decimal(str(fx["rate"]))
                            value = quantity * price_val * rate_val
                            pricing_status = "priced"
                            price_currency = price_data.get("currency", "EUR")
                            fetched_at = price_data.get("fetched_at")
                except Exception:
                    pass

            price = value / quantity if quantity > ZERO else ZERO
            row.update(
                {
                    "symbol": position_symbol,
                    "price": float(price) if price > ZERO else None,
                    "price_currency": price_currency,
                    "market_value_eur": money(value),
                    "unrealized_pl_eur": money(value - cost),
                    "unrealized_pl_pct": float(((value - cost) / cost * Decimal("100")).quantize(Decimal("0.01"))) if cost > ZERO else None,
                    "display_pl_eur": money(value - cost),
                    "display_pl_pct": float(((value - cost) / cost * Decimal("100")).quantize(Decimal("0.01"))) if cost > ZERO else None,
                    "pricing_status": pricing_status,
                }
            )
            if fetched_at:
                row["fetched_at"] = fetched_at

            # Compute variations
            pos_vars = compute_position_variations(
                asset=asset,
                symbol=position_symbol,
                currency=price_currency,
                quantity=quantity,
                current_value_eur=value,
                is_crypto_wallet=True,
                refresh=refresh
            )
            row["variations"] = pos_vars

            market_value += value
            unrealized_pl += value - cost
            priced_assets += 1
            row["asset_type"] = determine_asset_type(asset, isin, row["symbol"], row.get("broker", ""), exposures)
            enriched.append(row)
            continue

        def apply_fallback_if_possible(err_status: str):
            nonlocal market_value, unrealized_pl, unpriced_assets
            snapshot_val = position.get("market_value_eur")
            if snapshot_val is not None and snapshot_val > 0:
                row["pricing_status"] = "snapshot"
                row["market_value_eur"] = snapshot_val
                market_value += Decimal(str(snapshot_val))
                snapshot_pl = position.get("display_pl_eur")
                if snapshot_pl is not None:
                    unrealized_pl += Decimal(str(snapshot_pl))
                unpriced_assets += 1

                # Compute variations for fallback snapshot
                is_crypto = str(position.get("broker") or "").lower() == "crypto wallet"
                pos_vars = compute_position_variations(
                    asset=asset,
                    symbol=position_symbol or direct_symbol,
                    currency=position.get("price_currency", "EUR") or "EUR",
                    quantity=quantity,
                    current_value_eur=Decimal(str(snapshot_val)),
                    is_crypto_wallet=is_crypto,
                    refresh=refresh
                )
                row["variations"] = pos_vars
            else:
                row["pricing_status"] = err_status
                if err_status == "closed":
                    row["display_pl_eur"] = position.get("realized_pl_eur")
                    row["display_pl_pct"] = position.get("realized_pl_pct")
                else:
                    unpriced_assets += 1
            row["asset_type"] = determine_asset_type(asset, isin, row.get("symbol", ""), row.get("broker", ""), exposures)
            enriched.append(row)

        if quantity <= ZERO:
            apply_fallback_if_possible("closed")
            continue
            
        if not search_query and not direct_symbol:
            apply_fallback_if_possible("missing_isin")
            continue

        if symbol_data.get("status") != "resolved":
            row["pricing_error"] = symbol_data.get("error", "")
            apply_fallback_if_possible(symbol_data.get("status", "unresolved"))
            continue

        price_data = fetch_price(row["symbol"], refresh=refresh)
        if price_data.get("status") != "priced":
            row["pricing_error"] = price_data.get("error", "")
            apply_fallback_if_possible(price_data.get("status", "price_error"))
            continue

        fx = fx_to_eur(price_data.get("currency", "EUR"), refresh=refresh)
        if fx.get("rate") is None:
            row["pricing_error"] = f"Could not convert {price_data.get('currency')} to EUR."
            apply_fallback_if_possible(fx.get("status", "fx_error"))
            continue

        price = Decimal(str(price_data["price"]))
        rate = Decimal(str(fx["rate"]))
        value = quantity * price * rate
        row.update(
            {
                "price": float(price),
                "price_currency": price_data.get("currency", "EUR"),
                "market_value_eur": money(value),
                "unrealized_pl_eur": money(value - cost),
                "unrealized_pl_pct": float(((value - cost) / cost * Decimal("100")).quantize(Decimal("0.01"))) if cost > ZERO else None,
                "display_pl_eur": money(value - cost),
                "display_pl_pct": float(((value - cost) / cost * Decimal("100")).quantize(Decimal("0.01"))) if cost > ZERO else None,
                "pricing_status": "priced",
                "fetched_at": price_data.get("fetched_at"),
            }
        )

        # Compute variations
        pos_vars = compute_position_variations(
            asset=asset,
            symbol=row["symbol"],
            currency=price_data.get("currency", "EUR"),
            quantity=quantity,
            current_value_eur=value,
            is_crypto_wallet=False,
            refresh=refresh
        )
        row["variations"] = pos_vars

        market_value += value
        unrealized_pl += value - cost
        priced_assets += 1
        row["asset_type"] = determine_asset_type(asset, isin, row["symbol"], row.get("broker", ""), exposures)
        enriched.append(row)

    return {
        "positions": sorted(enriched, key=lambda item: (not item["is_open"], item["asset"])),
        "market_value": money(market_value),
        "unrealized_pl": money(unrealized_pl),
        "priced_assets": priced_assets,
        "unpriced_assets": unpriced_assets,
    }


def calculate_portfolio_statistics(trades, mappings, person=PRIMARY_PORTFOLIO_ID, broker="all", history_context=None):
    import numpy as np

    if not trades:
        return None
    start_date = min(trade.date for trade in trades)
    end_date = date.today()
    if start_date >= end_date:
        return None
        
    dates_list = []
    curr = start_date
    while curr <= end_date:
        if curr.weekday() < 5:
            dates_list.append(curr)
        curr += timedelta(days=1)
        
    if not dates_list:
        return None
        
    tr_cash_events, bbva_cash_events, revolut_cash_events = load_cash_histories(person)
                
    dividends = read_portfolio_dividends(person)
    interests = read_cash_interests(person)
    
    refs = build_instrument_refs(trades, mappings, refresh=False)
    history_context = history_context or {}
    context_histories = history_context.get("histories", {}) if isinstance(history_context, dict) else {}
    histories = {}
    currencies = set()
    for ref in refs.values():
        symbol = ref.get("symbol", "")
        if not symbol: continue
        history = context_histories.get(symbol) or fetch_history(symbol, start_date - timedelta(days=30), end_date, refresh=False)
        histories[symbol] = history
        if history.get("status") == "priced":
            currencies.add(normalize_currency_code(history.get("currency") or "EUR"))
            
    fx_histories = dict(history_context.get("fx_histories", {}) if isinstance(history_context, dict) else {})
    for currency in currencies:
        normalized = fx_base_currency(currency)
        if normalized and normalized != "EUR":
            symbol, _ = fx_symbol_for(normalized)
            if symbol not in fx_histories:
                fx_histories[symbol] = fetch_history(symbol, start_date - timedelta(days=30), end_date, refresh=False)
    add_revolut_fx_histories(revolut_cash_events, start_date, end_date, fx_histories, refresh=False)
            
    live_prices = dict(history_context.get("live_prices", {}) if isinstance(history_context, dict) else {})
    live_fx_prices = dict(history_context.get("live_fx_prices", {}) if isinstance(history_context, dict) else {})
    live_msci_price = dict(history_context.get("live_msci_price", {}) if isinstance(history_context, dict) else {})
    live_xeon_price = dict(history_context.get("live_xeon_price", {}) if isinstance(history_context, dict) else {})

    msci_prices = history_context.get("msci_prices", {}) if isinstance(history_context, dict) else {}
    msci_symbol = history_context.get("msci_symbol", "") if isinstance(history_context, dict) else ""
    if not msci_prices:
        for sym in ["SWDA.MI", "EUNL.DE", "URTH"]:
            h = fetch_history(sym, start_date - timedelta(days=30), end_date, refresh=False)
            if h and h.get("status") == "priced" and h.get("prices"):
                msci_prices = h["prices"]
                msci_symbol = sym
                break

    xeon_prices = history_context.get("xeon_prices", {}) if isinstance(history_context, dict) else {}
    if not xeon_prices:
        h_xeon = fetch_history("XEON.DE", start_date - timedelta(days=30), end_date, refresh=False)
        if h_xeon and h_xeon.get("status") == "priced" and h_xeon.get("prices"):
            xeon_prices = h_xeon["prices"]
            
    broker_lower = broker.lower()
    include_tr_cash = (broker_lower == "all" or broker_lower == "trade republic")
    include_bbva_cash = (broker_lower == "all" or broker_lower == "bbva")
    include_revolut_cash = broker_lower == "all"
    
    filtered_trades = trades
    if broker_lower != "all":
        filtered_trades = [t for t in trades if t.broker.lower() == broker_lower]
        
    ordered_trades = sorted(filtered_trades, key=lambda item: item.date)
    
    daily_metrics = []
    holdings = {}
    cost_basis = {}
    invested_other = ZERO
    proceeds_other = ZERO
    invested_tr = ZERO
    proceeds_tr = ZERO
    trade_idx = 0
    
    for d in dates_list:
        while trade_idx < len(ordered_trades) and ordered_trades[trade_idx].date <= d:
            t = ordered_trades[trade_idx]
            asset = t.isin or t.asset
            amount, _ = trade_cash_amount(t)
            is_tr = (t.broker.lower() == "trade republic")
            
            if t.quantity_diff >= ZERO:
                holdings[asset] = holdings.get(asset, ZERO) + t.quantity_diff
                cost_basis[asset] = cost_basis.get(asset, ZERO) + amount
                if is_tr:
                    invested_tr += amount
                else:
                    invested_other += amount
            else:
                sell_qty = abs(t.quantity_diff)
                prev_qty = holdings.get(asset, ZERO)
                prev_cost = cost_basis.get(asset, ZERO)
                if prev_qty > ZERO:
                    removed_cost = min(prev_cost, prev_cost * sell_qty / prev_qty)
                else:
                    removed_cost = ZERO
                cost_basis[asset] = max(ZERO, prev_cost - removed_cost)
                holdings[asset] = max(ZERO, prev_qty - sell_qty)
                if is_tr:
                    proceeds_tr += amount
                else:
                    proceeds_other += amount
            trade_idx += 1
            
        sec_mv = ZERO
        for asset, qty in holdings.items():
            if qty <= ZERO: continue
            ref = refs.get(asset)
            if not ref:
                ref_found = next((r_val for r_asset, r_val in refs.items() if r_val.get("isin") == asset or r_asset == asset), None)
                if ref_found: ref = ref_found
                else: continue
            symbol = ref.get("symbol", "")
            if not symbol: continue
            h = histories.get(symbol)
            if not h or h.get("status") != "priced": continue
            
            price_point = price_point_for_date(h.get("prices", {}), d, live_prices.get(symbol))
            if price_point is None: continue
            price = price_point[0]
            
            val_in_curr = Decimal(str(price)) * qty
            currency = normalize_currency_code(h.get("currency") or "EUR")
            
            if currency != "EUR":
                normalized = fx_base_currency(currency)
                fx_sym, is_div = fx_symbol_for(normalized)
                fx_h = fx_histories.get(fx_sym)
                if fx_h and fx_h.get("prices"):
                    fx_point = price_point_for_date(fx_h["prices"], d, live_fx_prices.get(fx_sym))
                    fx_rate = fx_point[0] if fx_point else None
                    if fx_rate is not None and fx_rate > 0:
                        rate_dec = Decimal(str(fx_rate))
                        if currency == "GBp": val_in_curr = val_in_curr / Decimal('100')
                        multiplier = Decimal('1') / rate_dec if is_div else rate_dec
                        val_in_curr = val_in_curr * multiplier
            sec_mv += val_in_curr
            
        tr_cash_bal = sum(item[1] for item in tr_cash_events if item[0] <= d) if include_tr_cash else ZERO
        tr_contrib = sum(item[2] for item in tr_cash_events if item[0] <= d) if include_tr_cash else ZERO
        bbva_cash_bal = sum(item[1] for item in bbva_cash_events if item[0] <= d) if include_bbva_cash else ZERO
        bbva_contrib = sum(item[2] for item in bbva_cash_events if item[0] <= d) if include_bbva_cash else ZERO
        revolut_cash_bal = revolut_cash_balance_eur(revolut_cash_events, d, fx_histories, live_fx_prices) if include_revolut_cash else ZERO
        revolut_contrib = revolut_contributions_eur(revolut_cash_events, d, fx_histories) if include_revolut_cash else ZERO
        
        accumulated_dividends_other = sum((div.amount_eur for div in dividends if div.date <= d and div.broker.lower() != "trade republic"), ZERO)
        accumulated_interest_other = sum((Decimal(str(i["net_eur"])) for i in interests if i["date"] <= d and i.get("broker", "").lower() not in {"trade republic", "bbva"}), ZERO)
        
        # Total Return metrics
        total_mv = sec_mv + accumulated_dividends_other + accumulated_interest_other + tr_cash_bal + bbva_cash_bal + revolut_cash_bal
        total_nc = (invested_other - proceeds_other) + tr_contrib + bbva_contrib + revolut_contrib
        
        # Price Return metrics
        price_mv = sec_mv
        price_nc = (invested_other - proceeds_other) + (invested_tr - proceeds_tr)
        
        msci_point = price_point_for_date(msci_prices, d, live_msci_price if msci_symbol else None)
        msci_price = msci_point[0] if msci_point else None
        msci_price_date = msci_point[1] if msci_point else None

        xeon_point = price_point_for_date(xeon_prices, d, live_xeon_price)
        xeon_price = xeon_point[0] if xeon_point else None
        xeon_price_date = xeon_point[1] if xeon_point else None
            
        daily_metrics.append({
            'date': d,
            'total_mv': float(total_mv),
            'total_nc': float(total_nc),
            'price_mv': float(price_mv),
            'price_nc': float(price_nc),
            'msci': float(msci_price) if msci_price else None,
            'msci_date': msci_price_date,
            'xeon': float(xeon_price) if xeon_price else None,
            'xeon_date': xeon_price_date,
        })
        
    # Compute returns for both
    total_returns = []
    price_returns = []
    msci_returns = []
    xeon_returns = []
    daily_returns = []
    
    for i in range(1, len(daily_metrics)):
        prev = daily_metrics[i-1]
        curr = daily_metrics[i]
        
        # Total Return
        total_cf = curr['total_nc'] - prev['total_nc']
        total_denom = prev['total_mv'] + max(total_cf, 0)
        total_ret = None
        if total_denom > 0:
            total_ret = (curr['total_mv'] - prev['total_mv'] - total_cf) / total_denom
            total_returns.append(total_ret)
            
        # Price Return
        price_cf = curr['price_nc'] - prev['price_nc']
        price_denom = prev['price_mv'] + max(price_cf, 0)
        price_ret = None
        if price_denom > 0:
            price_ret = (curr['price_mv'] - prev['price_mv'] - price_cf) / price_denom
            price_returns.append(price_ret)
            
        # MSCI World
        p_prev = prev['msci']
        p_curr = curr['msci']
        msci_ret = None
        if p_prev and p_curr and p_prev > 0 and curr.get("msci_date") != prev.get("msci_date"):
            msci_ret = (p_curr - p_prev) / p_prev
            msci_returns.append(msci_ret)

        # XEON
        x_prev = prev['xeon']
        x_curr = curr['xeon']
        xeon_ret = None
        if x_prev and x_curr and x_prev > 0 and curr.get("xeon_date") != prev.get("xeon_date"):
            xeon_ret = (x_curr - x_prev) / x_prev
            xeon_returns.append(xeon_ret)

        daily_returns.append({
            "date": curr["date"].isoformat(),
            "total_return": float(total_ret) if total_ret is not None else None,
            "price_return": float(price_ret) if price_ret is not None else None,
            "msci_return": float(msci_ret) if msci_ret is not None else None,
            "xeon_return": float(xeon_ret) if xeon_ret is not None else None,
        })
            
    if not total_returns or not price_returns:
        return None
        
    tot_rets = np.array(total_returns)
    prc_rets = np.array(price_returns)
    msci_rets_only = np.array(msci_returns)
    xeon_rets_only = np.array(xeon_returns)
    
    rf_annual = 0.03
    rf_daily = rf_annual / 252
    
    def calculate_stats(rets, m_rets, x_rets):
        mean = np.mean(rets)
        std = np.std(rets)
        sharpe = ((mean - rf_daily) / std * np.sqrt(252)) if std > 0 else 0.0
        
        m_mean = np.mean(m_rets) if len(m_rets) > 0 else 0.0
        m_std = np.std(m_rets) if len(m_rets) > 0 else 0.0
        m_sharpe = ((m_mean - rf_daily) / m_std * np.sqrt(252)) if m_std > 0 else 0.0

        x_mean = np.mean(x_rets) if len(x_rets) > 0 else 0.0
        x_std = np.std(x_rets) if len(x_rets) > 0 else 0.0
        x_sharpe = ((x_mean - rf_daily) / x_std * np.sqrt(252)) if x_std > 0 else 0.0
        
        return {
            "portfolio": {
                "daily_variance_pct": float(np.var(rets) * 10000),
                "daily_volatility_pct": float(std * 100),
                "annualized_volatility_pct": float(std * np.sqrt(252) * 100),
                "sharpe_ratio": float(sharpe),
                "mean_daily_return_pct": float(mean * 100),
            },
            "msci": {
                "daily_variance_pct": float(np.var(m_rets) * 10000) if len(m_rets) > 0 else 0.0,
                "daily_volatility_pct": float(m_std * 100) if len(m_rets) > 0 else 0.0,
                "annualized_volatility_pct": float(m_std * np.sqrt(252) * 100) if len(m_rets) > 0 else 0.0,
                "sharpe_ratio": float(m_sharpe),
                "mean_daily_return_pct": float(m_mean * 100) if len(m_rets) > 0 else 0.0,
            },
            "xeon": {
                "daily_variance_pct": float(np.var(x_rets) * 10000) if len(x_rets) > 0 else 0.0,
                "daily_volatility_pct": float(x_std * 100) if len(x_rets) > 0 else 0.0,
                "annualized_volatility_pct": float(x_std * np.sqrt(252) * 100) if len(x_rets) > 0 else 0.0,
                "sharpe_ratio": float(x_sharpe),
                "mean_daily_return_pct": float(x_mean * 100) if len(x_rets) > 0 else 0.0,
            }
        }
        
    return {
        "total_return": calculate_stats(tot_rets, msci_rets_only, xeon_rets_only),
        "price_return": calculate_stats(prc_rets, msci_rets_only, xeon_rets_only),
        "days_evaluated": len(tot_rets),
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "daily_returns": daily_returns,
    }


def dashboard_payload(
    refresh: bool = False,
    person: str = PRIMARY_PORTFOLIO_ID,
    berkshire_mode: str = "stock",
    proxy_mode: str = "on",
    broker: str = "all",
    live_only: str = "off",
) -> dict[str, Any]:
    person = (person or PRIMARY_PORTFOLIO_ID).lower()
    berkshire_mode = normalize_berkshire_mode(berkshire_mode)
    proxy_mode = normalize_proxy_mode(proxy_mode)
    broker = (broker or "all").strip().lower()
    if person != PRIMARY_PORTFOLIO_ID:
        return family_dashboard_payload(person, refresh=refresh, berkshire_mode=berkshire_mode, proxy_mode=proxy_mode, broker=broker, live_only=live_only)

    trades, source = read_trades()
    dividends = read_dividends()
    wallet_positions = read_crypto_wallet_positions(person)

    # Get all brokers first (unfiltered)
    all_brokers = sorted(list(set(t.broker for t in trades if t.broker) | set(d.broker for d in dividends if d.broker)))
    if wallet_positions:
        all_brokers = sorted(set(all_brokers) | {str(position.get("broker") or "Crypto Wallet") for position in wallet_positions})

    # Filter by broker
    if broker != "all":
        trades = [t for t in trades if t.broker.lower() == broker]
        dividends = [d for d in dividends if d.broker.lower() == broker]
        wallet_positions = [p for p in wallet_positions if str(p.get("broker") or "").lower() == broker]

    mappings = read_mappings()

    # Filter by live_only
    if live_only == "on":
        live_trades = []
        for t in trades:
            mapping = mapping_for(t.asset, t.isin, mappings)
            direct_symbol = yahoo_symbol_from_mapping(mapping.get("ticker", ""), mapping.get("exchange", ""))
            if not direct_symbol and t.isin:
                direct_symbol = resolve_isin(t.isin).get("symbol", "")
            is_crypto = t.broker.lower() == "crypto wallet"
            if direct_symbol or is_crypto:
                live_trades.append(t)
        trades = live_trades
        dividends = [d for d in dividends if any(t.asset == d.asset for t in trades)]
        if wallet_positions:
            wallet_positions = [p for p in wallet_positions if p.get("pricing_status") != "snapshot"]
    summary = summarize_trades(trades)
    if wallet_positions:
        summary["positions"].extend(wallet_positions)
        if broker == "crypto wallet" and not summary["series"]:
            wallet_net = sum((Decimal(str(position.get("cost_basis_eur") or 0)) for position in wallet_positions), ZERO)
            if wallet_net <= ZERO:
                wallet_net = sum((Decimal(str(position.get("market_value_eur") or 0)) for position in wallet_positions), ZERO)
            summary["series"] = [
                {
                    "date": crypto_wallet_transaction_start_date().isoformat(),
                    "invested": money(wallet_net),
                    "proceeds": 0.0,
                    "net_contributions": money(wallet_net),
                    "open_cost_basis": money(wallet_net),
                    "realized_pl": 0.0,
                    "fees": 0.0,
                    "taxes": 0.0,
                },
                {
                    "date": date.today().isoformat(),
                    "invested": money(wallet_net),
                    "proceeds": 0.0,
                    "net_contributions": money(wallet_net),
                    "open_cost_basis": money(wallet_net),
                    "realized_pl": 0.0,
                    "fees": 0.0,
                    "taxes": 0.0,
                }
            ]
            summary["totals"]["invested"] = money(wallet_net)
            summary["totals"]["net_contributions"] = money(wallet_net)
            summary["totals"]["open_cost_basis"] = money(wallet_net)
    dividend_summary = summarize_dividends(dividends)
    contribution_summary = (
        crypto_wallet_contributions(wallet_positions)
        if broker == "crypto wallet" and wallet_positions
        else summarize_net_contributions(trades)
    )
    priced = enrich_positions(summary["positions"], mappings, refresh=refresh)
    distribution = calculate_distribution(
        priced["positions"],
        read_exposures(berkshire_mode=berkshire_mode, proxy_mode=proxy_mode),
        berkshire_mode=berkshire_mode,
        proxy_mode=proxy_mode,
    )
    valuation = (
        crypto_wallet_valuation(wallet_positions)
        if broker == "crypto wallet" and wallet_positions
        else calculate_valuation_series(trades, mappings, refresh=refresh, person=person, broker=broker)
    )

    extra_frictions = read_extra_friction_events()
    if broker != "all":
        extra_frictions = [f for f in extra_frictions if f.broker.lower() == broker]

    frictions = summarize_frictions(
        trade_friction_events(trades) + inferred_fineco_sell_tax_events(trades) + extra_frictions,
        priced["market_value"],
    )
    expenses = summarize_expense_events(read_expense_events(person, refresh=refresh))
    mapped_assets = set(mappings)
    trade_assets = {trade.asset for trade in trades} | {str(position.get("asset") or "") for position in wallet_positions}
    assets_without_isin = {
        position["asset"]
        for position in summary["positions"]
        if position["is_open"] and not position.get("isin") and not mapping_for(position["asset"], "", mappings).get("isin")
    }

    # Load dividends and cash interests to compute final total returns
    dividends = read_dividends()
    interests = read_cash_interests(person)
    if broker != "all":
        dividends = [d for d in dividends if d.broker.lower() == broker]
        interests = [i for i in interests if i.get("broker", "").lower() == broker]
    accumulated_dividends = sum((d.amount_eur for d in dividends), ZERO)
    accumulated_interest = sum((Decimal(str(i["net_eur"])) for i in interests), ZERO)
    total_market_value = Decimal(str(priced["market_value"])) + accumulated_dividends + accumulated_interest

    totals = {
        **summary["totals"],
        "market_value": priced["market_value"],
        "total_market_value": float(total_market_value.quantize(Decimal("0.01"))),
        "unrealized_pl": priced["unrealized_pl"],
        "estimated_total_value": money(Decimal(str(priced["market_value"]))),
        "priced_assets": priced["priced_assets"],
        "unpriced_assets": priced["unpriced_assets"],
    }
    if valuation["series"]:
        totals["return_pct"] = valuation["series"][-1]["return_pct"]
        totals["total_return_pct"] = valuation["series"][-1]["total_return_pct"]
        totals["historical_profit"] = valuation["series"][-1]["profit"]
        totals["historical_total_profit"] = valuation["series"][-1]["total_profit"]
        totals["total_market_value"] = valuation["series"][-1]["total_market_value"]
        totals["total_net_contributions"] = valuation["series"][-1]["total_net_contributions"]
    totals["variations"] = valuation.get("variations", {})

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "person": PRIMARY_PORTFOLIO_ID,
        "person_name": PRIMARY_PORTFOLIO_NAME,
        "berkshire_mode": berkshire_mode,
        "proxy_mode": proxy_mode,
        "trade_file": source["relative_path"],
        "trade_source": source["kind"],
        "mapping_file": configured_path_label(MAPPINGS_CSV),
        "trade_count": len(trades),
        "asset_count": len(trade_assets),
        "date_range": {
            "start": min(trade.date for trade in trades).isoformat() if trades else None,
            "end": max(trade.date for trade in trades).isoformat() if trades else None,
        },
        "totals": totals,
        "series": summary["series"],
        "valuation_series": valuation["series"],
        "valuation_status": {
            "status": valuation["status"],
            "symbols": valuation.get("symbols", []),
        },
        "positions": priced["positions"],
        "distribution": distribution,
        "dividends": dividend_summary,
        "cash_interests": summarize_cash_interests(read_cash_interests(person)),
        "expenses": expenses,
        "net_contributions": contribution_summary,
        "frictions": frictions,
        "mapping_status": {
            "missing_in_mapping": sorted(assets_without_isin),
            "extra_in_mapping": sorted(mapped_assets - trade_assets),
            "filled_isins": sum(1 for value in mappings.values() if value.get("isin")),
            "total_rows": len(mappings),
        },
        "brokers": all_brokers,
        "stats": calculate_portfolio_statistics(
            trades,
            mappings,
            person=person,
            broker=broker,
            history_context=valuation.get("_history_context", {}),
        ),
    }
    payload["news_symbols"] = news_symbols_from_payload(payload)
    return payload


NEWS_SYMBOL_EXCLUDE = {"", "USD", "EUR", "GBP", "USDC-USD", "BTC-USD", "ETH-USD", "TON-USD", "TON11419-USD"}


def normalize_news_symbol(raw: str) -> str:
    symbol = str(raw or "").strip().upper()
    if not symbol:
        return ""
    symbol = symbol.replace("/", "-")
    if symbol in NEWS_SYMBOL_EXCLUDE or " " in symbol:
        return ""
    if not re.fullmatch(r"[A-Z0-9.-]{1,15}", symbol):
        return ""
    return symbol


def news_symbols_from_payload(payload: dict[str, Any], limit: int = 14) -> list[str]:
    scores: dict[str, Decimal] = {}

    for position in payload.get("positions", []):
        if not position.get("is_open"):
            continue
        if str(position.get("asset_class") or "").lower() == "crypto":
            continue
        isin = str(position.get("isin") or "").upper()
        asset = str(position.get("asset") or "")
        if isin.startswith(("IE", "LU", "NL")) or " acc" in asset.lower() or "etf" in asset.lower():
            continue
        symbol = normalize_news_symbol(position.get("symbol") or "")
        if symbol:
            scores[symbol] = scores.get(symbol, ZERO) + Decimal(str(position.get("market_value_eur") or 0)) + Decimal("1000000")

    for row in payload.get("distribution", {}).get("rows", []):
        symbol = normalize_news_symbol(row.get("holding_ticker") or "")
        if not symbol or symbol.isdigit():
            continue
        scores[symbol] = scores.get(symbol, ZERO) + Decimal(str(row.get("market_value_eur") or 0))

    return [symbol for symbol, _ in sorted(scores.items(), key=lambda item: item[1], reverse=True)[:limit]]


def normalize_news_symbols(symbols: list[str] | tuple[str, ...] | None, limit: int = 14) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in symbols or []:
        symbol = normalize_news_symbol(raw)
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        normalized.append(symbol)
        if len(normalized) >= limit:
            break
    return normalized


def parse_rss_date(raw: str) -> str:
    if not raw:
        return ""
    try:
        parsed = email.utils.parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return raw
    if parsed.tzinfo:
        parsed = parsed.astimezone(timezone.utc)
    return parsed.strftime("%Y-%m-%d %H:%M UTC")


def fetch_symbol_news(symbol: str, limit: int = 6) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({"s": symbol, "region": "US", "lang": "en-US"})
    url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?{query}"
    req = urllib.request.Request(url, headers={"User-Agent": "portfolio-dashboard/1.0"})
    with urllib.request.urlopen(req, timeout=12) as response:
        raw = response.read()

    root = ET.fromstring(raw)
    items: list[dict[str, Any]] = []
    for item in root.findall(".//item")[:limit]:
        title = " ".join((item.findtext("title", default="") or "").split())
        link = (item.findtext("link", default="") or "").strip()
        if not title or not link:
            continue
        items.append(
            {
                "symbol": symbol,
                "title": title,
                "link": link,
                "published": parse_rss_date(item.findtext("pubDate", default="") or ""),
                "source": item.findtext("source", default="") or "Yahoo Finance",
            }
        )
    return items


def portfolio_news_payload(
    person: str = PRIMARY_PORTFOLIO_ID,
    berkshire_mode: str = "stock",
    proxy_mode: str = "on",
    broker: str = "all",
    refresh: bool = False,
    live_only: str = "off",
    symbols: list[str] | None = None,
) -> dict[str, Any]:
    symbols = normalize_news_symbols(symbols)
    if not symbols:
        payload = dashboard_payload(refresh=False, person=person, berkshire_mode=berkshire_mode, proxy_mode=proxy_mode, broker=broker, live_only=live_only)
        symbols = normalize_news_symbols(payload.get("news_symbols") or news_symbols_from_payload(payload))
    cache = get_news_cache()
    cache_key = "|".join([person, berkshire_mode, proxy_mode, broker, live_only, ",".join(symbols)])
    cached = cache.get(cache_key) if isinstance(cache, dict) else None
    now = int(time.time())
    if not refresh and cached and now - int(cached.get("fetched_at_ts", 0)) < NEWS_TTL_SECONDS:
        return cached.get("payload", {})

    rows: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    seen: set[str] = set()
    for symbol in symbols:
        try:
            for item in fetch_symbol_news(symbol):
                dedupe_key = item["link"] or f"{item['symbol']}:{item['title']}"
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                rows.append(item)
        except Exception as exc:
            errors.append({"symbol": symbol, "error": str(exc)})

    rows.sort(key=lambda item: item.get("published") or "", reverse=True)
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "Yahoo Finance RSS",
        "symbols": symbols,
        "count": len(rows),
        "errors": errors,
        "items": rows[:40],
        "status": "available" if rows else "unavailable",
    }
    if isinstance(cache, dict):
        cache[cache_key] = {"fetched_at_ts": now, "payload": result}
        save_json(NEWS_CACHE, cache)
    return result


EXPORT_PERIOD_LABELS = {
    "1w": "Last 1 week",
    "1m": "Last 1 month",
    "ytd": "Year to date",
    "1y": "Last 1 year",
    "since24": "Since Jan 2024",
    "all": "All time",
}


def export_period_label(period: str) -> str:
    return EXPORT_PERIOD_LABELS.get((period or "all").lower(), "All time")


def export_value(value: Any) -> Any:
    if isinstance(value, (str, int, float)) or value is None:
        return value
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=True)
    return str(value)


def export_sheet_name(name: str) -> str:
    clean = re.sub(r"[\[\]\*\?/\\:]", " ", name).strip()[:31]
    return clean or "Sheet"


def export_rows_from_dicts(rows: list[dict[str, Any]], columns: list[tuple[str, str]]) -> list[list[Any]]:
    output = [[label for _, label in columns]]
    for row in rows:
        output.append([export_value(row.get(key)) for key, _ in columns])
    return output


def sorted_by_market_value(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows or [], key=lambda row: float(row.get("market_value_eur") or 0), reverse=True)


def dividend_yearly_export_rows(dividends: dict[str, Any]) -> list[dict[str, Any]]:
    yearly: dict[str, dict[str, Any]] = {}
    for row in dividends.get("rows", []) or []:
        year = str(row.get("date") or "")[:4]
        if not year:
            continue
        bucket = yearly.setdefault(year, {"year": year, "amount_eur": 0.0, "tax_eur": 0.0, "gross_eur": 0.0, "count": 0})
        bucket["amount_eur"] += float(row.get("amount_eur") or 0)
        bucket["tax_eur"] += float(row.get("tax_eur") or 0)
        bucket["gross_eur"] += float(row.get("gross_eur") or 0)
        bucket["count"] += 1
    return [
        {
            "year": year,
            "count": values["count"],
            "amount_eur": round(values["amount_eur"], 2),
            "tax_eur": round(values["tax_eur"], 2),
            "gross_eur": round(values["gross_eur"], 2),
        }
        for year, values in sorted(yearly.items(), reverse=True)
    ]


def add_xlsx_sheet(workbook: Workbook, title: str, rows: list[list[Any]]) -> None:
    ws = workbook.create_sheet(export_sheet_name(title))
    for row in rows:
        ws.append(row)
    for column_cells in ws.columns:
        width = min(42, max(10, max(len(str(cell.value or "")) for cell in column_cells) + 2))
        ws.column_dimensions[column_cells[0].column_letter].width = width
    ws.freeze_panes = "A2"


def dashboard_export_context(
    payload: dict[str, Any],
    person: str,
    berkshire_mode: str,
    proxy_mode: str,
    broker: str,
    live_only: str,
    period: str,
) -> list[list[Any]]:
    totals = payload.get("totals", {})
    date_range = payload.get("date_range", {})
    toggles = [
        f"Person: {payload.get('person_name') or person}",
        f"Window: {export_period_label(period)}",
        f"Broker: {broker}",
        f"Berkshire: {'13F look-through' if berkshire_mode == 'lookthrough' else 'stock'}",
        f"Composition: {'proxy gaps on' if proxy_mode == 'on' else 'official only'}",
        f"Assets: {'live only' if live_only == 'on' else 'all assets'}",
        "Vs MSCI World: shown",
        "Vs inflation: shown",
    ]
    return [
        ["Generated at", payload.get("generated_at")],
        ["Person", payload.get("person_name") or person],
        ["Window", export_period_label(period)],
        ["Broker", broker],
        ["Berkshire mode", berkshire_mode],
        ["Proxy mode", proxy_mode],
        ["Live filter", "Live only" if live_only == "on" else "All assets"],
        ["Vs MSCI World", "Shown"],
        ["Vs inflation", "Shown"],
        ["Toggles", " | ".join(toggles)],
        ["Date range", f"{date_range.get('start') or '-'} to {date_range.get('end') or '-'}"],
        ["Market value EUR", totals.get("market_value")],
        ["Return %", totals.get("return_pct")],
        ["Unrealized P/L EUR", totals.get("unrealized_pl")],
        ["Realized P/L EUR", totals.get("realized_pl")],
        ["Net contributions EUR", totals.get("net_contributions")],
        ["Priced assets", totals.get("priced_assets")],
        ["Unpriced assets", totals.get("unpriced_assets")],
    ]


def export_period_series(series: list[dict[str, Any]], period: str) -> list[dict[str, Any]]:
    if not series:
        return []
    period = (period or "all").lower()
    if period == "all":
        return series
    end = date.fromisoformat(series[-1]["date"])
    if period == "ytd":
        start = date(end.year, 1, 1)
    elif period == "1w":
        start = end - timedelta(days=7)
    elif period == "1m":
        start = end - timedelta(days=30)
    elif period == "1y":
        start = end.replace(year=end.year - 1)
    elif period == "since24":
        start = date(2024, 1, 11)
    else:
        start = date.min
    return [row for row in series if date.fromisoformat(row["date"]) >= start]


def export_period_rows_by_date(rows: list[dict[str, Any]], period: str) -> list[dict[str, Any]]:
    if not rows:
        return []
    period = (period or "all").lower()
    if period == "all":
        return rows
    parsed_dates: list[date] = []
    for row in rows:
        try:
            parsed_dates.append(date.fromisoformat(str(row.get("date") or "")))
        except ValueError:
            continue
    if not parsed_dates:
        return []
    end = max(parsed_dates)
    if period == "ytd":
        start = date(end.year, 1, 1)
    elif period == "1w":
        start = end - timedelta(days=7)
    elif period == "1m":
        start = end - timedelta(days=30)
    elif period == "1y":
        start = end.replace(year=end.year - 1)
    elif period == "since24":
        start = date(2024, 1, 11)
    else:
        start = date.min
    output: list[dict[str, Any]] = []
    for row in rows:
        try:
            row_date = date.fromisoformat(str(row.get("date") or ""))
        except ValueError:
            continue
        if row_date >= start:
            output.append(row)
    return output


def expense_category_export_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    total_outflow = ZERO
    for row in rows:
        amount = Decimal(str(row.get("amount_eur") or 0))
        category = normalize_expense_category(str(row.get("category") or ""))
        bucket = grouped.setdefault(category, {"category": category, "amount_eur": ZERO, "count": 0})
        bucket["amount_eur"] += amount
        bucket["count"] += 1
        if expense_row_kind(row) not in {"income", "credits"}:
            total_outflow += amount
    output = []
    for values in grouped.values():
        amount = values["amount_eur"]
        is_non_outflow = values["category"] in {"Income", "Credits"}
        output.append(
            {
                "category": values["category"],
                "amount_eur": money(amount),
                "count": values["count"],
                "share_pct": float((amount / total_outflow * Decimal("100")).quantize(Decimal("0.01"))) if total_outflow and not is_non_outflow else None,
            }
        )
    return sorted(output, key=lambda item: float(item.get("amount_eur") or 0), reverse=True)


def normalized_return_delta(first: dict[str, Any], last: dict[str, Any], key: str) -> float:
    first_val = float(first.get(key) or 0)
    last_val = float(last.get(key) or 0)
    base = 1 + first_val / 100
    if abs(base) <= 1e-6:
        return 0.0
    return round(((1 + last_val / 100) / base - 1) * 100, 2)


def benchmark_export_rows(payload: dict[str, Any], period: str) -> list[dict[str, Any]]:
    series = export_period_series(payload.get("valuation_series", []) or [], period)
    if not series:
        return []
    first = series[0]
    last = series[-1]
    portfolio = normalized_return_delta(first, last, "return_pct")
    msci = normalized_return_delta(first, last, "msci_return_pct")
    xeon = normalized_return_delta(first, last, "xeon_return_pct")
    inflation = normalized_return_delta(first, last, "inflation_return_pct")
    return [
        {"metric": "Portfolio return", "value_pct": portfolio, "comparison": ""},
        {"metric": "MSCI World return", "value_pct": msci, "comparison": ""},
        {"metric": "XEON return", "value_pct": xeon, "comparison": ""},
        {"metric": "Eurozone inflation", "value_pct": inflation, "comparison": ""},
        {"metric": "Portfolio vs MSCI World", "value_pct": round(portfolio - msci, 2), "comparison": "Outperformance" if portfolio >= msci else "Underperformance"},
        {"metric": "Portfolio vs XEON", "value_pct": round(portfolio - xeon, 2), "comparison": "Outperformance" if portfolio >= xeon else "Underperformance"},
        {"metric": "Portfolio vs inflation", "value_pct": round(portfolio - inflation, 2), "comparison": "Real gain" if portfolio >= inflation else "Real loss"},
    ]


def build_export_tables(payload: dict[str, Any], context_rows: list[list[Any]], period: str) -> dict[str, list[list[Any]]]:
    distribution = payload.get("distribution", {})
    dividends = payload.get("dividends", {})
    contributions = payload.get("net_contributions", {})
    frictions = payload.get("frictions", {})
    expenses = payload.get("expenses", {})
    expense_rows = export_period_rows_by_date(expenses.get("rows", []) or [], period)
    expense_credit_rows = [row for row in expense_rows if expense_row_kind(row) == "credits"]
    return {
        "Overview": [["Field", "Value"], *context_rows],
        "Benchmark Comparison": export_rows_from_dicts(benchmark_export_rows(payload, period), [
            ("metric", "Metric"),
            ("value_pct", "Value %"),
            ("comparison", "Comparison"),
        ]),
        "Holdings": export_rows_from_dicts(sorted_by_market_value(payload.get("positions", [])), [
            ("asset", "Asset"),
            ("asset_type", "Type"),
            ("isin", "ISIN"),
            ("symbol", "Symbol"),
            ("quantity", "Quantity"),
            ("price", "Price"),
            ("price_currency", "Currency"),
            ("market_value_eur", "Market value EUR"),
            ("cost_basis_eur", "Cost EUR"),
            ("display_pl_eur", "P/L EUR"),
            ("display_pl_pct", "P/L %"),
            ("pricing_status", "Status"),
        ]),
        "Distribution": export_rows_from_dicts(distribution.get("underlying", []), [
            ("holding", "Asset"),
            ("holding_ticker", "Ticker"),
            ("market_value_eur", "Value EUR"),
            ("weight_pct", "Weight %"),
        ]),
        "Sectors": export_rows_from_dicts(distribution.get("sectors", []), [
            ("sector", "Sector"),
            ("market_value_eur", "Value EUR"),
            ("weight_pct", "Weight %"),
        ]),
        "Geographies": export_rows_from_dicts(distribution.get("geographies", []), [
            ("geo", "Geo area"),
            ("market_value_eur", "Value EUR"),
            ("weight_pct", "Weight %"),
        ]),
        "Asset Classes": export_rows_from_dicts(distribution.get("asset_classes", []), [
            ("asset_class", "Asset class"),
            ("market_value_eur", "Value EUR"),
            ("weight_pct", "Weight %"),
        ]),
        "Missing Composition": export_rows_from_dicts(distribution.get("missing", []), [
            ("asset", "Asset"),
            ("isin", "ISIN"),
            ("market_value_eur", "Value EUR"),
            ("status", "Status"),
        ]),
        "Dividends Yearly": export_rows_from_dicts(dividend_yearly_export_rows(dividends), [
            ("year", "Year"),
            ("count", "Payments"),
            ("amount_eur", "Net EUR"),
            ("tax_eur", "Tax EUR"),
            ("gross_eur", "Gross EUR"),
        ]),
        "Dividends Payments": export_rows_from_dicts(dividends.get("rows", []), [
            ("date", "Date"),
            ("broker", "Broker"),
            ("asset", "Asset"),
            ("isin", "ISIN"),
            ("amount_eur", "Net EUR"),
            ("tax_eur", "Tax EUR"),
            ("gross_eur", "Gross EUR"),
        ]),
        "Contributions": export_rows_from_dicts(contributions.get("by_date", []), [
            ("date", "Date"),
            ("buys_eur", "Buys EUR"),
            ("sells_eur", "Sells EUR"),
            ("net_eur", "Net EUR"),
        ]),
        "Frictions": export_rows_from_dicts(frictions.get("rows", []), [
            ("date", "Date"),
            ("broker", "Broker"),
            ("type", "Type"),
            ("description", "Description"),
            ("amount_eur", "Amount EUR"),
        ]),
        "Expense Categories": export_rows_from_dicts(expense_category_export_rows(expense_rows), [
            ("category", "Category"),
            ("count", "Rows"),
            ("amount_eur", "Amount EUR"),
            ("share_pct", "Outflow share %"),
        ]),
        "Expense Rows": export_rows_from_dicts(expense_rows, [
            ("date", "Date"),
            ("source_label", "Source"),
            ("merchant", "Merchant"),
            ("description", "Description"),
            ("flow_kind", "Flow kind"),
            ("category", "Category"),
            ("subcategory", "Subcategory"),
            ("amount_eur", "Amount EUR"),
            ("currency", "Currency"),
            ("native_amount", "Native amount"),
            ("confidence", "Confidence"),
        ]),
        "Expense Credits": export_rows_from_dicts(expense_credit_rows, [
            ("date", "Date"),
            ("source_label", "Source"),
            ("merchant", "Merchant"),
            ("description", "Description"),
            ("category", "Category"),
            ("subcategory", "Subcategory"),
            ("amount_eur", "Amount EUR"),
            ("currency", "Currency"),
            ("native_amount", "Native amount"),
        ]),
    }


def build_xlsx_export(tables: dict[str, list[list[Any]]]) -> io.BytesIO:
    workbook = Workbook()
    workbook.remove(workbook.active)
    for title, rows in tables.items():
        add_xlsx_sheet(workbook, title, rows)
    output = io.BytesIO()
    workbook.save(output)
    output.seek(0)
    return output


def build_pdf_export(tables: dict[str, list[list[Any]]], title: str) -> io.BytesIO:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=landscape(A4), rightMargin=24, leftMargin=24, topMargin=24, bottomMargin=24)
    styles = getSampleStyleSheet()
    body = ParagraphStyle("ExportBody", parent=styles["BodyText"], fontSize=7, leading=8.5)
    header = ParagraphStyle("ExportHeader", parent=styles["BodyText"], fontSize=7, leading=8.5, textColor=colors.white, fontName="Helvetica-Bold")
    positive = ParagraphStyle("ExportPositive", parent=body, textColor=colors.HexColor("#047857"), fontName="Helvetica-Bold")
    negative = ParagraphStyle("ExportNegative", parent=body, textColor=colors.HexColor("#B91C1C"), fontName="Helvetica-Bold")
    small = ParagraphStyle("ExportSmall", parent=styles["BodyText"], fontSize=8, leading=10, textColor=colors.HexColor("#4B5563"))
    card_label = ParagraphStyle("ExportCardLabel", parent=styles["BodyText"], fontSize=7, leading=8.5, textColor=colors.HexColor("#6B7280"))
    card_value = ParagraphStyle("ExportCardValue", parent=styles["BodyText"], fontSize=13, leading=15, textColor=colors.HexColor("#111827"), fontName="Helvetica-Bold")

    def text(value: Any) -> str:
        raw = "" if value is None else str(value)
        return raw.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def overview_dict() -> dict[str, Any]:
        rows = tables.get("Overview", [])
        return {str(row[0]): row[1] for row in rows[1:] if len(row) >= 2}

    def is_positive_negative_column(label: str) -> bool:
        label_l = label.lower()
        return any(token in label_l for token in ["p/l", "return", "net eur", "amount eur"])

    def numeric_value(value: Any) -> float | None:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            cleaned = re.sub(r"[^0-9.\-]", "", value)
            if cleaned and cleaned not in {"-", ".", "-."}:
                try:
                    return float(cleaned)
                except ValueError:
                    return None
        return None

    def table_for(section: str, rows: list[list[Any]]) -> Table | None:
        if not rows:
            return None
        headers = [str(item) for item in rows[0]]
        data_rows = rows[1:]
        if not data_rows:
            data_rows = [["No data available for this selection.", *["" for _ in headers[1:]]]]
        display_rows = [headers, *data_rows[:30]]
        if section in {"Holdings", "Distribution"} and display_rows and headers and headers[0] == "Asset":
            display_rows = [display_rows[0], *[[asset_cell_html(row), *row[1:]] for row in display_rows[1:]]]
        cell_rows = []
        for ridx, row in enumerate(display_rows):
            cells = []
            for cidx, cell in enumerate(row):
                style = header if ridx == 0 else body
                if ridx > 0 and is_positive_negative_column(headers[cidx]):
                    value = numeric_value(cell)
                    if value is not None and value > 0:
                        style = positive
                    elif value is not None and value < 0:
                        style = negative
                rendered = str(cell) if ridx > 0 and section in {"Holdings", "Distribution"} and cidx == 0 else text(cell)
                cells.append(Paragraph(rendered, style))
            cell_rows.append(cells)
        table = Table(cell_rows, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D1D5DB")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]))
        for cidx, label in enumerate(headers):
            if is_positive_negative_column(label):
                for ridx, row in enumerate(display_rows[1:], start=1):
                    value = numeric_value(row[cidx]) if cidx < len(row) else None
                    if value is None or value == 0:
                        continue
                    table.setStyle(TableStyle([("TEXTCOLOR", (cidx, ridx), (cidx, ridx), colors.HexColor("#047857" if value > 0 else "#B91C1C"))]))
        return table

    def asset_cell_html(row: list[Any]) -> str:
        ticker = ""
        if len(row) > 3 and str(row[3] or "").strip():
            ticker = str(row[3]).strip()
        elif len(row) > 1 and str(row[1] or "").strip():
            ticker = str(row[1]).strip()
        source = ticker or (str(row[0]) if row else "")
        letters = re.sub(r"[^A-Za-z0-9]", "", source.upper())[:3]
        badge = letters or "ETF"
        asset = text(row[0] if row else "")
        return f'<font color="#2563EB"><b>[{text(badge)}]</b></font> {asset}'

    overview = overview_dict()
    card_fields = [
        ("Market value EUR", overview.get("Market value EUR")),
        ("Return %", overview.get("Return %")),
        ("Unrealized P/L EUR", overview.get("Unrealized P/L EUR")),
        ("Net contributions EUR", overview.get("Net contributions EUR")),
    ]
    story = [Paragraph(title, styles["Title"]), Spacer(1, 8)]
    story.append(Paragraph(f"Generated at {text(overview.get('Generated at', '-'))}", small))
    story.append(Spacer(1, 12))
    cards = Table([[
        [Paragraph(text(label), card_label), Paragraph(text(value), card_value)]
        for label, value in card_fields
    ]], colWidths=[doc.width / 4 - 8] * 4)
    cards.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F3F4F6")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.white),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(cards)
    story.append(Spacer(1, 14))
    toggles = [
        ["Person", overview.get("Person")],
        ["Window", overview.get("Window")],
        ["Broker", overview.get("Broker")],
        ["Berkshire", overview.get("Berkshire mode")],
        ["Composition", overview.get("Proxy mode")],
        ["Assets", overview.get("Live filter")],
        ["Vs MSCI World", overview.get("Vs MSCI World")],
        ["Vs inflation", overview.get("Vs inflation")],
    ]
    toggle_table = Table([[Paragraph(text(k), header), Paragraph(text(v), body)] for k, v in toggles], colWidths=[90, 220])
    toggle_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#111827")),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.white),
        ("BACKGROUND", (1, 0), (1, -1), colors.HexColor("#EEF2FF")),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(Paragraph("Active dashboard toggles", styles["Heading2"]))
    story.append(toggle_table)
    story.append(Spacer(1, 12))
    overview_table = table_for("Overview", tables.get("Overview", []))
    if overview_table:
        story.append(Paragraph("Report overview", styles["Heading2"]))
        story.append(overview_table)

    for section, rows in tables.items():
        if section == "Overview":
            continue
        story.append(PageBreak())
        story.append(Paragraph(section, styles["Heading1"]))
        story.append(Spacer(1, 8))
        table = table_for(section, rows)
        if table:
            story.append(table)
        if len(rows) > 31:
            story.append(Spacer(1, 6))
            story.append(Paragraph(f"Showing first 30 rows of {len(rows) - 1}. Use XLSX for the full table.", styles["Italic"]))
    doc.build(story)
    output.seek(0)
    return output


def export_filename(person: str, period: str, fmt: str) -> str:
    safe_person = re.sub(r"[^A-Za-z0-9_-]+", "-", person or "portfolio").strip("-").lower()
    safe_period = re.sub(r"[^A-Za-z0-9_-]+", "-", period or "all").strip("-").lower()
    return f"portfolio-{safe_person}-{safe_period}-{date.today().isoformat()}.{fmt}"


# ─── Watchlist Feature ───
WATCHLIST_FILE = SETTINGS.data_path("watchlist.json")
WATCHLIST_CACHE_FILE = SETTINGS.cache_path("watchlist.json")

KNOWN_ISINS = {
    "IWQU.L": "IE00BP3QZ601",
    "FUSD.L": "IE00BYXV8M31",
    "TDIV.AS": "NL0011683594",
    "TDIV.L": "NL0011683594",
}

def get_watchlist_tickers() -> list[str]:
    if not WATCHLIST_FILE.exists():
        default_list = ["IWQU.L", "FUSD.L"]
        WATCHLIST_FILE.parent.mkdir(parents=True, exist_ok=True)
        try:
            save_json(WATCHLIST_FILE, default_list)
        except Exception:
            pass
        return default_list
    try:
        with open(WATCHLIST_FILE, "r") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
    except Exception:
        pass
    return ["IWQU.L", "FUSD.L"]

def fetch_ticker_quote(symbol: str) -> dict[str, Any]:
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="2d")
        if hist.empty:
            return {"ticker": symbol, "error": "No historical data found"}
        
        closes = hist["Close"].dropna().tolist()
        if not closes:
            return {"ticker": symbol, "error": "No Close prices available"}
            
        current_price = closes[-1]
        prev_close = closes[-2] if len(closes) > 1 else current_price
        change = current_price - prev_close
        change_pct = (change / prev_close * 100) if prev_close > 0 else 0.0
        
        try:
            info = ticker.fast_info
            currency = normalize_currency_code(fast_info_value(info, "currency") or infer_currency(symbol))
        except Exception:
            currency = infer_currency(symbol)
            
        long_name = symbol
        try:
            long_name = ticker.info.get("longName") or ticker.info.get("shortName") or symbol
        except Exception:
            pass
            
        isin = KNOWN_ISINS.get(symbol.upper())
        just_etf_url = f"https://www.justetf.com/en/etf-profile.html?isin={isin}" if isin else f"https://www.justetf.com/en/find-etf.html?query={symbol.split('.')[0]}"
        
        return {
            "ticker": symbol,
            "name": long_name,
            "price": round(float(current_price), 3),
            "prev_close": round(float(prev_close), 3),
            "change": round(float(change), 3),
            "change_pct": round(float(change_pct), 2),
            "currency": currency,
            "yfinance_url": f"https://finance.yahoo.com/quote/{symbol}",
            "justetf_url": just_etf_url,
        }
    except Exception as e:
        return {"ticker": symbol, "error": str(e)}

def fetch_watchlist_data(refresh: bool = False) -> list[dict[str, Any]]:
    tickers = get_watchlist_tickers()
    now = int(time.time())
    cache = {}
    if WATCHLIST_CACHE_FILE.exists() and not refresh:
        try:
            with open(WATCHLIST_CACHE_FILE, "r") as f:
                cache = json.load(f)
        except Exception:
            pass

    results = []
    cache_dirty = False
    for ticker in tickers:
        cached_item = cache.get(ticker)
        if cached_item and now - cached_item.get("fetched_at", 0) < 900:
            results.append(cached_item["data"])
        else:
            data = fetch_ticker_quote(ticker)
            results.append(data)
            cache[ticker] = {"fetched_at": now, "data": data}
            cache_dirty = True

    if cache_dirty:
        try:
            save_json(WATCHLIST_CACHE_FILE, cache)
        except Exception:
            pass
    return results

@app.get("/api/watchlist")
def api_get_watchlist():
    refresh = request.args.get("refresh", "false").lower() == "true"
    try:
        data = fetch_watchlist_data(refresh=refresh)
        return jsonify({"watchlist": data})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.post("/api/watchlist")
def api_modify_watchlist():
    payload = request.get_json() or {}
    ticker = str(payload.get("ticker", "")).strip().upper()
    action = str(payload.get("action", "")).strip().lower()
    if not ticker:
        return jsonify({"error": "Ticker is required"}), 400
    
    tickers = get_watchlist_tickers()
    if action == "add":
        if ticker not in tickers:
            tickers.append(ticker)
    elif action == "remove":
        if ticker in tickers:
            tickers.remove(ticker)
    else:
        return jsonify({"error": "Invalid action, must be 'add' or 'remove'"}), 400
        
    try:
        save_json(WATCHLIST_FILE, tickers)
        if WATCHLIST_CACHE_FILE.exists():
            try:
                with open(WATCHLIST_CACHE_FILE, "r") as f:
                    cache = json.load(f)
                if ticker in cache:
                    del cache[ticker]
                save_json(WATCHLIST_CACHE_FILE, cache)
            except Exception:
                pass
        return jsonify({"status": "success", "tickers": tickers, "watchlist": fetch_watchlist_data(refresh=True)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.get("/api/portfolio")
def api_portfolio():
    refresh = request.args.get("refresh") == "1"
    person = request.args.get("person", PRIMARY_PORTFOLIO_ID)
    berkshire_mode = request.args.get("berkshire", "stock")
    proxy_mode = request.args.get("proxy", "on")
    broker = request.args.get("broker", "all")
    live_only = request.args.get("live_only", "off")
    try:
        return jsonify(dashboard_payload(refresh=refresh, person=person, berkshire_mode=berkshire_mode, proxy_mode=proxy_mode, broker=broker, live_only=live_only))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.get("/api/news")
def api_news():
    refresh = request.args.get("refresh") == "1"
    person = request.args.get("person", PRIMARY_PORTFOLIO_ID)
    berkshire_mode = request.args.get("berkshire", "stock")
    proxy_mode = request.args.get("proxy", "on")
    broker = request.args.get("broker", "all")
    live_only = request.args.get("live_only", "off")
    raw_symbols = request.args.get("symbols", "")
    symbols = [item for item in raw_symbols.split(",") if item] if raw_symbols else None
    try:
        return jsonify(
            portfolio_news_payload(
                person=person,
                berkshire_mode=berkshire_mode,
                proxy_mode=proxy_mode,
                broker=broker,
                refresh=refresh,
                live_only=live_only,
                symbols=symbols,
            )
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

@app.get("/api/rankings")
def api_rankings():
    refresh = request.args.get("refresh") == "1"
    berkshire_mode = request.args.get("berkshire", "stock")
    proxy_mode = request.args.get("proxy", "on")
    broker = request.args.get("broker", "all")
    live_only = request.args.get("live_only", "off")
    try:
        users = [PRIMARY_PORTFOLIO_ID] + list(FAMILY_PORTFOLIOS.keys())
        user_series = {}
        for user in users:
            payload = dashboard_payload(
                refresh=refresh,
                person=user,
                berkshire_mode=berkshire_mode,
                proxy_mode=proxy_mode,
                broker=broker,
                live_only=live_only
            )
            user_series[user] = payload.get("valuation_series", [])
            
        start_dates = {}
        for user, series in user_series.items():
            if series:
                start_dates[user] = series[0]["date"]
                
        common_start_date = None
        if start_dates:
            common_start_date = max(start_dates.values())
            
        current_year_start = f"{datetime.now().year}-01-01"
        
        rankings = []
        for user in users:
            series = user_series[user]
            if not series:
                rankings.append({
                    "person": user,
                    "name": FAMILY_PORTFOLIOS.get(user, {}).get("name", user.capitalize()),
                    "start_date": None,
                    "returns": {
                        "price": {"start": 0.0, "common": 0.0, "ytd": 0.0},
                        "total": {"start": 0.0, "common": 0.0, "ytd": 0.0}
                    }
                })
                continue
                
            p_first = series[0]
            p_last = series[-1]
            
            def find_point_on_or_after(target_date):
                for p in series:
                    if p["date"] >= target_date:
                        return p
                return series[-1]
                
            p_common = find_point_on_or_after(common_start_date) if common_start_date else p_first
            p_ytd = find_point_on_or_after(current_year_start)
            
            def point_number(point, key):
                try:
                    return float(point.get(key) or 0.0)
                except (TypeError, ValueError):
                    return 0.0

            def calc_period_return(p_t, p_0, total=False):
                profit_key = "total_profit" if total else "profit"
                contrib_key = "total_net_contributions" if total else "net_contributions"
                value_key = "total_market_value" if total else "market_value"
                period_profit = point_number(p_t, profit_key) - point_number(p_0, profit_key)
                period_contributions = point_number(p_t, contrib_key) - point_number(p_0, contrib_key)
                start_value = point_number(p_0, value_key)
                capital_at_work = max(0.01, start_value + max(0.0, period_contributions))
                return round(period_profit / capital_at_work * 100.0, 2)
                
            ret_start_price = calc_period_return(p_last, p_first, total=False)
            ret_start_total = calc_period_return(p_last, p_first, total=True)
            
            ret_common_price = calc_period_return(p_last, p_common, total=False)
            ret_common_total = calc_period_return(p_last, p_common, total=True)
            
            ret_ytd_price = calc_period_return(p_last, p_ytd, total=False)
            ret_ytd_total = calc_period_return(p_last, p_ytd, total=True)
            
            rankings.append({
                "person": user,
                "name": FAMILY_PORTFOLIOS.get(user, {}).get("name", user.capitalize()),
                "start_date": p_first["date"],
                "returns": {
                    "price": {
                        "start": ret_start_price,
                        "common": ret_common_price,
                        "ytd": ret_ytd_price
                    },
                    "total": {
                        "start": ret_start_total,
                        "common": ret_common_total,
                        "ytd": ret_ytd_total
                    }
                }
            })
            
        return jsonify({
            "common_start_date": common_start_date,
            "ytd_start_date": current_year_start,
            "rankings": rankings
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.get("/api/export")
def api_export():
    fmt = (request.args.get("format") or "xlsx").strip().lower()
    if fmt not in {"xlsx", "pdf"}:
        return jsonify({"error": "Unsupported export format. Use xlsx or pdf."}), 400
    person = request.args.get("person", PRIMARY_PORTFOLIO_ID)
    berkshire_mode = normalize_berkshire_mode(request.args.get("berkshire", "stock"))
    proxy_mode = normalize_proxy_mode(request.args.get("proxy", "on"))
    broker = request.args.get("broker", "all")
    live_only = request.args.get("live_only", "off")
    period = (request.args.get("period") or "all").lower()
    try:
        payload = dashboard_payload(
            refresh=False,
            person=person,
            berkshire_mode=berkshire_mode,
            proxy_mode=proxy_mode,
            broker=broker,
            live_only=live_only,
        )
        context_rows = dashboard_export_context(payload, person, berkshire_mode, proxy_mode, broker, live_only, period)
        tables = build_export_tables(payload, context_rows, period)
        filename = export_filename(person, period, fmt)
        if fmt == "xlsx":
            output = build_xlsx_export(tables)
            return send_file(output, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", as_attachment=True, download_name=filename)
        output = build_pdf_export(tables, f"Portfolio Report - {payload.get('person_name') or person} - {export_period_label(period)}")
        return send_file(output, mimetype="application/pdf", as_attachment=True, download_name=filename)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.get("/")
def index():
    profiles = [(PRIMARY_PORTFOLIO_ID, PRIMARY_PORTFOLIO_NAME)] + [
        (portfolio_id, profile.display_name)
        for portfolio_id, profile in SETTINGS.portfolios.items()
        if portfolio_id.lower() != PRIMARY_PORTFOLIO_ID
    ]
    icon = '<svg viewBox="0 0 24 24"><path d="M20 21a8 8 0 0 0-16 0"/><circle cx="12" cy="7" r="4"/></svg>'
    buttons = []
    for index, (portfolio_id, display_name) in enumerate(profiles):
        active = ' class="active"' if index == 0 else ""
        safe_id = html.escape(portfolio_id, quote=True)
        safe_name = html.escape(display_name, quote=True)
        buttons.append(
            f'<button type="button" data-person="{safe_id}" data-label="{safe_name}"{active}>'
            f'<span class="user-avatar" aria-hidden="true">{icon}</span>'
            f'<span class="selector-label">{safe_name}</span></button>'
        )
    return HTML.replace("<!-- PORTFOLIO_BUTTONS -->", "".join(buttons)).replace(
        "__PRIMARY_PORTFOLIO_ID__", json.dumps(PRIMARY_PORTFOLIO_ID)
    )


HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Portfolio Dashboard</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #0c0f1a;
      --bg-secondary: #111827;
      --panel: rgba(17, 24, 39, 0.7);
      --panel-solid: #111827;
      --panel-hover: rgba(30, 41, 59, 0.8);
      --glass: rgba(255, 255, 255, 0.03);
      --ink: #f1f5f9;
      --ink-secondary: #cbd5e1;
      --muted: #64748b;
      --line: rgba(148, 163, 184, 0.12);
      --line-strong: rgba(148, 163, 184, 0.2);
      --blue: #60a5fa;
      --blue-dim: rgba(96, 165, 250, 0.15);
      --green: #34d399;
      --green-dim: rgba(52, 211, 153, 0.12);
      --red: #f87171;
      --red-dim: rgba(248, 113, 113, 0.12);
      --amber: #fbbf24;
      --amber-dim: rgba(251, 191, 36, 0.12);
      --teal: #2dd4bf;
      --violet: #a78bfa;
      --violet-dim: rgba(167, 139, 250, 0.12);
      --cyan: #22d3ee;
      --pink: #f472b6;
      --pink-dim: rgba(244, 114, 182, 0.12);
      --gradient-1: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      --gradient-2: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
      --gradient-3: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
      --gradient-accent: linear-gradient(135deg, #60a5fa 0%, #a78bfa 50%, #f472b6 100%);
      --shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3), 0 2px 4px -2px rgba(0, 0, 0, 0.2);
      --shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.4), 0 4px 6px -4px rgba(0, 0, 0, 0.3);
      --shadow-glow: 0 0 20px rgba(96, 165, 250, 0.15);
      --radius: 14px;
      --radius-sm: 10px;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Inter', ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: var(--bg);
      min-height: 100vh;
      -webkit-font-smoothing: antialiased;
      -moz-osx-font-smoothing: grayscale;
    }

    /* ─── Scrollbar ─── */
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: rgba(148,163,184,0.2); border-radius: 999px; }
    ::-webkit-scrollbar-thumb:hover { background: rgba(148,163,184,0.35); }

    /* ─── Header ─── */
    header {
      display: flex;
      justify-content: space-between;
      gap: 18px;
      align-items: center;
      padding: 14px 32px;
      background:
        linear-gradient(180deg, rgba(17,24,39,0.94), rgba(15,23,42,0.82)),
        linear-gradient(90deg, rgba(96,165,250,0.10), rgba(45,212,191,0.06), rgba(244,114,182,0.07));
      backdrop-filter: blur(24px) saturate(180%);
      -webkit-backdrop-filter: blur(24px) saturate(180%);
      border-bottom: 1px solid rgba(148,163,184,0.14);
      position: sticky;
      top: 0;
      z-index: 100;
      box-shadow: 0 12px 34px rgba(0,0,0,0.24), inset 0 1px 0 rgba(255,255,255,0.04);
    }
    header::after {
      content: "";
      position: absolute;
      left: 32px;
      right: 32px;
      bottom: -1px;
      height: 1px;
      background: linear-gradient(90deg, transparent, rgba(96,165,250,0.42), rgba(45,212,191,0.28), transparent);
      pointer-events: none;
    }
    .topbar-brand {
      min-width: 0;
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .brand-mark {
      width: 42px;
      height: 42px;
      min-width: 42px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border-radius: 12px;
      border: 1px solid rgba(255,255,255,0.13);
      color: #fff;
      background:
        linear-gradient(135deg, rgba(96,165,250,0.50), rgba(45,212,191,0.35)),
        rgba(15,23,42,0.74);
      box-shadow: 0 10px 24px rgba(0,0,0,0.22), inset 0 1px 0 rgba(255,255,255,0.12);
    }
    .brand-mark svg {
      width: 23px;
      height: 23px;
      stroke: currentColor;
      stroke-width: 2;
      fill: none;
    }
    .topbar-copy {
      min-width: 0;
      display: grid;
      gap: 5px;
    }
    h1 {
      font-size: 22px;
      font-weight: 800;
      letter-spacing: 0;
      line-height: 1.05;
      color: var(--ink);
    }
    .meta {
      width: fit-content;
      max-width: min(58vw, 760px);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      color: var(--ink-secondary);
      border: 1px solid rgba(148,163,184,0.12);
      border-radius: 999px;
      padding: 4px 10px;
      background: rgba(15,23,42,0.54);
      font-size: 12px;
      font-weight: 500;
      line-height: 1.2;
    }
    .topbar-actions {
      display: flex;
      align-items: center;
      gap: 10px;
      margin-left: auto;
    }

    /* ─── Buttons ─── */
    button {
      border: 1px solid var(--line-strong);
      background: var(--panel);
      color: var(--ink-secondary);
      border-radius: 8px;
      padding: 8px 16px;
      font-size: 13px;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.2s ease;
      font-family: inherit;
    }
    button:hover {
      background: var(--panel-hover);
      border-color: var(--blue);
      color: var(--ink);
      box-shadow: var(--shadow-glow);
    }
    button:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }
    #refresh {
      min-width: 146px;
      min-height: 42px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 9px;
      padding: 9px 15px 9px 12px;
      color: var(--ink);
      background:
        linear-gradient(135deg, rgba(96,165,250,0.22), rgba(45,212,191,0.12)),
        rgba(15,23,42,0.58);
      border-color: rgba(96,165,250,0.32);
      box-shadow: 0 10px 24px rgba(0,0,0,0.18), inset 0 1px 0 rgba(255,255,255,0.06);
    }
    #refresh:hover {
      background:
        linear-gradient(135deg, rgba(96,165,250,0.30), rgba(45,212,191,0.20)),
        rgba(15,23,42,0.72);
      border-color: rgba(45,212,191,0.42);
      transform: translateY(-1px);
    }
    .refresh-button-icon {
      width: 22px;
      height: 22px;
      min-width: 22px;
      border-radius: 999px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      color: #fff;
      background: rgba(255,255,255,0.08);
    }
    .refresh-button-icon svg {
      width: 14px;
      height: 14px;
      stroke: currentColor;
      stroke-width: 2.2;
      fill: none;
    }
    body.dashboard-refreshing #refresh .refresh-button-icon {
      animation: refresh-spin 0.85s linear infinite;
    }

    /* ─── Pill selector (persons + periods) ─── */
    .control-stack {
      display: grid;
      gap: 10px;
    }
    .control-row {
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      align-items: center;
    }
    .primary-controls {
      align-items: stretch;
    }
    .secondary-controls {
      gap: 8px;
      align-items: center;
      opacity: 0.82;
    }
    .secondary-label {
      color: var(--muted);
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 0.08em;
      line-height: 1;
      text-transform: uppercase;
    }
    .periods {
      display: inline-flex;
      gap: 2px;
      align-items: center;
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 3px;
      background: rgba(15, 23, 42, 0.6);
      backdrop-filter: blur(8px);
    }
    .periods button {
      min-width: 50px;
      padding: 6px 12px;
      border: 0;
      border-radius: 8px;
      background: transparent;
      font-size: 12px;
      font-weight: 500;
      color: var(--muted);
      transition: all 0.25s ease;
    }
    .periods button:hover {
      color: var(--ink-secondary);
      background: rgba(255,255,255,0.04);
      box-shadow: none;
    }
    .periods button.active {
      background: linear-gradient(135deg, rgba(96,165,250,0.2), rgba(167,139,250,0.2));
      color: var(--ink);
      box-shadow: 0 1px 3px rgba(0,0,0,0.2);
    }
    .secondary-selector {
      padding: 2px;
      border-color: rgba(148,163,184,0.10);
      background: rgba(15,23,42,0.34);
      backdrop-filter: blur(6px);
    }
    .secondary-selector button {
      min-width: 0;
      min-height: 28px;
      padding: 4px 9px;
      border-radius: 7px;
      color: rgba(148,163,184,0.82);
      font-size: 11px;
      font-weight: 500;
    }
    .secondary-selector button:hover {
      color: var(--ink-secondary);
      background: rgba(255,255,255,0.035);
    }
    .secondary-selector button.active {
      color: var(--ink-secondary);
      background: rgba(96,165,250,0.10);
      box-shadow: none;
    }
    .selector-fancy {
      gap: 4px;
      padding: 4px;
      border-color: rgba(96,165,250,0.22);
      background:
        linear-gradient(135deg, rgba(15,23,42,0.84), rgba(30,41,59,0.62)),
        linear-gradient(90deg, rgba(96,165,250,0.10), rgba(45,212,191,0.08));
      box-shadow: inset 0 1px 0 rgba(255,255,255,0.04), 0 8px 24px rgba(0,0,0,0.16);
    }
    .selector-fancy button {
      min-width: 0;
      min-height: 36px;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 5px 11px 5px 6px;
      color: var(--ink-secondary);
      white-space: nowrap;
    }
    .selector-fancy button.active {
      background: linear-gradient(135deg, rgba(96,165,250,0.24), rgba(45,212,191,0.15));
      box-shadow: 0 8px 20px rgba(0,0,0,0.2), inset 0 1px 0 rgba(255,255,255,0.06);
    }
    .selector-fancy button.active .user-avatar,
    .selector-fancy button.active .broker-logo,
    .selector-fancy button.active .time-icon {
      transform: scale(1.03);
      border-color: rgba(255,255,255,0.28);
      box-shadow: 0 0 0 1px rgba(96,165,250,0.20), 0 8px 18px rgba(0,0,0,0.22);
    }
    .selector-label {
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .person-selector .selector-label { max-width: 90px; }
    .broker-selector .selector-label { max-width: 150px; }
    .time-selector button {
      width: var(--time-width, 64px);
      min-height: 40px;
      flex-direction: column;
      align-items: stretch;
      justify-content: center;
      gap: 5px;
      padding: 5px 8px;
    }
    .time-main {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
    }
    .time-icon {
      width: 18px;
      height: 18px;
      min-width: 18px;
      border-radius: 999px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border: 1px solid rgba(255,255,255,0.12);
      color: var(--ink-secondary);
      background: linear-gradient(135deg, rgba(96,165,250,0.18), rgba(45,212,191,0.12));
      transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
    }
    .time-icon svg {
      width: 12px;
      height: 12px;
      stroke: currentColor;
      stroke-width: 2;
      fill: none;
    }
    .time-scale {
      height: 3px;
      width: 100%;
      overflow: hidden;
      border-radius: 999px;
      background: rgba(148,163,184,0.12);
    }
    .time-scale span {
      display: block;
      height: 100%;
      width: 100%;
      border-radius: inherit;
      background: linear-gradient(90deg, var(--blue), var(--teal));
      transform: scaleX(var(--time-fill, 0.2));
      transform-origin: left center;
      opacity: 0.7;
    }
    .time-selector button.active .time-icon {
      color: #fff;
      background: linear-gradient(135deg, rgba(96,165,250,0.55), rgba(45,212,191,0.38));
    }
    .time-selector button.active .time-scale span {
      opacity: 1;
      box-shadow: 0 0 12px rgba(45,212,191,0.28);
    }
    .user-avatar,
    .broker-logo {
      width: 24px;
      height: 24px;
      min-width: 24px;
      border-radius: 8px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border: 1px solid rgba(255,255,255,0.12);
      color: #fff;
      transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
      overflow: hidden;
    }
    .user-avatar svg,
    .broker-logo svg {
      width: 14px;
      height: 14px;
      stroke: currentColor;
      stroke-width: 2;
      fill: none;
    }
    .person-selector button:nth-child(5n + 1) .user-avatar { background: linear-gradient(135deg, #2563eb, #14b8a6); }
    .person-selector button:nth-child(5n + 2) .user-avatar { background: linear-gradient(135deg, #059669, #84cc16); }
    .person-selector button:nth-child(5n + 3) .user-avatar { background: linear-gradient(135deg, #db2777, #f97316); }
    .person-selector button:nth-child(5n + 4) .user-avatar { background: linear-gradient(135deg, #7c3aed, #06b6d4); }
    .person-selector button:nth-child(5n) .user-avatar { background: linear-gradient(135deg, #475569, #f59e0b); }
    .broker-logo {
      font-size: 10px;
      font-weight: 800;
      line-height: 1;
      letter-spacing: 0;
    }
    .broker-logo.all { background: linear-gradient(135deg, #475569, #0f172a); }
    .broker-logo.fineco { background: #facc15; color: #111827; }
    .broker-logo.interactive-brokers { background: linear-gradient(135deg, #ef4444, #111827); }
    .broker-logo.trade-republic { background: #ffffff; color: #111827; }
    .broker-logo.etoro { background: #16a34a; color: #ffffff; }
    .broker-logo.crypto-wallet { background: linear-gradient(135deg, #f59e0b, #0ea5e9); color: #ffffff; }
    .broker-logo.bbva { background: #1455d9; color: #ffffff; }
    .broker-logo.mediolanum { background: linear-gradient(135deg, #1d4ed8, #facc15); color: #ffffff; }
    .broker-logo.manual { background: linear-gradient(135deg, #64748b, #334155); color: #ffffff; }

    /* ─── Main layout ─── */
    main {
      padding: 24px 32px 48px;
      display: grid;
      gap: 32px;
      max-width: none;
      margin: 0 auto;
      width: 100%;
      transition: filter 0.28s ease, opacity 0.28s ease, transform 0.28s ease;
    }
    main > :not(.dashboard-refresh-overlay) {
      transition: opacity 0.24s ease, filter 0.24s ease, transform 0.24s ease;
    }

    /* ─── Metric Cards ─── */
    .metrics {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
      gap: 12px;
    }
    .metric.clickable {
      cursor: pointer;
      user-select: none;
    }
    .metric.clickable:hover {
      border-color: rgba(96, 165, 250, 0.4) !important;
      box-shadow: var(--shadow-glow), var(--shadow-lg) !important;
    }
    .metric-label-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 8px;
    }
    .metric-label-row span { min-width: 0; }
    .metric-plus {
      width: 24px;
      height: 24px;
      min-width: 24px;
      padding: 0;
      border-radius: 999px;
      border: 1px solid rgba(96, 165, 250, 0.35);
      background: rgba(96, 165, 250, 0.12);
      color: var(--ink);
      font-size: 15px;
      line-height: 22px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
    }
    .metric-plus:hover,
    .metric-plus.active {
      background: rgba(96, 165, 250, 0.24);
      border-color: rgba(96, 165, 250, 0.7);
      box-shadow: var(--shadow-glow);
    }
    .metric {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      padding: 16px 18px;
      box-shadow: var(--shadow);
      min-height: 90px;
      position: relative;
      overflow: hidden;
      transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
      backdrop-filter: blur(12px);
    }
    .metric::before {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: 2px;
      background: var(--gradient-accent);
      opacity: 0;
      transition: opacity 0.2s ease;
    }
    .metric:hover {
      transform: translateY(-2px);
      box-shadow: var(--shadow-lg);
      border-color: rgba(148,163,184,0.2);
    }
    .metric:hover::before { opacity: 1; }
    .metric span {
      display: block;
      color: var(--muted);
      font-size: 11px;
      font-weight: 500;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      line-height: 1.25;
    }
    .metric strong {
      display: block;
      margin-top: 10px;
      font-size: 22px;
      font-weight: 700;
      line-height: 1.1;
      letter-spacing: -0.02em;
      overflow-wrap: anywhere;
    }
    .metric-benchmark {
      margin-top: 8px;
      display: flex;
      align-items: center;
      gap: 6px;
      flex-wrap: wrap;
      color: var(--muted);
      font-size: 11px;
      font-weight: 600;
      line-height: 1.2;
    }
    .metric-benchmark .positive { color: var(--green); }
    .metric-benchmark .negative { color: var(--red); }
    .movers-panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      padding: 16px 18px;
      box-shadow: var(--shadow);
    }
    .movers-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      margin-bottom: 12px;
    }
    .movers-head strong {
      font-size: 14px;
      font-weight: 700;
    }
    .movers-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }
    .movers-column h3 {
      color: var(--muted);
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      margin-bottom: 8px;
    }
    .mover-row {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto auto;
      gap: 10px;
      align-items: center;
      padding: 8px 0;
      border-top: 1px solid rgba(255,255,255,0.04);
      font-size: 12px;
    }
    .mover-name {
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      color: var(--ink-secondary);
    }
    .mover-pill {
      justify-self: start;
      color: var(--muted);
      background: rgba(148, 163, 184, 0.1);
      border: 1px solid rgba(148, 163, 184, 0.18);
      border-radius: 999px;
      padding: 2px 7px;
      font-size: 10px;
      font-weight: 700;
      text-transform: uppercase;
    }
    .mover-values {
      display: flex;
      flex-direction: column;
      align-items: flex-end;
      gap: 2px;
      white-space: nowrap;
    }
    .mover-values small {
      color: var(--muted);
      font-size: 10px;
    }
    .export-panel {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 16px;
      position: relative;
      background:
        linear-gradient(180deg, rgba(17,24,39,0.70), rgba(15,23,42,0.58)),
        linear-gradient(90deg, rgba(96,165,250,0.08), transparent 42%);
      border: 1px solid rgba(96,165,250,0.18);
      border-radius: var(--radius);
      padding: 16px 18px;
      box-shadow: var(--shadow);
      overflow: hidden;
      --section-accent: var(--blue);
      --section-accent-soft: rgba(96,165,250,0.10);
    }
    .export-panel::before {
      content: "";
      position: absolute;
      left: 0;
      top: 0;
      bottom: 0;
      width: 3px;
      background: var(--section-accent);
      opacity: 0.58;
    }
    .export-copy {
      display: flex;
      align-items: center;
      gap: 10px;
      min-width: 0;
    }
    .export-copy-text {
      min-width: 0;
      display: grid;
      gap: 4px;
    }
    .export-copy strong {
      font-size: 14px;
      font-weight: 700;
    }
    .export-actions {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }
    .export-actions select {
      border: 1px solid var(--line-strong);
      background: rgba(15, 23, 42, 0.8);
      color: var(--ink-secondary);
      border-radius: 8px;
      padding: 8px 12px;
      font-size: 13px;
      font-family: inherit;
    }
    #export-button {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      min-height: 38px;
      border-color: rgba(96,165,250,0.28);
      background: rgba(96,165,250,0.12);
      color: var(--ink);
    }
    #export-button svg {
      width: 15px;
      height: 15px;
      stroke: currentColor;
      stroke-width: 2;
      fill: none;
    }

    /* ─── Info Box ─── */
    .info-box {
      background: rgba(30, 41, 59, 0.5);
      border: 1px solid var(--line);
      border-radius: var(--radius-sm);
      padding: 14px 16px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.6;
    }
    .info-box strong {
      color: var(--ink-secondary);
      font-weight: 600;
    }

    /* ─── Sections (Collapsible) ─── */
    section {
      min-width: 0;
      position: relative;
      background:
        linear-gradient(180deg, rgba(17,24,39,0.70), rgba(15,23,42,0.62)),
        var(--panel);
      border: 1px solid var(--line);
      border-left: 4px solid var(--section-accent);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      overflow: visible;
      backdrop-filter: blur(12px);
      transition: border-color 0.2s ease, box-shadow 0.2s ease, background 0.2s ease;
      --section-accent: rgba(96,165,250,0.45);
      --section-accent-soft: rgba(96,165,250,0.08);
    }
    section::before {
      content: none;
      position: absolute;
      top: 0;
      bottom: 0;
      left: 0;
      width: 3px;
      background: var(--section-accent);
      opacity: 0.42;
      pointer-events: none;
    }
    section:hover {
      border-color: rgba(148,163,184,0.18);
      border-left-color: var(--section-accent);
    }
    section.section-primary {
      border-color: rgba(96,165,250,0.24);
      border-left-color: var(--section-accent);
      background:
        linear-gradient(180deg, rgba(17,24,39,0.82), rgba(15,23,42,0.66)),
        linear-gradient(90deg, var(--section-accent-soft), transparent 36%);
      box-shadow: var(--shadow-lg);
    }
    section.section-primary::before { opacity: 0.76; width: 4px; }
    section.section-core {
      background:
        linear-gradient(180deg, rgba(17,24,39,0.74), rgba(15,23,42,0.60)),
        linear-gradient(90deg, var(--section-accent-soft), transparent 28%);
    }
    section.section-support {
      background: rgba(17,24,39,0.54);
    }
    section.section-support::before { opacity: 0.28; }
    section.section-risk {
      border-color: rgba(251,191,36,0.15);
      border-left-color: var(--section-accent);
      background:
        linear-gradient(180deg, rgba(17,24,39,0.70), rgba(15,23,42,0.60)),
        linear-gradient(90deg, rgba(251,191,36,0.06), transparent 30%);
    }
    section.section-system {
      border-style: solid;
      background: rgba(15,23,42,0.48);
    }
    .section-head {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      padding: 16px 20px;
      cursor: pointer;
      user-select: none;
      transition: background 0.2s ease;
      border-bottom: 1px solid transparent;
    }
    .section-head:hover {
      background: rgba(255,255,255,0.02);
    }
    .section-head.expanded {
      border-bottom-color: var(--line);
    }
    .section-head-left {
      display: flex;
      align-items: center;
      gap: 10px;
      min-width: 0;
    }
    .section-icon {
      width: 26px;
      height: 26px;
      min-width: 26px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border-radius: 8px;
      color: var(--section-accent);
      background: var(--section-accent-soft);
      border: 1px solid rgba(148,163,184,0.10);
    }
    .section-icon svg {
      width: 15px;
      height: 15px;
      stroke: currentColor;
      stroke-width: 2;
      fill: none;
    }
    section.section-primary .section-icon {
      width: 30px;
      height: 30px;
      min-width: 30px;
      border-radius: 9px;
      background: var(--section-accent-soft);
      box-shadow: inset 0 1px 0 rgba(255,255,255,0.06);
    }
    .chevron {
      width: 18px;
      height: 18px;
      color: var(--muted);
      transition: transform 0.35s cubic-bezier(0.4, 0, 0.2, 1);
      flex-shrink: 0;
    }
    .section-head.expanded .chevron {
      transform: rotate(180deg);
    }
    h2 {
      font-size: 14px;
      font-weight: 600;
      letter-spacing: 0;
      color: var(--ink);
      min-width: 0;
      overflow-wrap: anywhere;
    }
    section.section-primary h2 {
      font-size: 15px;
      font-weight: 750;
    }
    h3 {
      font-size: 12px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: var(--ink-secondary);
      margin-bottom: 8px;
    }
    .subtle {
      color: var(--muted);
      font-size: 11px;
      font-weight: 400;
    }
    .section-content {
      overflow: hidden;
      transition: max-height 0.45s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.3s ease;
      max-height: 0;
      opacity: 0;
    }
    .section-content.expanded {
      max-height: 5000px;
      opacity: 1;
      overflow: visible;
    }
    .section-wrap-up {
      display: flex;
      justify-content: center;
      height: 0;
      margin-top: 18px;
      padding: 0 18px;
      border-top: 0;
      background: transparent;
      position: relative;
      z-index: 5;
      pointer-events: none;
    }
    .section-wrap-button {
      min-height: 34px;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 7px 12px 7px 9px;
      border-radius: 999px;
      border: 1px solid rgba(148,163,184,0.18);
      background:
        linear-gradient(135deg, rgba(96,165,250,0.08), rgba(45,212,191,0.04)),
        rgba(15,23,42,0.68);
      color: var(--muted);
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      transform: translateY(-50%);
      pointer-events: auto;
      backdrop-filter: blur(10px) saturate(130%);
      -webkit-backdrop-filter: blur(10px) saturate(130%);
      box-shadow: 0 8px 18px rgba(0,0,0,0.22), inset 0 1px 0 rgba(255,255,255,0.06);
      transition: background 0.18s ease, border-color 0.18s ease, color 0.18s ease, box-shadow 0.18s ease;
    }
    .section-wrap-button:hover {
      color: var(--ink);
      border-color: color-mix(in srgb, var(--section-accent) 42%, rgba(148,163,184,0.22));
      background:
        linear-gradient(135deg, color-mix(in srgb, var(--section-accent) 16%, transparent), rgba(255,255,255,0.035)),
        rgba(15,23,42,0.52);
      box-shadow: 0 9px 20px rgba(0,0,0,0.24), inset 0 1px 0 rgba(255,255,255,0.08);
    }
    .section-wrap-icon {
      width: 20px;
      height: 20px;
      min-width: 20px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border-radius: 999px;
      background: rgba(96,165,250,0.14);
      color: var(--blue);
    }
    .section-wrap-icon svg {
      width: 13px;
      height: 13px;
      stroke: currentColor;
      stroke-width: 2.2;
      fill: none;
    }

    /* ─── Charts ─── */
    .chart-wrap {
      padding: 10px 10px 16px;
      height: clamp(420px, 44vh, 620px);
      width: 100%;
      min-width: 0;
    }
    .chart-wrap.compact {
      height: clamp(260px, 30vh, 380px);
      padding-top: 4px;
    }
    svg { width: 100%; height: 100%; display: block; }
    .axis { stroke: rgba(148,163,184,0.15); stroke-width: 1; }
    .grid-line { stroke: rgba(148,163,184,0.06); stroke-width: 1; }
    .hover-line { stroke: rgba(148,163,184,0.4); stroke-width: 1; stroke-dasharray: 3 3; }
    .flow-event-line {
      transition: stroke-width 0.15s ease, stroke-opacity 0.15s ease, stroke 0.15s ease;
    }
    .flow-event-line.highlighted {
      stroke-width: 4.5px !important;
      stroke-opacity: 0.95 !important;
    }
    .hover-label {
      fill: var(--ink);
      font-size: 12px;
      paint-order: stroke;
      stroke: var(--bg-secondary);
      stroke-width: 4px;
      stroke-linejoin: round;
    }
    .series-invested { stroke: var(--blue); }
    .series-net { stroke: var(--green); }
    .series-cost { stroke: var(--teal); }
    .series-proceeds { stroke: var(--amber); }
    .series-realized { stroke: var(--red); }
    .series-market { stroke: var(--green); }
    .series-profit { stroke: var(--violet); }
    .series-return { stroke: var(--red); }
    .series-msci { stroke: var(--cyan); stroke-dasharray: 4 4; }
    .series-xeon { stroke: var(--pink); stroke-dasharray: 3 3; }
    .series-inflation { stroke: var(--amber); stroke-dasharray: 2 2; }
    .series-weighted { stroke: var(--violet); }
    .series-freq { stroke: var(--teal); }
    .series-line {
      fill: none;
      stroke-width: 2;
      stroke-linecap: round;
      stroke-linejoin: round;
    }

    /* ─── Legend ─── */
    .legend {
      display: flex;
      flex-wrap: wrap;
      gap: 8px 18px;
      padding: 0 20px 18px;
      color: var(--muted);
      font-size: 12px;
    }
    .chart-controls {
      width: 100%;
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 10px;
      align-items: stretch;
    }
    .chart-control-group {
      min-width: 0;
      border: 1px solid var(--line);
      border-radius: var(--radius-sm);
      background: rgba(15, 23, 42, 0.36);
      padding: 10px 12px;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .chart-control-title {
      color: var(--muted);
      font-size: 10px;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }
    .chart-control-items {
      display: flex;
      flex-wrap: wrap;
      gap: 7px 12px;
      align-items: center;
    }
    .legend label,
    .legend-item,
    .score-pill {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      cursor: pointer;
      transition: color 0.15s ease;
      min-height: 22px;
    }
    .legend label:hover { color: var(--ink-secondary); }
    .legend input { margin: 0; accent-color: var(--blue); }
    .legend-item {
      cursor: default;
      color: var(--ink-secondary);
    }
    .score-pill {
      border: 1px solid var(--line);
      border-radius: 999px;
      background: rgba(30, 41, 59, 0.7);
      color: var(--muted);
      padding: 3px 9px;
      user-select: none;
      backdrop-filter: blur(10px);
    }
    .score-pill.active {
      color: var(--ink);
      box-shadow: var(--shadow-glow);
    }
    .score-pill.teal.active {
      border-color: var(--teal);
      background: rgba(45, 212, 191, 0.15);
    }
    .score-pill.violet.active {
      border-color: var(--violet);
      background: rgba(167, 139, 250, 0.15);
    }
    .score-pill-label {
      color: inherit;
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.03em;
    }
    .score-pill-value {
      font-size: 11px;
      font-weight: 800;
    }
    .dot {
      display: inline-block;
      width: 8px;
      height: 8px;
      border-radius: 999px;
      margin-right: 5px;
      vertical-align: middle;
    }

    /* ─── Tables ─── */
    .table-wrap {
      overflow: auto;
      max-height: 620px;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;
    }
    th, td {
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
      text-align: right;
      white-space: nowrap;
    }
    th {
      position: sticky;
      top: 0;
      z-index: 1;
      background: var(--bg-secondary);
      color: var(--muted);
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }
    th.sortable {
      cursor: pointer;
      user-select: none;
      transition: color 0.15s ease;
    }
    th.sortable:hover {
      color: var(--ink-secondary);
    }
    th:first-child, td:first-child { text-align: left; }
    tr {
      transition: background 0.15s ease;
    }
    tbody tr:hover {
      background: rgba(255,255,255,0.02);
    }

    /* ─── Status badges ─── */
    .status {
      display: inline-block;
      border: 1px solid var(--line-strong);
      border-radius: 999px;
      padding: 2px 8px;
      color: var(--muted);
      background: rgba(255,255,255,0.04);
      font-size: 11px;
      font-weight: 500;
    }
    .status.priced {
      color: var(--green);
      border-color: rgba(52,211,153,0.3);
      background: var(--green-dim);
    }
    .status.snapshot {
      color: var(--blue);
      border-color: rgba(96,165,250,0.3);
      background: var(--blue-dim);
    }
    .status.missing_isin, .status.unresolved, .status.price_error, .status.fx_error {
      color: var(--amber);
      border-color: rgba(251,191,36,0.3);
      background: var(--amber-dim);
    }
    .status.closed {
      color: var(--muted);
      border-color: var(--line);
      background: rgba(255,255,255,0.02);
    }
    .holdings-toolbar {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      align-items: center;
      gap: 12px;
      padding: 14px 20px 12px;
    }
    .holdings-focus-copy {
      min-width: 0;
      display: flex;
      align-items: baseline;
      gap: 8px;
      flex-wrap: wrap;
      line-height: 1.25;
    }
    .holdings-focus-copy strong {
      color: var(--ink);
      font-size: 13px;
      font-weight: 700;
    }
    .holdings-focus-copy span {
      color: var(--muted);
      font-size: 11px;
      line-height: 1.25;
    }
    .holdings-focus-copy span::before {
      content: "·";
      margin-right: 8px;
      color: var(--line-strong);
    }
    .holdings-actions {
      display: flex;
      gap: 6px;
      align-items: center;
      flex-wrap: nowrap;
      justify-content: flex-end;
    }
    .holdings-action {
      min-height: 30px;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 8px 4px 5px;
      border-radius: 8px;
      background: rgba(15,23,42,0.52);
      border: 1px solid var(--line);
      color: var(--ink-secondary);
      box-shadow: inset 0 1px 0 rgba(255,255,255,0.03);
    }
    .holdings-action:hover {
      transform: translateY(-1px);
      box-shadow: var(--shadow-glow);
    }
    .holdings-action-icon {
      width: 20px;
      height: 20px;
      min-width: 20px;
      border-radius: 7px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      color: #fff;
    }
    .holdings-action-icon svg {
      width: 13px;
      height: 13px;
      stroke: currentColor;
      stroke-width: 2;
      fill: none;
    }
    .holdings-action-copy {
      display: inline-flex;
      align-items: baseline;
      gap: 5px;
      text-align: left;
      line-height: 1.15;
    }
    .holdings-action-copy strong {
      color: inherit;
      font-size: 11px;
      font-weight: 700;
      white-space: nowrap;
    }
    .holdings-action-copy small {
      color: var(--muted);
      font-size: 9px;
      font-weight: 600;
      white-space: nowrap;
    }
    .holdings-action-copy small::before {
      content: "·";
      margin-right: 5px;
      color: var(--line-strong);
    }
    .holdings-action.focus .holdings-action-icon {
      background: linear-gradient(135deg, rgba(96,165,250,0.9), rgba(45,212,191,0.72));
    }
    .holdings-action.focus {
      border-color: rgba(96,165,250,0.26);
    }
    .holdings-action.focus.active {
      background: rgba(96,165,250,0.14);
      border-color: rgba(96,165,250,0.48);
      color: var(--ink);
    }
    .holdings-action.closed .holdings-action-icon {
      background: linear-gradient(135deg, rgba(251,191,36,0.88), rgba(248,113,113,0.72));
    }
    .holdings-action.closed {
      border-color: rgba(251,191,36,0.22);
    }
    .holdings-action.closed.active {
      background: rgba(251,191,36,0.12);
      border-color: rgba(251,191,36,0.42);
      color: var(--ink);
    }
    .underlying-name {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
      min-width: 0;
    }
    .source-pills {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      flex-wrap: wrap;
    }
    .source-pill {
      display: inline-flex;
      align-items: center;
      max-width: 190px;
      min-height: 20px;
      padding: 2px 7px;
      border: 1px solid rgba(96,165,250,0.24);
      border-radius: 999px;
      background: rgba(96,165,250,0.1);
      color: var(--ink-secondary);
      font-size: 10px;
      font-weight: 600;
      line-height: 1.25;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      transition: all 0.15s ease-in-out;
    }
    .source-pill.active {
      background: var(--blue) !important;
      border-color: var(--blue) !important;
      color: #ffffff !important;
    }
    .composition-source-row {
      cursor: pointer;
    }
    .composition-source-row td {
      transition: background 0.15s ease, border-color 0.15s ease;
    }
    .composition-source-row.selected td {
      background: rgba(96,165,250,0.1);
      border-bottom-color: rgba(96,165,250,0.28);
    }
    .selected-flag {
      display: inline-flex;
      align-items: center;
      min-height: 18px;
      padding: 1px 7px;
      border-radius: 999px;
      border: 1px solid rgba(96,165,250,0.4);
      background: rgba(96,165,250,0.14);
      color: var(--blue);
      font-size: 9px;
      font-weight: 800;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      line-height: 1.2;
    }
    .news-symbols {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }
    .news-list {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 10px;
    }
    .news-card {
      min-width: 0;
      padding: 12px 14px;
      border: 1px solid var(--line);
      border-radius: var(--radius-sm);
      background: rgba(30,41,59,0.36);
      display: grid;
      gap: 8px;
    }
    .news-card a {
      color: var(--ink);
      text-decoration: none;
      font-size: 13px;
      font-weight: 600;
      line-height: 1.35;
    }
    .news-card a:hover { color: var(--blue); }
    .news-meta {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      align-items: center;
      color: var(--muted);
      font-size: 11px;
    }

    /* ─── Positive/Negative ─── */
    .positive { color: var(--green); }
    .negative { color: var(--red); }

    /* ─── Mapping / Coverage ─── */
    .mapping {
      padding: 18px 20px 20px;
      display: grid;
      gap: 12px;
      color: var(--muted);
      font-size: 13px;
    }
    .section-body {
      padding: 18px 20px 20px;
      display: grid;
      gap: 16px;
    }
    .stats-distribution {
      display: grid;
      gap: 12px;
      margin-top: 4px;
    }
    .stats-distribution-head {
      display: flex;
      justify-content: space-between;
      align-items: flex-end;
      gap: 12px;
      flex-wrap: wrap;
    }
    .stats-distribution-head h3 {
      color: var(--ink);
      font-size: 14px;
      font-weight: 700;
      margin-bottom: 3px;
    }
    .distribution-legend {
      display: inline-flex;
      gap: 10px;
      align-items: center;
      color: var(--muted);
      font-size: 11px;
      font-weight: 600;
    }
    .legend-dot {
      width: 9px;
      height: 9px;
      border-radius: 999px;
      display: inline-block;
      margin-right: 5px;
    }
    .legend-dot.portfolio { background: var(--blue); }
    .legend-dot.msci { background: var(--teal); }
    .return-distribution-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 14px;
    }
    .return-distribution-card {
      min-width: 0;
      border: 1px solid var(--line);
      border-radius: var(--radius-sm);
      padding: 14px;
      background: rgba(15,23,42,0.36);
      box-shadow: inset 0 1px 0 rgba(255,255,255,0.03);
    }
    .return-distribution-card-head {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      align-items: flex-start;
      margin-bottom: 8px;
    }
    .return-distribution-card strong {
      color: var(--ink);
      font-size: 13px;
      font-weight: 700;
    }
    .return-distribution-meta {
      color: var(--muted);
      font-size: 11px;
      line-height: 1.35;
      text-align: right;
    }
    .return-distribution-card svg {
      display: block;
      width: 100%;
      height: 210px;
      overflow: visible;
    }
    .hist-grid-line,
    .hist-axis {
      stroke: rgba(148,163,184,0.18);
      stroke-width: 1;
      shape-rendering: crispEdges;
    }
    .hist-zero-line {
      stroke: rgba(241,245,249,0.38);
      stroke-width: 1.2;
      shape-rendering: crispEdges;
    }
    .hist-bar.portfolio { fill: rgba(96,165,250,0.74); }
    .hist-bar.msci { fill: rgba(45,212,191,0.72); }
    .hist-mean-line.portfolio { stroke: var(--blue); }
    .hist-mean-line.msci { stroke: var(--teal); }
    .hist-mean-line {
      stroke-width: 2;
      stroke-dasharray: 4 4;
    }
    .hist-label {
      fill: var(--muted);
      font-size: 10px;
      font-weight: 600;
    }

    /* ─── Friction metrics ─── */
    .friction-summary {
      display: grid;
      grid-template-columns: repeat(4, minmax(130px, 1fr));
      gap: 12px;
      border-bottom: 1px solid var(--line);
      padding-bottom: 16px;
    }
    .friction-item {
      padding: 12px 14px;
      background: rgba(30,41,59,0.4);
      border: 1px solid var(--line);
      border-radius: var(--radius-sm);
    }
    .friction-item span {
      display: block;
      color: var(--muted);
      font-size: 11px;
      font-weight: 500;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      line-height: 1.25;
    }
    .friction-item strong {
      display: block;
      margin-top: 6px;
      font-size: 18px;
      font-weight: 700;
      line-height: 1.15;
      overflow-wrap: anywhere;
    }
    .expense-summary {
      display: grid;
      grid-template-columns: repeat(5, minmax(120px, 1fr));
      gap: 12px;
      border-bottom: 1px solid var(--line);
      padding-bottom: 16px;
    }
    .expense-item {
      padding: 12px 14px;
      background: rgba(30,41,59,0.36);
      border: 1px solid var(--line);
      border-radius: var(--radius-sm);
    }
    .expense-item span {
      display: block;
      color: var(--muted);
      font-size: 11px;
      font-weight: 500;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      line-height: 1.25;
    }
    .expense-item strong {
      display: block;
      margin-top: 6px;
      font-size: 18px;
      font-weight: 700;
      line-height: 1.15;
      overflow-wrap: anywhere;
    }
    .expense-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }
    .expense-grid .table-wrap,
    .expense-chart-card {
      max-height: 360px;
      border: 1px solid var(--line);
      border-radius: var(--radius-sm);
      overflow: auto;
      background: rgba(15,23,42,0.28);
    }
    .expense-chart-card {
      padding: 12px 14px;
      overflow: hidden;
    }
    .expense-chart-card h3 {
      margin-bottom: 10px;
    }
    .expense-chart {
      width: 100%;
      height: 230px;
      display: block;
      overflow: visible;
    }
    .expense-bar.spend { fill: rgba(96,165,250,0.74); }
    .expense-bar.income { fill: rgba(52,211,153,0.62); }
    .expense-bar.net { fill: rgba(251,191,36,0.58); }
    .expense-line { fill: none; stroke-width: 2.5; stroke-linecap: round; stroke-linejoin: round; }
    .expense-line.spend { stroke: #60a5fa; }
    .expense-line.income { stroke: #34d399; }
    .expense-line.net { stroke: #fbbf24; }
    .expense-axis,
    .expense-grid-line {
      stroke: rgba(148,163,184,0.18);
      stroke-width: 1;
      shape-rendering: crispEdges;
    }
    .expense-label {
      fill: var(--muted);
      font-size: 10px;
      font-weight: 600;
    }
    .empty-state {
      color: var(--muted);
      font-size: 13px;
      line-height: 1.45;
    }

    /* ─── Allocation Grid ─── */
    .allocation-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }
    .allocation-grid .table-wrap {
      max-height: 360px;
      border: 1px solid var(--line);
      border-radius: var(--radius-sm);
      overflow: auto;
    }

    /* ─── Progress bar ─── */
    .bar {
      height: 8px;
      background: rgba(30,41,59,0.6);
      border-radius: 999px;
      overflow: hidden;
      border: 1px solid var(--line);
    }
    .bar span {
      display: block;
      height: 100%;
      background: var(--gradient-accent);
      border-radius: 999px;
      transition: width 0.6s cubic-bezier(0.4, 0, 0.2, 1);
    }

    /* ─── Error ─── */
    .error {
      border: 1px solid rgba(248,113,113,0.3);
      background: var(--red-dim);
      color: var(--red);
      border-radius: var(--radius-sm);
      padding: 14px 18px;
      display: none;
      font-size: 13px;
    }

    /* ─── Loading shimmer ─── */
    @keyframes shimmer {
      0% { background-position: -200% 0; }
      100% { background-position: 200% 0; }
    }
    .loading-shimmer {
      background: linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.04) 50%, transparent 100%);
      background-size: 200% 100%;
      animation: shimmer 1.5s infinite;
    }
    @keyframes refresh-spin {
      to { transform: rotate(360deg); }
    }
    @keyframes refresh-pulse {
      0%, 100% { opacity: 0.72; transform: scaleX(0.7); }
      50% { opacity: 1; transform: scaleX(1); }
    }
    body.dashboard-refreshing main > :not(.dashboard-refresh-overlay),
    body.dashboard-redrawing main > :not(.dashboard-refresh-overlay) {
      opacity: 0.14;
      filter: blur(10px) saturate(0.8);
      transform: scale(0.992);
      pointer-events: none;
      user-select: none;
    }
    .dashboard-refresh-overlay {
      position: fixed;
      inset: 86px 24px 24px;
      z-index: 90;
      display: grid;
      place-items: center;
      opacity: 0;
      pointer-events: none;
      transform: translateY(8px);
      transition: opacity 0.22s ease, transform 0.22s ease;
    }
    body.dashboard-refreshing .dashboard-refresh-overlay,
    body.dashboard-redrawing .dashboard-refresh-overlay {
      opacity: 1;
      transform: translateY(0);
    }
    .refresh-card {
      width: min(320px, calc(100vw - 48px));
      border: 1px solid rgba(96,165,250,0.26);
      border-radius: var(--radius);
      padding: 18px;
      background:
        linear-gradient(135deg, rgba(17,24,39,0.9), rgba(30,41,59,0.78)),
        radial-gradient(circle at 20% 0%, rgba(96,165,250,0.25), transparent 34%);
      box-shadow: var(--shadow-lg), 0 0 36px rgba(96,165,250,0.12);
      backdrop-filter: blur(22px) saturate(170%);
      -webkit-backdrop-filter: blur(22px) saturate(170%);
      display: grid;
      gap: 12px;
      justify-items: center;
      text-align: center;
    }
    .refresh-ring {
      width: 44px;
      height: 44px;
      border-radius: 999px;
      border: 2px solid rgba(148,163,184,0.2);
      border-top-color: var(--blue);
      border-right-color: var(--violet);
      animation: refresh-spin 0.85s linear infinite;
      box-shadow: 0 0 24px rgba(96,165,250,0.22);
    }
    .refresh-title {
      color: var(--ink);
      font-size: 13px;
      font-weight: 700;
      letter-spacing: 0;
    }
    .refresh-bar {
      width: 100%;
      height: 3px;
      overflow: hidden;
      border-radius: 999px;
      background: rgba(148,163,184,0.12);
    }
    .refresh-bar span {
      display: block;
      width: 100%;
      height: 100%;
      border-radius: inherit;
      background: var(--gradient-accent);
      transform-origin: center;
      animation: refresh-pulse 1.05s ease-in-out infinite;
    }
    @media (prefers-reduced-motion: reduce) {
      .refresh-ring,
      .refresh-bar span {
        animation: none;
      }
      body.dashboard-refreshing main > :not(.dashboard-refresh-overlay),
      body.dashboard-redrawing main > :not(.dashboard-refresh-overlay),
      .dashboard-refresh-overlay {
        transition: none;
      }
    }

    /* ─── Responsive ─── */
    @media (max-width: 1100px) {
      .metrics { grid-template-columns: repeat(3, minmax(130px, 1fr)); }
      .friction-summary,
      .expense-summary { grid-template-columns: repeat(2, minmax(130px, 1fr)); }
      .allocation-grid,
      .expense-grid { grid-template-columns: 1fr; }
    }
    @media (max-width: 680px) {
      header { align-items: flex-start; flex-direction: column; padding: 16px 18px; }
      header::after { left: 18px; right: 18px; }
      .topbar-brand { width: 100%; }
      .brand-mark {
        width: 38px;
        height: 38px;
        min-width: 38px;
        border-radius: 11px;
      }
      h1 { font-size: 20px; }
      .meta { max-width: 100%; }
      .topbar-actions { width: 100%; }
      #refresh { width: 100%; }
      main { padding: 16px 18px 36px; }
      .control-stack { gap: 8px; }
      .control-row { gap: 8px; }
      .secondary-controls {
        gap: 6px;
        opacity: 0.76;
      }
      .secondary-label {
        width: 100%;
      }
      .selector-fancy {
        max-width: 100%;
        overflow-x: auto;
      }
      .selector-fancy button { padding-right: 9px; }
      .person-selector .selector-label { max-width: 76px; }
      .broker-selector .selector-label { max-width: 118px; }
      .return-distribution-card-head {
        flex-direction: column;
      }
      .return-distribution-meta {
        text-align: left;
      }
      .holdings-toolbar {
        grid-template-columns: 1fr;
        align-items: flex-start;
        padding: 12px 14px 10px;
      }
      .holdings-actions {
        width: 100%;
        justify-content: flex-start;
        overflow-x: auto;
        padding-bottom: 2px;
      }
      .holdings-action {
        flex: 0 0 auto;
      }
      .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .movers-grid { grid-template-columns: 1fr; }
      .export-panel { align-items: flex-start; flex-direction: column; }
      .export-actions { justify-content: flex-start; width: 100%; }
      .metric strong { font-size: 18px; }
      .chart-wrap { height: 300px; }
      th, td { padding: 8px 6px; font-size: 11px; }
      .section-head { padding: 14px 16px; }
      .section-body, .mapping { padding: 14px 16px; }
    }
    
    /* ─── Fee Compounding Calculator ─── */
    .calculator-layout {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 20px;
      margin-top: 10px;
    }
    .calculator-inputs {
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .calculator-input-group {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .calculator-input-group label {
      font-size: 12px;
      font-weight: 500;
      color: var(--ink-secondary);
      display: flex;
      justify-content: space-between;
    }
    .calculator-input-group label span {
      color: var(--blue);
      font-weight: 600;
    }
    .calculator-input-group input[type="range"] {
      width: 100%;
      height: 6px;
      background: rgba(30,41,59,0.8);
      border-radius: 999px;
      outline: none;
      -webkit-appearance: none;
    }
    .calculator-input-group input[type="range"]::-webkit-slider-thumb {
      -webkit-appearance: none;
      width: 16px;
      height: 16px;
      border-radius: 50%;
      background: var(--blue);
      cursor: pointer;
      border: 2px solid var(--panel-solid);
      box-shadow: 0 0 5px rgba(0,0,0,0.5);
    }
    .calculator-results {
      background: rgba(255,255,255,0.02);
      border: 1px solid var(--line);
      border-radius: var(--radius-sm);
      padding: 18px;
      display: flex;
      flex-direction: column;
      gap: 16px;
    }
    .calc-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-bottom: 10px;
      border-bottom: 1px solid var(--line);
    }
    .calc-row:last-child {
      border-bottom: none;
      padding-bottom: 0;
    }
    .calc-label {
      font-size: 13px;
      color: var(--ink-secondary);
    }
    .calc-val {
      font-size: 16px;
      font-weight: 700;
    }
    .calc-val.red {
      color: var(--red);
    }
    .calc-val.green {
      color: var(--green);
    }
    .calc-val.amber {
      color: var(--amber);
      font-size: 18px;
    }
    .calc-progress {
      margin-top: 6px;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .calc-bar-label {
      display: flex;
      justify-content: space-between;
      font-size: 11px;
      color: var(--muted);
    }
    .calc-bar-outer {
      height: 10px;
      background: rgba(30,41,59,0.6);
      border-radius: 999px;
      overflow: hidden;
      border: 1px solid var(--line);
    }
    .calc-bar-inner {
      height: 100%;
      border-radius: 999px;
    }
    .calc-bar-inner.mystyle {
      background: linear-gradient(90deg, #f87171, #ef4444);
    }
    .calc-bar-inner.etf {
      background: linear-gradient(90deg, #34d399, #10b981);
    }
  </style>
</head>
<body>
  <header>
    <div class="topbar-brand">
      <span class="brand-mark" aria-hidden="true">
        <svg viewBox="0 0 24 24">
          <path d="M4 18V6"/>
          <path d="M4 16l5-5 4 3 7-8"/>
          <path d="M15 6h5v5"/>
        </svg>
      </span>
      <div class="topbar-copy">
        <h1>Portfolio Dashboard</h1>
        <div class="meta" id="meta">Loading…</div>
      </div>
    </div>
    <div class="topbar-actions">
      <button id="refresh" type="button">
        <span class="refresh-button-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24"><path d="M20 11a8 8 0 0 0-14.8-4.2L3 9"/><path d="M3 4v5h5"/><path d="M4 13a8 8 0 0 0 14.8 4.2L21 15"/><path d="M21 20v-5h-5"/></svg>
        </span>
        <span>Refresh Prices</span>
      </button>
    </div>
  </header>
  <main>
    <div class="dashboard-refresh-overlay" aria-live="polite" aria-busy="true">
      <div class="refresh-card">
        <div class="refresh-ring" aria-hidden="true"></div>
        <div class="refresh-title" id="refresh-status">Updating dashboard</div>
        <div class="refresh-bar" aria-hidden="true"><span></span></div>
      </div>
    </div>
    <div class="error" id="error"></div>
    <div class="control-stack">
      <div class="control-row primary-controls">
        <div class="periods selector-fancy person-selector" id="persons" aria-label="Portfolio person">
          <!-- PORTFOLIO_BUTTONS -->
        </div>
        <div class="periods selector-fancy time-selector" id="periods" aria-label="Performance window">
          <button type="button" data-period="1w" style="--time-fill:.16;--time-width:60px" title="Last 1 week">
            <span class="time-main"><span class="time-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg></span><span class="selector-label">1W</span></span>
            <span class="time-scale" aria-hidden="true"><span></span></span>
          </button>
          <button type="button" data-period="1m" style="--time-fill:.28;--time-width:64px" title="Last 1 month">
            <span class="time-main"><span class="time-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg></span><span class="selector-label">1M</span></span>
            <span class="time-scale" aria-hidden="true"><span></span></span>
          </button>
          <button type="button" data-period="ytd" style="--time-fill:.44;--time-width:70px" title="Year to date">
            <span class="time-main"><span class="time-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg></span><span class="selector-label">YTD</span></span>
            <span class="time-scale" aria-hidden="true"><span></span></span>
          </button>
          <button type="button" data-period="1y" style="--time-fill:.58;--time-width:76px" title="Last 1 year">
            <span class="time-main"><span class="time-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg></span><span class="selector-label">1Y</span></span>
            <span class="time-scale" aria-hidden="true"><span></span></span>
          </button>
          <button type="button" data-period="since24" class="active" style="--time-fill:.76;--time-width:82px" title="Since January 2024">
            <span class="time-main"><span class="time-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg></span><span class="selector-label">'24</span></span>
            <span class="time-scale" aria-hidden="true"><span></span></span>
          </button>
          <button type="button" data-period="all" style="--time-fill:1;--time-width:88px" title="All time">
            <span class="time-main"><span class="time-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg></span><span class="selector-label">All</span></span>
            <span class="time-scale" aria-hidden="true"><span></span></span>
          </button>
        </div>
        <div class="periods selector-fancy broker-selector" id="brokers" aria-label="Broker filter" style="display:none;"></div>
      </div>
      <div class="control-row secondary-controls" aria-label="Secondary dashboard options">
        <span class="secondary-label">Options</span>
        <div class="periods secondary-selector" id="berkshire-mode" aria-label="Berkshire exposure mode">
          <button type="button" data-berkshire="stock" class="active">BRK stock</button>
          <button type="button" data-berkshire="lookthrough">BRK 13F</button>
        </div>
        <div class="periods secondary-selector" id="proxy-mode" aria-label="Proxy composition mode">
          <button type="button" data-proxy="on" class="active">Proxy gaps</button>
          <button type="button" data-proxy="off">Official only</button>
        </div>
        <div class="periods secondary-selector" id="live-mode" aria-label="Live price filter">
          <button type="button" data-live="all" class="active">All assets</button>
          <button type="button" data-live="live">Live only</button>
        </div>
        <div class="periods secondary-selector" id="return-mode" aria-label="Return calculation mode">
          <button type="button" data-return-mode="price" class="active">Price Return</button>
          <button type="button" data-return-mode="total">Total Return</button>
        </div>
      </div>
    </div>
    <div class="metrics" id="metrics"></div>
    <div class="movers-panel" id="movers-panel" hidden></div>

    <!-- User Rankings -->
    <section>
      <div class="section-head expanded" data-collapse="rankings-content" onclick="toggleSection(this)">
        <div class="section-head-left">
          <svg class="chevron" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z" clip-rule="evenodd"/></svg>
          <h2>Family Rankings</h2>
        </div>
        <span class="subtle" id="rankings-window-label">Common alignment: loading…</span>
      </div>
      <div class="section-content expanded" id="rankings-content">
        <div class="table-wrap">
          <table class="positions-table" id="rankings-table">
            <thead>
              <tr>
                <th style="text-align: left; cursor: default;">User</th>
                <th class="sortable" onclick="sortRankings('start')" id="rank-header-start">Return (Start of Portfolio)</th>
                <th class="sortable" onclick="sortRankings('common')" id="rank-header-common">Return (Common Alignment) ↓</th>
                <th class="sortable" onclick="sortRankings('ytd')" id="rank-header-ytd">Return (YTD)</th>
              </tr>
            </thead>
            <tbody id="rankings-tbody">
              <!-- Dynamically populated -->
            </tbody>
          </table>
        </div>
      </div>
    </section>

    <!-- Portfolio Value -->
    <section>
      <div class="section-head expanded" data-collapse="value-content" onclick="toggleSection(this)">
        <div class="section-head-left">
          <svg class="chevron" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z" clip-rule="evenodd"/></svg>
          <h2>Portfolio Value</h2>
        </div>
        <span class="subtle" id="value-window"></span>
      </div>
      <div class="section-content expanded" id="value-content">
        <div class="chart-wrap"><svg id="value-chart" role="img" aria-label="Portfolio value chart"></svg></div>
        <div class="chart-wrap compact"><svg id="return-chart" role="img" aria-label="Portfolio return percentage chart"></svg></div>
        <div id="score-pills" hidden></div>
        <div class="legend" id="value-legend"></div>
      </div>
    </section>

    <!-- Cash Flow Evolution -->
    <section>
      <div class="section-head expanded" data-collapse="cashflow-content" onclick="toggleSection(this)">
        <div class="section-head-left">
          <svg class="chevron" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z" clip-rule="evenodd"/></svg>
          <h2>Cash Flow Evolution</h2>
        </div>
        <span class="subtle" id="range"></span>
      </div>
      <div class="section-content expanded" id="cashflow-content">
        <div class="chart-wrap"><svg id="chart" role="img" aria-label="Portfolio evolution chart"></svg></div>
        <div class="legend" id="legend"></div>
      </div>
    </section>

    <!-- Current Holdings -->
    <section>
      <div class="section-head expanded" data-collapse="holdings-content" onclick="toggleSection(this)">
        <div class="section-head-left">
          <svg class="chevron" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z" clip-rule="evenodd"/></svg>
          <h2>Current Holdings</h2>
        </div>
        <span class="subtle" id="holdings-count"></span>
      </div>
      <div class="section-content expanded" id="holdings-content">
        <div class="holdings-toolbar">
          <div class="holdings-focus-copy">
            <strong id="holdings-view-title">Top holdings</strong>
            <span id="holdings-view-detail">Showing the largest open positions by current value.</span>
          </div>
          <div class="holdings-actions">
            <button type="button" id="btn-show-all-holdings" class="holdings-action focus">
              <span class="holdings-action-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24"><path d="M4 7h16"/><path d="M4 12h16"/><path d="M4 17h16"/><path d="M8 7v10"/></svg>
              </span>
              <span class="holdings-action-copy">
                <strong id="btn-show-all-label">Show all holdings</strong>
                <small id="btn-show-all-sub">Expand open rows</small>
              </span>
            </button>
            <button type="button" id="btn-toggle-closed" class="holdings-action closed">
              <span class="holdings-action-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24"><path d="M4 7h16"/><path d="M7 7V5h10v2"/><path d="M6 7l1 13h10l1-13"/><path d="M10 11v5"/><path d="M14 11v5"/></svg>
              </span>
              <span class="holdings-action-copy">
                <strong id="btn-closed-label">Show closed positions</strong>
                <small id="btn-closed-sub">Add exited rows</small>
              </span>
            </button>
          </div>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th class="sortable" data-sort="asset">Asset</th>
                <th class="sortable" data-sort="quantity">Qty</th>
                <th class="sortable" data-sort="isin">ISIN</th>
                <th class="sortable" data-sort="symbol">Symbol</th>
                <th class="sortable" data-sort="price">Price</th>
                <th class="sortable" data-sort="market_value_eur">Value EUR</th>
                <th class="sortable" data-sort="cost_basis_eur">Cost EUR</th>
                <th class="sortable" data-sort="display_pl_eur">P/L EUR</th>
                <th class="sortable" data-sort="display_pl_pct">P/L %</th>
                <th class="sortable" data-sort="pricing_status">Status</th>
              </tr>
            </thead>
            <tbody id="positions"></tbody>
          </table>
        </div>
      </div>
    </section>

    <!-- MyStyle Fee Compounding Calculator -->
    <section id="mystyle-calc-section" style="display: none;">
      <div class="section-head expanded" data-collapse="mystyle-calc-content" onclick="toggleSection(this)">
        <div class="section-head-left">
          <svg class="chevron" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z" clip-rule="evenodd"/></svg>
          <h2>MyStyle Fee Drag Calculator</h2>
        </div>
        <span class="subtle">Compounding Cost Projections</span>
      </div>
      <div class="section-content expanded" id="mystyle-calc-content" style="padding: 16px 20px;">
        <div class="calculator-layout">
          <div class="calculator-inputs">
            <div class="calculator-input-group">
              <label>Starting Capital: <span id="lbl-start-cap">€0</span></label>
              <input type="range" id="input-start-cap" min="10000" max="1000000" step="5000" value="100000">
            </div>
            <div class="calculator-input-group">
              <label>Years Horizon: <span id="lbl-horizon">20 years</span></label>
              <input type="range" id="input-horizon" min="1" max="40" step="1" value="20">
            </div>
            <div class="calculator-input-group">
              <label>Assumed Gross Annual Return: <span id="lbl-gross-ret">7.0%</span></label>
              <input type="range" id="input-gross-ret" min="1" max="15" step="0.1" value="7.0">
            </div>
            <div class="calculator-input-group">
              <label>Current Product Annual Fee: <span id="lbl-mystyle-fee">2.30%</span></label>
              <input type="range" id="input-mystyle-fee" min="0.5" max="5.0" step="0.05" value="2.30">
            </div>
            <div class="calculator-input-group">
              <label>Alternative ETF Annual Cost (TER): <span id="lbl-etf-fee">0.22%</span></label>
              <input type="range" id="input-etf-fee" min="0.05" max="2.0" step="0.05" value="0.22">
            </div>
          </div>
          <div class="calculator-results">
            <div class="calc-row">
              <span class="calc-label">Current Product Net Return:</span>
              <span class="calc-val red" id="val-mystyle-net-ret">4.70%</span>
            </div>
            <div class="calc-row">
              <span class="calc-label">ETF Net Return:</span>
              <span class="calc-val green" id="val-etf-net-ret">6.78%</span>
            </div>
            <div class="calc-row">
              <span class="calc-label">Projected Value (Current Product):</span>
              <span class="calc-val red" id="val-proj-mystyle">€0</span>
            </div>
            <div class="calc-row">
              <span class="calc-label">Projected Value (ETF):</span>
              <span class="calc-val green" id="val-proj-etf">€0</span>
            </div>
            <div class="calc-row" style="margin-top: 4px; padding-top: 10px; border-top: 1px solid var(--line-strong);">
              <span class="calc-label" style="font-weight: 600;">Estimated Fee Difference:</span>
              <span class="calc-val amber" id="val-lost-fees">€0</span>
            </div>
            <div class="calc-progress">
              <div class="calc-bar-label">
                <span>Current Product</span>
                <span id="bar-pct-mystyle">67.5%</span>
              </div>
              <div class="calc-bar-outer">
                <div class="calc-bar-inner mystyle" id="bar-mystyle" style="width: 67.5%;"></div>
              </div>
              <div class="calc-bar-label" style="margin-top: 4px;">
                <span>ETF Alternative</span>
                <span>100%</span>
              </div>
              <div class="calc-bar-outer">
                <div class="calc-bar-inner etf" style="width: 100%;"></div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Product-specific breakdowns belong in private configuration. -->
    <!-- Watchlist -->
    <section>
      <div class="section-head expanded" data-collapse="watchlist-content" onclick="toggleSection(this)">
        <div class="section-head-left">
          <svg class="chevron" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z" clip-rule="evenodd"/></svg>
          <h2>Watchlist</h2>
        </div>
        <span class="subtle" id="watchlist-summary">Loading watchlist…</span>
      </div>
      <div class="section-content expanded" id="watchlist-content">
        <div id="watchlist-grid" style="
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
          gap: 15px;
          margin-bottom: 15px;
        ">
        </div>
        <!-- Add Ticker Control -->
        <div style="
          display: flex;
          align-items: center;
          gap: 10px;
          max-width: 400px;
          margin: 15px auto 0;
          background: rgba(15, 23, 42, 0.4);
          padding: 8px 12px;
          border-radius: var(--radius-sm);
          border: 1px solid var(--line);
        ">
          <input type="text" id="watchlist-add-input" placeholder="Enter Ticker (e.g. FUSD.L)" style="
            flex: 1;
            background: transparent;
            border: none;
            color: var(--ink);
            font-size: 13px;
            outline: none;
            padding: 4px 0;
          ">
          <button type="button" id="watchlist-add-btn" style="
            background: var(--blue-dim);
            border: 1px solid var(--blue);
            color: var(--blue);
            border-radius: 6px;
            padding: 4px 12px;
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
          ">Add Ticker</button>
        </div>
      </div>
    </section>

    <!-- Stock News -->
    <section>
      <div class="section-head" data-collapse="news-content" onclick="toggleSection(this)">
        <div class="section-head-left">
          <svg class="chevron" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z" clip-rule="evenodd"/></svg>
          <h2>Stock News</h2>
        </div>
        <span class="subtle" id="news-summary">Loading feeds…</span>
      </div>
      <div class="section-content" id="news-content">
        <div class="section-body">
          <div class="news-symbols" id="news-symbols"></div>
          <div class="news-list" id="news-list">
            <div class="empty-state">Loading stock news…</div>
          </div>
        </div>
      </div>
    </section>

    <!-- Portfolio Distribution -->
    <section>
      <div class="section-head" data-collapse="distribution-content" onclick="toggleSection(this)">
        <div class="section-head-left">
          <svg class="chevron" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z" clip-rule="evenodd"/></svg>
          <h2>Portfolio Distribution</h2>
        </div>
        <span class="subtle" id="distribution-summary"></span>
      </div>
      <div class="section-content" id="distribution-content">
        <div class="section-body">
          <div class="info-box">
            <strong>How distribution is calculated:</strong>
            Direct shares use their full market value. ETFs and funds are split by rows in <code>asset_exposures.csv</code>; source metadata is in <code>data/etf_documents.json</code> and <code>data/proxy_exposures.csv</code>.
          </div>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Composition Source</th>
                  <th>Fund</th>
                  <th>Issuer</th>
                  <th>Status</th>
                  <th>Rows</th>
                  <th>Fetched</th>
                </tr>
              </thead>
              <tbody id="distribution-sources"></tbody>
            </table>
          </div>
          <div class="allocation-grid">
            <div class="table-wrap">
              <table>
                <thead><tr><th>Underlying</th><th>Value EUR</th><th>Weight</th></tr></thead>
                <tbody id="distribution-underlying"></tbody>
              </table>
            </div>
            <div class="table-wrap">
              <table>
                <thead><tr><th>Sector</th><th>Value EUR</th><th>Weight</th></tr></thead>
                <tbody id="distribution-sectors"></tbody>
              </table>
            </div>
            <div class="table-wrap">
              <table>
                <thead><tr><th>Geo Area</th><th>Value EUR</th><th>Weight</th></tr></thead>
                <tbody id="distribution-geographies"></tbody>
              </table>
            </div>
            <div class="table-wrap">
              <table>
                <thead><tr><th>Asset Class</th><th>Value EUR</th><th>Weight</th></tr></thead>
                <tbody id="distribution-classes"></tbody>
              </table>
            </div>
          </div>
          <div class="table-wrap">
            <table>
              <thead><tr><th>Missing Composition</th><th>ISIN</th><th>Value EUR</th><th>Status</th></tr></thead>
              <tbody id="distribution-missing"></tbody>
            </table>
          </div>
        </div>
      </div>
    </section>

    <!-- Dividends -->
    <section>
      <div class="section-head" data-collapse="dividends-content" onclick="toggleSection(this)">
        <div class="section-head-left">
          <svg class="chevron" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z" clip-rule="evenodd"/></svg>
          <h2>Dividends</h2>
        </div>
        <span class="subtle" id="dividends-summary"></span>
      </div>
      <div class="section-content" id="dividends-content">
        <div class="section-body">
          <div class="table-wrap">
            <h3>Yearly Summary</h3>
          <table>
            <thead>
              <tr>
                <th>Year</th>
                <th>Net Dividends EUR</th>
                <th>Avg Portfolio Value EUR</th>
                <th>Dividend Yield %</th>
                <th>Avg Invested Capital EUR</th>
                <th>Yield on Cost %</th>
              </tr>
            </thead>
            <tbody id="dividends-yearly"></tbody>
          </table>
        </div>
        <div class="table-wrap">
          <h3>Aggregate by Asset</h3>
          <table>
            <thead>
              <tr>
                <th>Asset</th>
                <th>ISIN</th>
                <th>Payments</th>
                <th>Total Net EUR</th>
                <th>Total Tax EUR</th>
                <th>Total Gross EUR</th>
              </tr>
            </thead>
            <tbody id="dividends-aggregate"></tbody>
          </table>
        </div>
        <div class="table-wrap">
          <h3>All Payments</h3>
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Broker</th>
                <th>Asset</th>
                <th>ISIN</th>
                <th>Net EUR</th>
                <th>Tax EUR</th>
                <th>Gross EUR</th>
              </tr>
            </thead>
            <tbody id="dividends"></tbody>
          </table>
        </div>
      </div>
      </div>
    </section>

    <!-- Cash Account Interest -->
    <section>
      <div class="section-head" data-collapse="cash-interest-content" onclick="toggleSection(this)">
        <div class="section-head-left">
          <svg class="chevron" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z" clip-rule="evenodd"/></svg>
          <h2>Cash Account Interest</h2>
        </div>
        <span class="subtle" id="cash-interest-summary"></span>
      </div>
      <div class="section-content" id="cash-interest-content">
        <div class="section-body">
          <div class="table-wrap">
            <h3>Summary by Broker</h3>
            <table>
              <thead>
                <tr>
                  <th>Broker</th>
                  <th>Payments</th>
                  <th>Net EUR</th>
                  <th>Tax EUR</th>
                  <th>Gross EUR</th>
                </tr>
              </thead>
              <tbody id="cash-interest-broker"></tbody>
            </table>
          </div>
          <div class="table-wrap">
            <h3>All Payments</h3>
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Broker</th>
                  <th>Net EUR</th>
                  <th>Tax EUR</th>
                  <th>Gross EUR</th>
                  <th>Description</th>
                </tr>
              </thead>
              <tbody id="cash-interest-payments"></tbody>
            </table>
          </div>
        </div>
      </div>
    </section>

    <!-- Expenses -->
    <section class="section-support" id="expenses-section">
      <div class="section-head" data-collapse="expenses-content" onclick="toggleSection(this)">
        <div class="section-head-left">
          <svg class="chevron" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z" clip-rule="evenodd"/></svg>
          <h2>Expenses</h2>
        </div>
        <span class="subtle" id="expenses-summary"></span>
      </div>
      <div class="section-content" id="expenses-content">
        <div class="section-body">
          <div class="expense-summary" id="expense-metrics"></div>
          <div class="expense-grid">
            <div class="table-wrap">
              <h3>Top Categories</h3>
              <table>
                <thead>
                  <tr>
                    <th>Category</th>
                    <th>Rows</th>
                    <th>Amount EUR</th>
                    <th>Share</th>
                  </tr>
                </thead>
                <tbody id="expense-categories"></tbody>
              </table>
            </div>
            <div class="expense-chart-card">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                <h3 style="margin: 0;">Expense Trend</h3>
                <div class="periods secondary-selector" id="expense-trend-mode" aria-label="Expense trend mode" style="padding: 2px; border-radius: 7px; background: rgba(15,23,42,0.34); display: flex;">
                  <button type="button" id="expense-toggle-monthly" class="active" style="min-height: 22px; padding: 2px 8px; font-size: 11px; font-weight: 500; border-radius: 5px; background: var(--blue); color: white; border: none; cursor: pointer;">Monthly</button>
                  <button type="button" id="expense-toggle-cumulative" style="min-height: 22px; padding: 2px 8px; font-size: 11px; font-weight: 500; border-radius: 5px; background: transparent; color: var(--text-sub, #94a3b8); border: none; cursor: pointer;">Cumulative</button>
                </div>
              </div>
              <div id="expense-trend-legend" style="display: flex; gap: 12px; font-size: 11px; margin-bottom: 8px; align-items: center;"></div>
              <svg class="expense-chart" id="expense-trend" role="img" aria-label="Monthly expense trend"></svg>
            </div>
            <div class="table-wrap">
              <h3>Source Breakdown</h3>
              <table>
                <thead>
                  <tr>
                    <th>Source</th>
                    <th>Rows</th>
                    <th>Outflow</th>
                    <th>Income</th>
                    <th>Credits</th>
                    <th>Net Outflow</th>
                  </tr>
                </thead>
                <tbody id="expense-sources"></tbody>
              </table>
            </div>
            <div class="table-wrap">
              <h3>Top Merchants</h3>
              <table>
                <thead>
                  <tr>
                    <th>Merchant</th>
                    <th>Category</th>
                    <th>Rows</th>
                    <th>Amount EUR</th>
                  </tr>
                </thead>
                <tbody id="expense-merchants"></tbody>
              </table>
            </div>
          </div>
          <div class="table-wrap">
            <h3>Credits</h3>
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Source</th>
                  <th>Subcategory</th>
                  <th>Merchant</th>
                  <th>Amount EUR</th>
                </tr>
              </thead>
              <tbody id="expense-credits"></tbody>
            </table>
          </div>
          <div class="table-wrap">
            <h3>Recent Rows</h3>
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Source</th>
                  <th>Category</th>
                  <th>Merchant</th>
                  <th>Description</th>
                  <th>Amount EUR</th>
                </tr>
              </thead>
              <tbody id="expense-rows"></tbody>
            </table>
          </div>
        </div>
      </div>
    </section>

    <!-- Net Contributions -->
    <section>
      <div class="section-head" data-collapse="contributions-content" onclick="toggleSection(this)">
        <div class="section-head-left">
          <svg class="chevron" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z" clip-rule="evenodd"/></svg>
          <h2>Net Contributions</h2>
        </div>
        <span class="subtle" id="contributions-summary"></span>
      </div>
      <div class="section-content" id="contributions-content">
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Broker</th>
                <th>Buys EUR</th>
                <th>Sells EUR</th>
                <th>Net EUR</th>
                <th>Share</th>
              </tr>
            </thead>
            <tbody id="contributions-broker"></tbody>
          </table>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Buys EUR</th>
                <th>Sells EUR</th>
                <th>Net EUR</th>
              </tr>
            </thead>
            <tbody id="contributions-date"></tbody>
          </table>
        </div>
      </div>
    </section>

    <!-- Taxes & Costs -->
    <section>
      <div class="section-head" data-collapse="frictions-content" onclick="toggleSection(this)">
        <div class="section-head-left">
          <svg class="chevron" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z" clip-rule="evenodd"/></svg>
          <h2>Taxes &amp; Costs</h2>
        </div>
        <span class="subtle" id="frictions-summary"></span>
      </div>
      <div class="section-content" id="frictions-content">
        <div class="section-body">
          <div class="friction-summary" id="friction-metrics"></div>
          <div class="info-box">
            <strong>How liquidation is calculated:</strong>
            Taxes paid include trade taxes, portfolio/stamp taxes, and dividend withholding. Costs paid include parsed investment broker commissions and spread/overnight costs. Total drag is taxes plus costs. Net liquidation is current market value minus total drag for the selected window.
          </div>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Broker</th>
                  <th>Costs EUR</th>
                  <th>Taxes EUR</th>
                  <th>Dividend Tax EUR</th>
                  <th>Total EUR</th>
                </tr>
              </thead>
              <tbody id="frictions-broker"></tbody>
            </table>
          </div>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Broker</th>
                  <th>Type</th>
                  <th>Description</th>
                  <th>Amount EUR</th>
                </tr>
              </thead>
              <tbody id="frictions-events"></tbody>
            </table>
          </div>
          <div id="tax-losses-wrap" style="display:none; margin-top: 20px; border-top: 1px solid var(--line); padding-top: 20px;">
            <h3 style="font-size: 14px; font-weight: 600; margin-bottom: 12px; color: var(--ink);">Tax Loss Carry-forwards (Minusvalenze)</h3>
            <div class="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Year Formed</th>
                    <th>Broker</th>
                    <th>Available Carry-forward</th>
                    <th>Expiration Date</th>
                  </tr>
                </thead>
                <tbody id="tax-losses-tbody"></tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Portfolio Statistics -->
    <section id="stats-section" style="display:none;">
      <div class="section-head" data-collapse="stats-content" onclick="toggleSection(this)">
        <div class="section-head-left">
          <svg class="chevron" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z" clip-rule="evenodd"/></svg>
          <h2>Portfolio Statistics</h2>
        </div>
        <span class="subtle" id="stats-summary"></span>
      </div>
      <div class="section-content" id="stats-content">
        <div class="section-body">
          <div class="info-box" style="margin-bottom:15px;" id="stats-info">
            <strong>Volatility & Risk Summary:</strong>
            Daily variance, standard deviation (volatility), and annualized volatility are calculated using the strictly daily business-day return series of the portfolio and the MSCI World index. Sharpe ratio is annualized assuming a 3.0% risk-free rate.
          </div>
          <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(280px, 1fr)); gap:15px;">
            <div class="table-wrap">
              <h3>Your Portfolio</h3>
              <table>
                <tbody>
                  <tr><td style="text-align:left; font-weight:600;">Mean Daily Return</td><td id="stats-port-mean" style="text-align:right; font-weight:600;">-</td></tr>
                  <tr><td style="text-align:left;">Daily Return Variance</td><td id="stats-port-var" style="text-align:right;">-</td></tr>
                  <tr><td style="text-align:left;">Daily Volatility (Std Dev)</td><td id="stats-port-daily-vol" style="text-align:right;">-</td></tr>
                  <tr><td style="text-align:left; font-weight:600; color:var(--blue);">Annualized Volatility</td><td id="stats-port-ann-vol" style="text-align:right; font-weight:600; color:var(--blue);">-</td></tr>
                  <tr><td style="text-align:left; font-weight:600; color:var(--green);">Annualized Sharpe Ratio</td><td id="stats-port-sharpe" style="text-align:right; font-weight:600; color:var(--green);">-</td></tr>
                </tbody>
              </table>
            </div>
            <div class="table-wrap">
              <h3>Benchmark: MSCI World</h3>
              <table>
                <tbody>
                  <tr><td style="text-align:left; font-weight:600;">Mean Daily Return</td><td id="stats-msci-mean" style="text-align:right; font-weight:600;">-</td></tr>
                  <tr><td style="text-align:left;">Daily Return Variance</td><td id="stats-msci-var" style="text-align:right;">-</td></tr>
                  <tr><td style="text-align:left;">Daily Volatility (Std Dev)</td><td id="stats-msci-daily-vol" style="text-align:right;">-</td></tr>
                  <tr><td style="text-align:left; font-weight:600; color:var(--blue);">Annualized Volatility</td><td id="stats-msci-ann-vol" style="text-align:right; font-weight:600; color:var(--blue);">-</td></tr>
                  <tr><td style="text-align:left; font-weight:600; color:var(--green);">Annualized Sharpe Ratio</td><td id="stats-msci-sharpe" style="text-align:right; font-weight:600; color:var(--green);">-</td></tr>
                </tbody>
              </table>
            </div>
            <div class="table-wrap">
              <h3>Benchmark: XEON (Cash)</h3>
              <table>
                <tbody>
                  <tr><td style="text-align:left; font-weight:600;">Mean Daily Return</td><td id="stats-xeon-mean" style="text-align:right; font-weight:600;">-</td></tr>
                  <tr><td style="text-align:left;">Daily Return Variance</td><td id="stats-xeon-var" style="text-align:right;">-</td></tr>
                  <tr><td style="text-align:left;">Daily Volatility (Std Dev)</td><td id="stats-xeon-daily-vol" style="text-align:right;">-</td></tr>
                  <tr><td style="text-align:left; font-weight:600; color:var(--blue);">Annualized Volatility</td><td id="stats-xeon-ann-vol" style="text-align:right; font-weight:600; color:var(--blue);">-</td></tr>
                  <tr><td style="text-align:left; font-weight:600; color:var(--green);">Annualized Sharpe Ratio</td><td id="stats-xeon-sharpe" style="text-align:right; font-weight:600; color:var(--green);">-</td></tr>
                </tbody>
              </table>
            </div>
          </div>
          <div class="stats-distribution">
            <div class="stats-distribution-head">
              <div>
                <h3>Daily Return Distributions</h3>
                <span class="subtle" id="stats-dist-summary"></span>
              </div>
              <div class="distribution-legend" aria-hidden="true">
                <span><span class="legend-dot portfolio"></span>Portfolio</span>
                <span><span class="legend-dot msci"></span>MSCI World</span>
              </div>
            </div>
            <div class="return-distribution-grid">
              <div class="return-distribution-card">
                <div class="return-distribution-card-head">
                  <strong>Portfolio Daily Returns</strong>
                  <span class="return-distribution-meta" id="stats-port-dist-meta"></span>
                </div>
                <svg id="stats-port-dist" role="img" aria-label="Portfolio daily return distribution"></svg>
              </div>
              <div class="return-distribution-card">
                <div class="return-distribution-card-head">
                  <strong>MSCI World Daily Returns</strong>
                  <span class="return-distribution-meta" id="stats-msci-dist-meta"></span>
                </div>
                <svg id="stats-msci-dist" role="img" aria-label="MSCI World daily return distribution"></svg>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Pricing Coverage -->
    <section>
      <div class="section-head" data-collapse="coverage-content" onclick="toggleSection(this)">
        <div class="section-head-left">
          <svg class="chevron" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z" clip-rule="evenodd"/></svg>
          <h2>Pricing Coverage</h2>
        </div>
        <span class="subtle" id="coverage-text"></span>
      </div>
      <div class="section-content" id="coverage-content">
        <div class="mapping">
          <div class="bar"><span id="coverage-bar" style="width:0%"></span></div>
          <div id="mapping-status"></div>
        </div>
      </div>
    </section>
    <!-- Optional per-portfolio actions loaded from private configuration. -->
    <section id="todos-section" style="display:none;">
      <div class="section-head expanded" data-collapse="todos-content" onclick="toggleSection(this)">
        <div class="section-head-left">
          <svg class="chevron" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z" clip-rule="evenodd"/></svg>
          <h2>Suggested Actions &amp; To-Dos</h2>
        </div>
      </div>
      <div class="section-content expanded" id="todos-content">
        <div class="section-body">
          <ul id="todos-list" style="margin: 0; padding-left: 20px; line-height: 1.6; color: var(--ink-secondary);">
            <!-- Populated via JS -->
          </ul>
        </div>
      </div>
    </section>
    <section class="export-panel" aria-label="Export dashboard">
      <div class="export-copy">
        <span class="section-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24"><path d="M12 3v12"/><path d="M8 11l4 4 4-4"/><path d="M5 19h14"/></svg>
        </span>
        <div class="export-copy-text">
          <strong>Export current view</strong>
          <span class="subtle" id="export-summary">Uses the selected person, window, broker, Berkshire mode, proxy mode, and live filter.</span>
        </div>
      </div>
      <div class="export-actions">
        <select id="export-format" aria-label="Export format">
          <option value="pdf">PDF</option>
          <option value="xlsx">XLSX</option>
        </select>
        <button type="button" id="export-button">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v12"/><path d="M8 11l4 4 4-4"/><path d="M5 20h14"/></svg>
          <span>Export</span>
        </button>
      </div>
    </section>
    
    <!-- Info Modal -->
    <div id="info-modal" style="display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; background-color: rgba(12, 15, 26, 0.8); backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px); align-items: center; justify-content: center; opacity: 0; transition: opacity 0.2s ease;">
      <div style="background: var(--bg-secondary); border: 1px solid var(--line-strong); border-radius: var(--radius); max-width: 600px; width: 90%; max-height: 85vh; overflow-y: auto; padding: 24px; box-shadow: var(--shadow-lg); position: relative; color: var(--ink);">
        <button type="button" onclick="closeInfoModal()" style="position: absolute; right: 16px; top: 16px; background: transparent; border: none; font-size: 20px; cursor: pointer; color: var(--muted); line-height: 1;">&times;</button>
        <h3 id="modal-title" style="font-size: 18px; font-weight: 700; margin-bottom: 16px; color: var(--ink); border-bottom: 1px solid var(--line); padding-bottom: 10px;"></h3>
        <div id="modal-content" style="line-height: 1.6; font-size: 13.5px; color: var(--ink-secondary);"></div>
        <div style="margin-top: 24px; display: flex; justify-content: flex-end;">
          <button type="button" onclick="closeInfoModal()" style="background: var(--panel-hover); border: 1px solid var(--line-strong); border-radius: var(--radius-sm); padding: 8px 16px; color: var(--ink); cursor: pointer; font-size: 13px; font-weight: 500;">Close</button>
        </div>
      </div>
    </div>
  </main>
  <script>
    /* ─── Info Modals & Popups ─── */
    window.showAssetInfoPopup = function(type, event) {
      if (event) {
        event.preventDefault();
        event.stopPropagation();
      }
      if (type === 'europension') {
        const title = "Mediolanum Europension TaxBenefit Previdenza";
        const content = `
          <p style="margin-bottom: 12px;"><strong>What it is:</strong> A private individual pension plan (<em>PIP - Piano Individuale Pensionistico</em>) offered by Banca Mediolanum.</p>
          <p style="margin-bottom: 12px;"><strong>Tax Advantage:</strong> Annual contributions are fully deductible from taxable income up to a maximum of <strong>€5.164,57</strong>. At a 43% marginal tax bracket, this yields an immediate <strong>+75.4% return</strong> (saving €2.220 in taxes on a €2.943 net outlay).</p>
          <div style="background: rgba(245, 158, 11, 0.08); border-left: 3px solid var(--amber); padding: 12px; margin-bottom: 16px; border-radius: 4px; font-size: 13px; color: var(--ink-secondary);">
            <strong style="color: var(--amber);">Management Fee Drag Compounding Impact:</strong>
            <p style="margin-top: 6px; margin-bottom: 0;">Traditional PIPs have an annual management cost (ISC) of <strong>~2.0%</strong>. A low-cost alternative Open Pension Fund (FPA) like <em>Amundi SecondaPensione</em> has a fee of only <strong>~0.8%</strong>.</p>
            <p style="margin-top: 6px; margin-bottom: 0;">Over a 15-year period on €5.164 annual contributions:</p>
            <ul style="margin: 6px 0 0 16px; padding: 0;">
              <li><strong>Standard FPA (~0.8% fee)</strong>: yields <strong>~€120.000</strong> net payout</li>
              <li><strong>Traditional PIP (~2.0% fee)</strong>: yields <strong>~€108.000</strong> net payout</li>
            </ul>
            <p style="margin-top: 6px; margin-bottom: 0; font-weight: 500; color: var(--ink);">Transferring this policy to a low-cost FPA saves ~€12.000 in lost fees while fully preserving the tax deduction!</p>
          </div>
        `;
        showInfoModal(title, content);
      } else if (type === 'mystyle') {
        const title = "Managed Product Fee Analysis";
        const content = `
          <p style="margin-bottom: 12px;"><strong>What it is:</strong> A multi-fund insurance wrapper can combine product-level charges with the costs of its underlying funds.</p>
          <p style="margin-bottom: 12px;"><strong>Why compare fees:</strong> Small annual cost differences compound over long holding periods. Use the calculator with the fees and capital from your own documents.</p>
          <div style="background: rgba(239, 68, 68, 0.08); border-left: 3px solid var(--red); padding: 12px; margin-bottom: 16px; border-radius: 4px; font-size: 13px; color: var(--ink-secondary);">
            <strong style="color: var(--red);">Illustrative comparison only</strong>
            <p style="margin-top: 6px; margin-bottom: 0;">The calculator does not include taxes, trading costs, guarantees, insurance benefits, or changes in future returns. It is not investment advice.</p>
          </div>
          <p style="margin-bottom: 0;">Actual statement charges belong in the private portfolio configuration and appear in the dashboard's Frictions section.</p>
        `;
        showInfoModal(title, content);
      }
    };
    
    window.showInfoModal = function(title, html) {
      const modal = document.getElementById("info-modal");
      document.getElementById("modal-title").innerHTML = title;
      document.getElementById("modal-content").innerHTML = html;
      modal.style.display = "flex";
      // Force reflow
      modal.offsetHeight;
      modal.style.opacity = "1";
    };
    
    window.closeInfoModal = function() {
      const modal = document.getElementById("info-modal");
      modal.style.opacity = "0";
      modal.addEventListener("transitionend", function handler() {
        if (modal.style.opacity === "0") {
          modal.style.display = "none";
        }
        modal.removeEventListener("transitionend", handler);
      }, { once: true });
    };

    /* ─── Collapsible section toggle ─── */
    function toggleSection(header) {
      const targetId = header.dataset.collapse;
      const content = document.getElementById(targetId);
      if (!content) return;
      const isExpanded = content.classList.contains('expanded');
      if (isExpanded) {
        content.style.maxHeight = content.scrollHeight + 'px';
        requestAnimationFrame(() => {
          content.style.maxHeight = '0';
          content.classList.remove('expanded');
        });
        header.classList.remove('expanded');
      } else {
        content.classList.add('expanded');
        content.style.maxHeight = content.scrollHeight + 'px';
        header.classList.add('expanded');
        content.addEventListener('transitionend', function handler() {
          content.style.maxHeight = '';
          content.removeEventListener('transitionend', handler);
          scheduleChartResize();
        });
        requestAnimationFrame(scheduleChartResize);
      }
    }
    function sectionIconSvg(name) {
      const icons = {
        value: `<svg viewBox="0 0 24 24"><path d="M4 18V6"/><path d="M4 16l5-5 4 3 7-8"/><path d="M15 6h5v5"/></svg>`,
        flow: `<svg viewBox="0 0 24 24"><path d="M4 7h11a4 4 0 0 1 0 8H8"/><path d="M8 11l-4 4 4 4"/><path d="M17 4l3 3-3 3"/></svg>`,
        holdings: `<svg viewBox="0 0 24 24"><path d="M5 7h14"/><path d="M5 12h14"/><path d="M5 17h14"/><path d="M9 7v10"/></svg>`,
        calculator: `<svg viewBox="0 0 24 24"><rect x="5" y="3" width="14" height="18" rx="2"/><path d="M8 7h8"/><path d="M8 11h2"/><path d="M14 11h2"/><path d="M8 15h2"/><path d="M14 15h2"/></svg>`,
        layers: `<svg viewBox="0 0 24 24"><path d="M12 3l8 4-8 4-8-4 8-4Z"/><path d="M4 12l8 4 8-4"/><path d="M4 17l8 4 8-4"/></svg>`,
        watch: `<svg viewBox="0 0 24 24"><path d="M12 5l2.2 4.5 5 .7-3.6 3.5.8 5-4.4-2.3-4.4 2.3.8-5-3.6-3.5 5-.7L12 5Z"/></svg>`,
        news: `<svg viewBox="0 0 24 24"><path d="M4 6h14v12H4z"/><path d="M18 9h2v9a2 2 0 0 1-2 2"/><path d="M7 9h8"/><path d="M7 13h8"/><path d="M7 17h5"/></svg>`,
        distribution: `<svg viewBox="0 0 24 24"><path d="M12 3v18"/><path d="M12 12l8-5"/><path d="M12 12l8 5"/><circle cx="12" cy="12" r="2"/><circle cx="20" cy="7" r="2"/><circle cx="20" cy="17" r="2"/><circle cx="4" cy="12" r="2"/></svg>`,
        income: `<svg viewBox="0 0 24 24"><path d="M12 3v18"/><path d="M16 7.5a4 4 0 0 0-4-2c-2 0-3.5 1-3.5 2.6 0 3.8 7 1.8 7 5.8 0 1.8-1.6 3.1-3.8 3.1a5.2 5.2 0 0 1-4.2-2"/></svg>`,
        cash: `<svg viewBox="0 0 24 24"><rect x="4" y="7" width="16" height="10" rx="2"/><circle cx="12" cy="12" r="2"/><path d="M7 10v4"/><path d="M17 10v4"/></svg>`,
        contribution: `<svg viewBox="0 0 24 24"><path d="M12 4v16"/><path d="M8 8l4-4 4 4"/><path d="M4 16h16"/></svg>`,
        risk: `<svg viewBox="0 0 24 24"><path d="M12 3l9 16H3L12 3Z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>`,
        stats: `<svg viewBox="0 0 24 24"><path d="M5 19V5"/><path d="M5 19h14"/><path d="M8 16v-4"/><path d="M12 16V8"/><path d="M16 16v-6"/></svg>`,
        coverage: `<svg viewBox="0 0 24 24"><path d="M12 3l7 3v5c0 4.5-2.8 8-7 10-4.2-2-7-5.5-7-10V6l7-3Z"/><path d="M8.5 12l2.2 2.2L15.8 9"/></svg>`,
        todo: `<svg viewBox="0 0 24 24"><path d="M5 6h14"/><path d="M5 12h14"/><path d="M5 18h9"/><path d="M16 17l2 2 4-4"/></svg>`,
        panel: `<svg viewBox="0 0 24 24"><rect x="4" y="5" width="16" height="14" rx="2"/><path d="M4 10h16"/></svg>`
      };
      return icons[name] || icons.panel;
    }
    function initializeSectionIdentity() {
      const accents = {
        blue: ["#60a5fa", "rgba(96,165,250,0.09)"],
        teal: ["#2dd4bf", "rgba(45,212,191,0.08)"],
        green: ["#34d399", "rgba(52,211,153,0.08)"],
        amber: ["#fbbf24", "rgba(251,191,36,0.08)"],
        violet: ["#a78bfa", "rgba(167,139,250,0.08)"],
        red: ["#f87171", "rgba(248,113,113,0.07)"],
        slate: ["rgba(148,163,184,0.70)", "rgba(148,163,184,0.06)"]
      };
      const config = {
        "Portfolio Value": { tier: "primary", accent: "blue", icon: "value" },
        "Cash Flow Evolution": { tier: "core", accent: "teal", icon: "flow" },
        "Current Holdings": { tier: "core", accent: "green", icon: "holdings" },
        "MyStyle Fee Drag Calculator": { tier: "risk", accent: "amber", icon: "calculator" },
        "MyStyle Portfolio Breakdown": { tier: "risk", accent: "amber", icon: "layers" },
        "Watchlist": { tier: "support", accent: "violet", icon: "watch" },
        "Stock News": { tier: "support", accent: "slate", icon: "news" },
        "Portfolio Distribution": { tier: "core", accent: "violet", icon: "distribution" },
        "Dividends": { tier: "support", accent: "green", icon: "income" },
        "Cash Account Interest": { tier: "support", accent: "teal", icon: "cash" },
        "Net Contributions": { tier: "support", accent: "blue", icon: "contribution" },
        "Taxes & Costs": { tier: "risk", accent: "amber", icon: "risk" },
        "Portfolio Statistics": { tier: "core", accent: "blue", icon: "stats" },
        "Pricing Coverage": { tier: "system", accent: "slate", icon: "coverage" },
        "Suggested Actions & To-Dos": { tier: "risk", accent: "amber", icon: "todo" }
      };

      document.querySelectorAll(".section-head[data-collapse]").forEach(header => {
        const title = header.querySelector("h2")?.textContent?.trim() || "";
        const item = config[title] || { tier: "support", accent: "slate", icon: "panel" };
        const section = header.closest("section");
        if (!section) return;
        const [accent, accentSoft] = accents[item.accent] || accents.slate;
        section.classList.add(`section-${item.tier}`);
        section.style.setProperty("--section-accent", accent);
        section.style.setProperty("--section-accent-soft", accentSoft);

        const left = header.querySelector(".section-head-left");
        const heading = left?.querySelector("h2");
        if (!left || !heading || left.querySelector(".section-icon")) return;
        const icon = document.createElement("span");
        icon.className = "section-icon";
        icon.setAttribute("aria-hidden", "true");
        icon.innerHTML = sectionIconSvg(item.icon);
        left.insertBefore(icon, heading);
      });
    }
    function initializeSectionWrapButtons() {
      document.querySelectorAll(".section-content[id]").forEach(content => {
        if (content.querySelector(".section-wrap-up")) return;
        const header = [...document.querySelectorAll(".section-head[data-collapse]")]
          .find(item => item.dataset.collapse === content.id);
        if (!header) return;

        const sectionTitle = header.querySelector("h2")?.textContent?.trim() || "section";
        const wrap = document.createElement("div");
        wrap.className = "section-wrap-up";
        wrap.innerHTML = `
          <button type="button" class="section-wrap-button" aria-label="Collapse ${escapeHtml(sectionTitle)}">
            <span class="section-wrap-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24"><path d="M6 15l6-6 6 6"/></svg>
            </span>
            <span>Wrap up</span>
          </button>
        `;
        wrap.querySelector("button").addEventListener("click", event => {
          event.preventDefault();
          event.stopPropagation();
          if (content.classList.contains("expanded")) {
            event.currentTarget.blur();
            toggleSection(header);
          }
        });
        content.appendChild(wrap);
      });
    }
    let dashboardData = null;
    let rankingsData = null;
    let rankingsSort = { key: "common", direction: "desc" };
    let selectedExpenseTrendMode = "monthly";
    const PRIMARY_PORTFOLIO_ID = __PRIMARY_PORTFOLIO_ID__;
    let selectedPerson = PRIMARY_PORTFOLIO_ID;
    let selectedPeriod = "since24";
    let selectedBerkshireMode = "stock";
    let selectedProxyMode = "on";
    let selectedLiveMode = "all";
    let selectedReturnMode = "price";
    let chartResizeTimer = null;
    let sortState = { key: "market_value_eur", direction: "desc" };
    let variationMode = "pct";
    let selectedBroker = "all";
    let showAllHoldings = false;
    let showClosed = false;
    let activeMoversPeriod = null;
    let selectedDistributionSource = "";
    let loadRequestId = 0;
    let redrawTimer = null;

    function setRefreshLabel(label) {
      const status = document.getElementById("refresh-status");
      if (status) status.textContent = label || "Updating dashboard";
    }
    function setDashboardBusy(isBusy, label = "Updating dashboard") {
      window.clearTimeout(redrawTimer);
      document.body.classList.remove("dashboard-redrawing");
      setRefreshLabel(label);
      document.body.classList.toggle("dashboard-refreshing", isBusy);
    }
    function withRedrawVeil(label, renderFn) {
      if (document.body.classList.contains("dashboard-refreshing")) {
        renderFn();
        return;
      }
      window.clearTimeout(redrawTimer);
      setRefreshLabel(label);
      document.body.classList.add("dashboard-redrawing");
      requestAnimationFrame(() => {
        renderFn();
        redrawTimer = window.setTimeout(() => {
          document.body.classList.remove("dashboard-redrawing");
        }, 240);
      });
    }
    function resetHoldingsView() {
      showAllHoldings = false;
      showClosed = false;
    }

    function toggleVariationMode() {
      variationMode = variationMode === "pct" ? "amount" : "pct";
      if (dashboardData) {
        renderMetrics(periodMetrics(dashboardData));
        renderMoversPanel();
      }
    }
    const cashVisibility = {
      invested: true,
      net_contributions: true,
      open_cost_basis: true,
      proceeds: true,
      realized_pl: true
    };
    const returnVisibility = {
      return_pct: true,
      msci_return_pct: false,
      xeon_return_pct: false,
      inflation_return_pct: false,
      weighted_score: false,
      freq_score: false
    };
    let showTransactions = true;
    let showAllTransactions = false;
    const returnDefs = [
      ["return_pct", "Return %", "series-return"],
      ["msci_return_pct", "MSCI World %", "series-msci"],
      ["xeon_return_pct", "XEON (Cash) %", "series-xeon"],
      ["inflation_return_pct", "Inflation %", "series-inflation"],
      ["weighted_score", "Area > MSCI %", "series-weighted"],
      ["freq_score", "Time > MSCI %", "series-freq"]
    ];
    const metricDefs = [
      ["market_value", "Market value"],
      ["return_pct", "Return"],
      ["open_cost_basis", "Open cost"],
      ["unrealized_pl", "Unrealized P/L"],
      ["realized_pl", "Realized P/L"],
      ["net_contributions", "Net contributions"]
    ];
    const chartDefs = [
      ["invested", "Invested", "series-invested"],
      ["net_contributions", "Net contributions", "series-net"],
      ["open_cost_basis", "Open cost basis", "series-cost"],
      ["proceeds", "Proceeds", "series-proceeds"],
      ["realized_pl", "Realized P/L", "series-realized"]
    ];
    const euro = new Intl.NumberFormat("en-IE", { style: "currency", currency: "EUR" });
    const euroWhole = new Intl.NumberFormat("en-IE", { style: "currency", currency: "EUR", maximumFractionDigits: 0 });
    const num = new Intl.NumberFormat("en-IE", { maximumFractionDigits: 4 });
    const pct = new Intl.NumberFormat("en-IE", { maximumFractionDigits: 2, minimumFractionDigits: 2 });

    function money(value) {
      if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
      return euro.format(Number(value));
    }
    function moneyWhole(value) {
      if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
      return euroWhole.format(Number(value));
    }
    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>"']/g, char => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
      }[char]));
    }
    function percent(value) {
      if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
      return `${pct.format(Number(value))}%`;
    }
    function signedClass(value) {
      const n = Number(value || 0);
      if (n > 0) return "positive";
      if (n < 0) return "negative";
      return "";
    }
    function renderMetrics(totals) {
      const v = totals.variations || {
        "1d": { pct: 0.0, amount: 0.0 },
        "1w": { pct: 0.0, amount: 0.0 },
        "1m": { pct: 0.0, amount: 0.0 }
      };

      const marketValueHtml = `
        <div class="metric">
          <span>Market value</span>
          <strong>${moneyWhole(totals.market_value)}</strong>
        </div>
      `;

      const variationHtml = ["1d", "1w", "1m"].map(period => {
        const val = v[period] || { pct: 0.0, amount: 0.0 };
        const displayVal = variationMode === "pct" 
          ? `${val.pct >= 0 ? "+" : ""}${pct.format(val.pct)}%` 
          : `${val.amount >= 0 ? "+" : ""}${moneyWhole(val.amount)}`;
        const colorClass = signedClass(val.amount);
        const hasMsci = val.msci_pct !== null && val.msci_pct !== undefined && Number.isFinite(Number(val.msci_pct));
        const hasVsMsci = val.vs_msci_pct !== null && val.vs_msci_pct !== undefined && Number.isFinite(Number(val.vs_msci_pct));
        const msciVal = hasMsci ? Number(val.msci_pct) : null;
        const vsMsciVal = hasVsMsci ? Number(val.vs_msci_pct) : null;
        const msciText = hasMsci ? `${msciVal >= 0 ? "+" : ""}${pct.format(msciVal)}%` : "-";
        const vsMsciText = hasVsMsci ? `${vsMsciVal >= 0 ? "+" : ""}${pct.format(vsMsciVal)} pp` : "-";
        const msciClass = signedClass(msciVal);
        const vsMsciClass = signedClass(vsMsciVal);
        const activeClass = activeMoversPeriod === period ? "active" : "";
        return `
          <div class="metric clickable" onclick="toggleVariationMode()" title="Click to toggle % / €">
            <div class="metric-label-row">
              <span>${period.toUpperCase()} Var</span>
              <button type="button" class="metric-plus ${activeClass}" onclick="toggleMovers('${period}', event)" aria-label="Show ${period.toUpperCase()} movers" title="Show ${period.toUpperCase()} movers">+</button>
            </div>
            <strong class="${colorClass}">${displayVal}</strong>
            <div class="metric-benchmark">
              <span>MSCI <span class="${msciClass}">${msciText}</span></span>
              <span class="${vsMsciClass}">${vsMsciText}</span>
            </div>
          </div>
        `;
      }).join("");

      const restHtml = metricDefs.slice(1).map(([key, label]) => `
        <div class="metric">
          <span>${label}</span>
          <strong class="${signedClass(key.includes("pl") || key.includes("pct") ? totals[key] : 0)}">${key.includes("pct") ? percent(totals[key]) : moneyWhole(totals[key])}</strong>
        </div>
      `).join("");

      document.getElementById("metrics").innerHTML = marketValueHtml + restHtml + variationHtml;
      renderMoversPanel();
    }
    function periodLabel(period) {
      if (period === "1d") return "1D";
      if (period === "1w") return "1W";
      if (period === "1m") return "1M";
      return String(period || "").toUpperCase();
    }
    function toggleMovers(period, event) {
      if (event) {
        event.preventDefault();
        event.stopPropagation();
      }
      activeMoversPeriod = activeMoversPeriod === period ? null : period;
      if (dashboardData) renderMetrics(periodMetrics(dashboardData));
    }
    function positionMovers(period) {
      if (!dashboardData) return [];
      return (dashboardData.positions || [])
        .filter(p => p && p.is_open && ["STOCK", "ETF"].includes(String(p.asset_type || "").toUpperCase()))
        .map(p => {
          const variation = (p.variations || {})[period] || {};
          const amount = Number(variation.amount || 0);
          const pctMove = Number(variation.pct || 0);
          return {
            asset: p.asset || p.symbol || "",
            symbol: p.symbol || p.isin || "",
            type: String(p.asset_type || "").toUpperCase(),
            amount,
            pct: pctMove
          };
        })
        .filter(row => row.asset && Number.isFinite(row.amount) && Number.isFinite(row.pct) && (row.amount !== 0 || row.pct !== 0));
    }
    function moverRowsHtml(rows) {
      if (!rows.length) return `<div class="empty-state">No stock or ETF movement data available for this window.</div>`;
      return rows.map(row => `
        <div class="mover-row">
          <div class="mover-name" title="${escapeHtml(row.asset)}">${escapeHtml(row.asset)}</div>
          <span class="mover-pill">${escapeHtml(row.type)}</span>
          <div class="mover-values">
            <strong class="${signedClass(row.amount)}">${row.pct >= 0 ? "+" : ""}${pct.format(row.pct)}%</strong>
            <small class="${signedClass(row.amount)}">${row.amount >= 0 ? "+" : ""}${money(row.amount)}</small>
          </div>
        </div>
      `).join("");
    }
    function renderMoversPanel() {
      const panel = document.getElementById("movers-panel");
      if (!panel) return;
      if (!activeMoversPeriod || !dashboardData) {
        panel.hidden = true;
        panel.innerHTML = "";
        return;
      }
      const movers = positionMovers(activeMoversPeriod);
      const byPct = [...movers].sort((a, b) => Math.abs(b.pct) - Math.abs(a.pct)).slice(0, 3);
      const byAmount = [...movers].sort((a, b) => Math.abs(b.amount) - Math.abs(a.amount)).slice(0, 3);
      const label = periodLabel(activeMoversPeriod);
      panel.hidden = false;
      panel.innerHTML = `
        <div class="movers-head">
          <strong>${label} stock/ETF movers</strong>
          <span class="subtle">Based on current holding value and cached/live price history</span>
        </div>
        <div class="movers-grid">
          <div class="movers-column">
            <h3>Top 3 by % move</h3>
            ${moverRowsHtml(byPct)}
          </div>
          <div class="movers-column">
            <h3>Top 3 by portfolio € move</h3>
            ${moverRowsHtml(byAmount)}
          </div>
        </div>
      `;
    }
    function filterByPeriod(series) {
      if (!series || !series.length) return series || [];
      if (selectedPeriod === "all") return series || [];
      if (selectedPeriod === "since24") return series.filter(p => new Date(p.date) >= new Date("2024-01-11"));
      
      const end = new Date(series[series.length - 1].date);
      const start = new Date(end);
      if (selectedPeriod === "ytd") {
        start.setMonth(0);
        start.setDate(1);
      }
      if (selectedPeriod === "1w") start.setDate(end.getDate() - 7);
      if (selectedPeriod === "1m") start.setMonth(end.getMonth() - 1);
      if (selectedPeriod === "1y") start.setFullYear(start.getFullYear() - 1);
      
      return series.filter(p => new Date(p.date) >= start);
    }
    function selectedWindowLabel() {
      if (selectedPeriod === "1w") return "Last 1 week";
      if (selectedPeriod === "1m") return "Last 1 month";
      if (selectedPeriod === "ytd") return "Year to date";
      if (selectedPeriod === "1y") return "Last 1 year";
      if (selectedPeriod === "since24") return "Since Jan 2024";
      return "All time";
    }
    function canUseSince24Window() {
      return selectedPerson === PRIMARY_PORTFOLIO_ID && selectedBroker === "all";
    }
    function defaultPeriodForSelection() {
      return canUseSince24Window() ? "since24" : "all";
    }
    function normalizeSelectedPeriod() {
      if (selectedPeriod === "since24" && !canUseSince24Window()) {
        selectedPeriod = "all";
      }
    }
    function updatePeriodButtons() {
      normalizeSelectedPeriod();
      document.querySelectorAll("#periods button").forEach(button => {
        const isSince24 = button.dataset.period === "since24";
        button.style.display = isSince24 && !canUseSince24Window() ? "none" : "";
        button.classList.toggle("active", selectedPeriod === button.dataset.period);
      });
    }
    function chartRangeLabel(series) {
      const filtered = filterByPeriod(series || []);
      if (!filtered.length) return selectedWindowLabel();
      return `${selectedWindowLabel()} | ${filtered[0].date} to ${filtered[filtered.length - 1].date}`;
    }
    function periodMetrics(data) {
      const totals = { ...data.totals };
      if (selectedReturnMode === "total") {
        totals.return_pct = totals.total_return_pct;
        totals.historical_profit = totals.historical_total_profit;
        totals.market_value = totals.total_market_value || totals.market_value;
      }
      const isPrimaryAll = (selectedPerson === PRIMARY_PORTFOLIO_ID && selectedPeriod === "all");
      if (selectedPeriod === "all" && !isPrimaryAll) return totals;

      const values = filterByPeriod(data.valuation_series || []);
      const cash = filterByPeriod(data.series || []);
      if (values.length >= 2) {
        const first = values[0];
        const last = values[values.length - 1];
        const p_last = Number(selectedReturnMode === "total" ? last.total_profit : last.profit || 0);
        const p_first = Number(selectedReturnMode === "total" ? first.total_profit : first.profit || 0);
        const periodProfit = p_last - p_first;
        const isTotal = (selectedReturnMode === "total");
        const periodContributions = Number(isTotal ? last.total_net_contributions : last.net_contributions || 0) - Number(isTotal ? first.total_net_contributions : first.net_contributions || 0);
        const startVal = Number(isTotal ? first.total_market_value : first.market_value || 0);
        const capitalAtWork = Math.max(0.01, startVal + Math.max(0, periodContributions));
        totals.market_value = Number(isTotal ? last.total_market_value : last.market_value || 0);
        totals.return_pct = periodProfit / capitalAtWork * 100;
        totals.historical_profit = periodProfit;
      }
      if (cash.length >= 2) {
        const first = cash[0];
        const last = cash[cash.length - 1];
        totals.realized_pl = Number(last.realized_pl || 0) - Number(first.realized_pl || 0);
        totals.net_contributions = Number(last.net_contributions || 0) - Number(first.net_contributions || 0);
      }
      return totals;
    }
    function pointPath(points, key, xScale, yScale) {
      return points.map((p, i) => `${i ? "L" : "M"}${xScale(p.date).toFixed(2)} ${yScale(Number(p[key] || 0)).toFixed(2)}`).join(" ");
    }
    function xTicks(series, count = 6) {
      if (series.length <= count) return series.map(p => p.date);
      const ticks = [];
      for (let i = 0; i < count; i++) {
        const idx = Math.round(i * (series.length - 1) / (count - 1));
        ticks.push(series[idx].date);
      }
      return [...new Set(ticks)];
    }
    function formatShortDate(value) {
      return new Date(value).toLocaleDateString("en-GB", { month: "short", year: "2-digit" });
    }
    /* Compute nice Y-axis bounds: auto-scale to data with 5% padding */
    function niceYRange(rawMin, rawMax, forceZero) {
      let lo = rawMin, hi = rawMax;
      if (forceZero) lo = Math.min(0, lo);
      if (lo === hi) { lo -= 1; hi += 1; }
      const pad = (hi - lo) * 0.05;
      lo -= pad;
      hi += pad;
      if (forceZero && lo > 0) lo = 0;
      return { minY: lo, maxY: hi };
    }
    /* Smart tick formatter: abbreviates large numbers (10k, 1.2M) */
    function smartTickFormat(value) {
      const abs = Math.abs(value);
      if (abs >= 1e6) return (value / 1e6).toFixed(1).replace(/\.0$/, '') + 'M';
      if (abs >= 1e4) return (value / 1e3).toFixed(0) + 'k';
      if (abs >= 1e3) return (value / 1e3).toFixed(1).replace(/\.0$/, '') + 'k';
      return Math.round(value).toString();
    }
    /* Get SVG dimensions from its container and set viewBox to match */
    function initSvgSize(svg) {
      const container = svg.closest(".chart-wrap") || svg;
      const rect = container.getBoundingClientRect();
      const w = Math.max(320, Math.round(rect.width));
      const h = Math.max(220, Math.round(rect.height));
      svg.setAttribute('viewBox', `0 0 ${w} ${h}`);
      svg.setAttribute('preserveAspectRatio', 'none');
      return { w, h };
    }

    function pointerToSvgX(svg, clientX, width) {
      const box = svg.getBoundingClientRect();
      if (!box.width) return 0;
      return (clientX - box.left) / box.width * width;
    }

    function addHover(svg, series, defs, xScale, yScale, width, height, topMargin, bottom, valueFormatter) {
      const hover = document.createElementNS("http://www.w3.org/2000/svg", "g");
      hover.style.display = "none";
      hover.innerHTML = `<line class="hover-line" y1="${topMargin}" y2="${height - bottom}"></line><text class="hover-label" x="66" y="${topMargin + 14}"></text>`;
      svg.appendChild(hover);
      const line = hover.querySelector("line");
      const label = hover.querySelector("text");
      const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
      const leftEdge = Math.max(0, Math.min(...series.map(point => xScale(point.date))));
      const rightEdge = Math.min(width, Math.max(...series.map(point => xScale(point.date))));
      rect.setAttribute("x", String(leftEdge));
      rect.setAttribute("y", String(topMargin));
      rect.setAttribute("width", String(Math.max(1, rightEdge - leftEdge)));
      rect.setAttribute("height", String(height - bottom - topMargin));
      rect.setAttribute("fill", "transparent");
      rect.style.cursor = "crosshair";
      rect.addEventListener("pointermove", event => {
        const viewX = pointerToSvgX(svg, event.clientX, width);
        let nearest = series[0];
        let nearestDistance = Infinity;
        for (const point of series) {
          const distance = Math.abs(xScale(point.date) - viewX);
          if (distance < nearestDistance) {
            nearest = point;
            nearestDistance = distance;
          }
        }
        const x = xScale(nearest.date);
        line.setAttribute("x1", x);
        line.setAttribute("x2", x);
        
        // Highlight transaction line if there is one on this date
        svg.querySelectorAll(".flow-event-line").forEach(l => l.classList.remove("highlighted"));
        const flowLine = svg.querySelector(`.flow-event-line[data-date="${nearest.date}"]`);
        if (flowLine) {
          flowLine.classList.add("highlighted");
        }
        
        let flowText = "";
        const idx = series.indexOf(nearest);
        if (idx > 0) {
          const prev = series[idx - 1];
          const isTotal = (selectedReturnMode === "total");
          const useTotal = isTotal && showAllTransactions;
          const prevContrib = Number(useTotal ? (prev.total_net_contributions || 0) : (prev.net_contributions || 0));
          const currContrib = Number(useTotal ? (nearest.total_net_contributions || 0) : (nearest.net_contributions || 0));
          const diff = currContrib - prevContrib;
          if (Math.abs(diff) > 0.01) {
            const flowAmt = Math.abs(diff);
            const formattedAmt = flowAmt.toLocaleString("it-IT", {minimumFractionDigits: 0, maximumFractionDigits: 2});
            if (useTotal) {
              flowText = diff > 0 
                ? `  ·  [Inflow: +€${formattedAmt}]` 
                : `  ·  [Outflow: -€${formattedAmt}]`;
            } else {
              flowText = diff > 0 
                ? `  ·  [Buy: +€${formattedAmt}]` 
                : `  ·  [Sell: -€${formattedAmt}]`;
            }
          }
        }
        const labelText = `${nearest.date}  ${defs.map(([key, name]) => `${name}: ${valueFormatter(Number(nearest[key] || 0), key)}`).join("  ·  ")}${flowText}`;
        label.textContent = labelText;
        /* Keep label inside chart */
        const textLen = label.getComputedTextLength ? label.getComputedTextLength() : 200;
        const maxLabelX = width - textLen - 10;
        label.setAttribute("x", String(Math.min(maxLabelX, Math.max(leftEdge + 8, x + 12))));
        hover.style.display = "block";
      });
      rect.addEventListener("pointerleave", () => {
        hover.style.display = "none";
        svg.querySelectorAll(".flow-event-line").forEach(l => l.classList.remove("highlighted"));
      });
      svg.appendChild(rect);
    }
    function renderLineChart(svgId, series, defs, formatTick = null) {
      const svg = document.getElementById(svgId);
      svg.innerHTML = "";
      if (!series.length) return;
      const { w, h } = initSvgSize(svg);
      const left = 60, right = 20, top = 22, bottom = 36;
      const dates = series.map(p => new Date(p.date).getTime());
      const values = [];
      series.forEach(p => defs.forEach(([key]) => values.push(Number(p[key] || 0))));
      const minX = Math.min(...dates), maxX = Math.max(...dates);
      /* Auto-scale Y to data range — only force zero for "all" period or when data crosses 0 */
      const rawMin = Math.min(...values), rawMax = Math.max(...values);
      const forceZero = selectedPeriod === 'all' || (rawMin < 0 && rawMax > 0);
      const { minY, maxY } = niceYRange(rawMin, rawMax, forceZero);
      const xScale = d => left + ((new Date(d).getTime() - minX) / Math.max(1, maxX - minX)) * (w - left - right);
      const yScale = v => top + (1 - ((v - minY) / Math.max(1, maxY - minY))) * (h - top - bottom);
      /* Draw zero-line if visible */
      if (minY <= 0 && maxY >= 0) {
        const axisY = yScale(0);
        svg.insertAdjacentHTML("beforeend", `<line class="axis" x1="${left}" y1="${axisY}" x2="${w-right}" y2="${axisY}" stroke-opacity="0.3"></line>`);
      }
      svg.insertAdjacentHTML("beforeend", `<line class="axis" x1="${left}" y1="${top}" x2="${left}" y2="${h-bottom}"></line>`);
      /* Y-axis ticks */
      const tickFmt = formatTick || smartTickFormat;
      const tickCount = 5;
      for (let i = 0; i <= tickCount; i++) {
        const t = i / tickCount;
        const y = top + t * (h - top - bottom);
        const value = maxY - t * (maxY - minY);
        svg.insertAdjacentHTML("beforeend", `<line class="grid-line" x1="${left}" y1="${y}" x2="${w-right}" y2="${y}"></line>`);
        svg.insertAdjacentHTML("beforeend", `<text x="${left - 6}" y="${y + 4}" fill="#64748b" font-size="11" text-anchor="end">${tickFmt(value)}</text>`);
      }
      /* Transaction Flow Events (Dotted vertical lines) */
      if (svgId === "value-chart" && showTransactions) {
        const isTotal = (selectedReturnMode === "total");
        const useTotal = isTotal && showAllTransactions;
        
        let maxDiff = 0.01;
        for (let i = 1; i < series.length; i++) {
          const prev = series[i - 1];
          const curr = series[i];
          const prevContrib = Number(useTotal ? (prev.total_net_contributions || 0) : (prev.net_contributions || 0));
          const currContrib = Number(useTotal ? (curr.total_net_contributions || 0) : (curr.net_contributions || 0));
          const diff = Math.abs(currContrib - prevContrib);
          if (diff > maxDiff) maxDiff = diff;
        }

        for (let i = 1; i < series.length; i++) {
          const prev = series[i - 1];
          const curr = series[i];
          const prevContrib = Number(useTotal ? (prev.total_net_contributions || 0) : (prev.net_contributions || 0));
          const currContrib = Number(useTotal ? (curr.total_net_contributions || 0) : (curr.net_contributions || 0));
          const diff = currContrib - prevContrib;
          if (Math.abs(diff) > 0.01) {
            const x = xScale(curr.date);
            const ratio = Math.abs(diff) / maxDiff;
            // Scale stroke width from 1.0px to 4.0px
            const strokeWidth = (1.0 + ratio * 3.0).toFixed(2);
            // Scale opacity from 0.25 to 0.75
            const opacity = (0.25 + ratio * 0.5).toFixed(2);
            const color = diff > 0 ? "#22c55e" : "#ef4444"; // green vs red
            const flowAmtStr = Math.abs(diff).toLocaleString("it-IT", {minimumFractionDigits: 0, maximumFractionDigits: 2});
            let tooltipText = "";
            if (useTotal) {
              tooltipText = diff > 0 
                ? `${curr.date}: Inflow +€${flowAmtStr}` 
                : `${curr.date}: Outflow/Purchase -€${flowAmtStr}`;
            } else {
              tooltipText = diff > 0 
                ? `${curr.date}: Buy +€${flowAmtStr}` 
                : `${curr.date}: Sell -€${flowAmtStr}`;
            }
            
            svg.insertAdjacentHTML("beforeend", `
              <line class="flow-event-line" 
                    x1="${x}" y1="${top}" 
                    x2="${x}" y2="${h - bottom}" 
                    stroke="${color}" 
                    stroke-opacity="${opacity}" 
                    stroke-width="${strokeWidth}" 
                    stroke-dasharray="3,3"
                    data-date="${curr.date}"
                    data-amount="${diff}">
                <title>${tooltipText}</title>
              </line>
            `);
          }
        }
      }

      /* Data lines */
      defs.forEach(([key, label, klass]) => {
        svg.insertAdjacentHTML("beforeend", `<path class="series-line ${klass}" d="${pointPath(series, key, xScale, yScale)}"></path>`);
      });
      /* X-axis ticks */
      xTicks(series, Math.min(8, Math.floor(w / 110))).forEach(date => {
        const x = xScale(date);
        svg.insertAdjacentHTML("beforeend", `<text x="${x}" y="${h - 10}" fill="#64748b" font-size="11" text-anchor="middle">${formatShortDate(date)}</text>`);
      });
      addHover(svg, series, defs, xScale, yScale, w, h, top, bottom, (value, key) => key.includes("pct") || key.includes("score") ? `${value.toFixed(2)}%` : money(value));
    }
    function getLegendColor(klass) {
      if (klass.includes("market")) return getComputedStyle(document.documentElement).getPropertyValue("--green");
      if (klass.includes("invested")) return getComputedStyle(document.documentElement).getPropertyValue("--blue");
      if (klass.includes("profit")) return getComputedStyle(document.documentElement).getPropertyValue("--violet");
      if (klass.includes("return")) return getComputedStyle(document.documentElement).getPropertyValue("--red");
      if (klass.includes("msci")) return getComputedStyle(document.documentElement).getPropertyValue("--cyan");
      if (klass.includes("xeon")) return getComputedStyle(document.documentElement).getPropertyValue("--pink");
      if (klass.includes("inflation")) return getComputedStyle(document.documentElement).getPropertyValue("--amber");
      if (klass.includes("weighted")) return getComputedStyle(document.documentElement).getPropertyValue("--violet");
      if (klass.includes("freq")) return getComputedStyle(document.documentElement).getPropertyValue("--teal");
      return "#94a3b8";
    }
    function bindReturnLegend() {
      document.querySelectorAll("[data-return-series]").forEach(input => {
        input.addEventListener("change", event => {
          returnVisibility[event.target.dataset.returnSeries] = event.target.checked;
          if (dashboardData) {
            renderValueCharts(dashboardData.valuation_series || []);
          }
        });
      });
    }
    function normalizeReturnSeries(series) {
      if (!series || !series.length) return [];
      const p0 = series[0];
      const r0 = Number(selectedReturnMode === "total" ? p0.total_return_pct : p0.return_pct || 0);
      const m0 = Number(p0.msci_return_pct || 0);
      const xeon0 = Number(p0.xeon_return_pct || 0);
      const inf0 = Number(p0.inflation_return_pct || 0);
      const mapped = series.map(p => {
        const r_t = Number(selectedReturnMode === "total" ? p.total_return_pct : p.return_pct || 0);
        const m_t = Number(p.msci_return_pct || 0);
        const xeon_t = Number(p.xeon_return_pct || 0);
        const inf_t = Number(p.inflation_return_pct || 0);
        
        const norm_r = Math.abs(1 + r0 / 100) > 1e-6 ? ((1 + r_t / 100) / (1 + r0 / 100) - 1) * 100 : 0;
        const norm_m = Math.abs(1 + m0 / 100) > 1e-6 ? ((1 + m_t / 100) / (1 + m0 / 100) - 1) * 100 : 0;
        const norm_xeon = Math.abs(1 + xeon0 / 100) > 1e-6 ? ((1 + xeon_t / 100) / (1 + xeon0 / 100) - 1) * 100 : 0;
        const norm_inf = Math.abs(1 + inf0 / 100) > 1e-6 ? ((1 + inf_t / 100) / (1 + inf0 / 100) - 1) * 100 : 0;
        
        return {
          ...p,
          return_pct: norm_r,
          msci_return_pct: norm_m,
          xeon_return_pct: norm_xeon,
          inflation_return_pct: norm_inf
        };
      });
      
      mapped.forEach((p, idx) => {
        const scores = timeWeightedOutperformanceScores(mapped.slice(0, idx + 1));
        p.weighted_score = scores.areaScore;
        p.freq_score = scores.timeScore;
      });
      return mapped;
    }
    function integrateDiffSegment(d0, d1, days) {
      if (days <= 0) return { positiveArea: 0, negativeArea: 0, positiveDays: d0 > 0 ? days : 0, totalDays: days };
      if (Math.abs(d0) < 1e-9 && Math.abs(d1) < 1e-9) {
        return { positiveArea: 0, negativeArea: 0, positiveDays: 0, totalDays: days };
      }
      if (d0 >= 0 && d1 >= 0) {
        return { positiveArea: ((d0 + d1) / 2) * days, negativeArea: 0, positiveDays: days, totalDays: days };
      }
      if (d0 <= 0 && d1 <= 0) {
        return { positiveArea: 0, negativeArea: ((Math.abs(d0) + Math.abs(d1)) / 2) * days, positiveDays: 0, totalDays: days };
      }
      const crossing = Math.abs(d0) / (Math.abs(d0) + Math.abs(d1));
      const daysToCross = days * crossing;
      if (d0 > 0) {
        return {
          positiveArea: (d0 / 2) * daysToCross,
          negativeArea: (Math.abs(d1) / 2) * (days - daysToCross),
          positiveDays: daysToCross,
          totalDays: days
        };
      }
      return {
        positiveArea: (d1 / 2) * (days - daysToCross),
        negativeArea: (Math.abs(d0) / 2) * daysToCross,
        positiveDays: days - daysToCross,
        totalDays: days
      };
    }
    function timeWeightedOutperformanceScores(series) {
      if (!series || series.length < 2) return { timeScore: 100, areaScore: 50 };
      let positiveArea = 0;
      let negativeArea = 0;
      let positiveDays = 0;
      let totalDays = 0;
      for (let i = 1; i < series.length; i++) {
        const prev = series[i - 1];
        const curr = series[i];
        const prevDate = new Date(prev.date).getTime();
        const currDate = new Date(curr.date).getTime();
        const days = Math.max(0, (currDate - prevDate) / 86400000);
        if (!Number.isFinite(days) || days <= 0) continue;
        const d0 = Number(prev.return_pct || 0) - Number(prev.msci_return_pct || 0);
        const d1 = Number(curr.return_pct || 0) - Number(curr.msci_return_pct || 0);
        const segment = integrateDiffSegment(d0, d1, days);
        positiveArea += segment.positiveArea;
        negativeArea += segment.negativeArea;
        positiveDays += segment.positiveDays;
        totalDays += segment.totalDays;
      }
      const totalArea = positiveArea + negativeArea;
      return {
        timeScore: totalDays > 1e-6 ? (positiveDays / totalDays * 100) : 100,
        areaScore: totalArea > 1e-6 ? (positiveArea / totalArea * 100) : 50
      };
    }

    function renderValueCharts(series) {
      const filtered = filterByPeriod(series);
      const isTotal = (selectedReturnMode === "total");
      const valueDefs = [
        [isTotal ? "total_market_value" : "market_value", "Portfolio value", "series-market"],
        [isTotal ? "total_net_contributions" : "net_contributions", "Net contributions", "series-invested"],
        [isTotal ? "total_profit" : "profit", "Profit", "series-profit"]
      ];
      const activeReturnDefs = returnDefs.filter(([key]) => returnVisibility[key]);
      renderLineChart("value-chart", filtered, valueDefs);
      
      const normalizedReturns = normalizeReturnSeries(filtered);
      renderLineChart("return-chart", normalizedReturns, activeReturnDefs, value => `${value.toFixed(1)}%`);

      const outperformanceScores = timeWeightedOutperformanceScores(normalizedReturns);
      const scoreFreq = outperformanceScores.timeScore;
      const scoreWeighted = outperformanceScores.areaScore;

      const scorePills = `
        <button type="button" id="freq-pill" class="score-pill teal ${returnVisibility.freq_score ? "active" : ""}" title="Toggle time-weighted outperformance line">
          <span class="score-pill-label">Time > MSCI</span>
          <span class="score-pill-value" style="color: ${scoreFreq >= 50 ? 'var(--green)' : 'var(--red)'};">${scoreFreq.toFixed(1)}%</span>
        </button>
        <button type="button" id="weighted-pill" class="score-pill violet ${returnVisibility.weighted_score ? "active" : ""}" title="Toggle area-weighted outperformance line">
          <span class="score-pill-label">Area</span>
          <span class="score-pill-value" style="color: ${scoreWeighted >= 50 ? 'var(--green)' : 'var(--red)'};">${scoreWeighted.toFixed(1)}%</span>
        </button>
      `;

      const valHtml = valueDefs.map(([key, label, klass]) => `<span class="legend-item"><i class="dot" style="background:${getLegendColor(klass)}"></i>${label}</span>`);
      const retHtml = returnDefs.map(([key, label, klass]) => {
        const lineStyle = klass.includes('msci') || klass.includes('inflation') || klass.includes('xeon') ? 'border-radius:0; height:2px; margin-top:6px;' : '';
        return `
          <label>
            <input type="checkbox" data-return-series="${key}" ${returnVisibility[key] ? "checked" : ""}>
            <i class="dot" style="background:${getLegendColor(klass)}; ${lineStyle}"></i>
            ${label}
          </label>
        `;
      });
      const transHtml = `
        <label>
          <input type="checkbox" id="toggle-transactions" ${showTransactions ? "checked" : ""}>
          <i class="dot" style="background:var(--blue); border-radius:0; width: 2px; height: 10px; border: 1px dashed var(--blue); margin-top: 2px;"></i>
          Flow Events
        </label>
        ${(showTransactions && isTotal) ? `
        <label>
          <input type="checkbox" id="toggle-show-all-transactions" ${showAllTransactions ? "checked" : ""}>
          Show All
        </label>
        ` : ""}
      `;
      document.getElementById("value-legend").innerHTML = `
        <div class="chart-controls">
          <div class="chart-control-group">
            <div class="chart-control-title">Value chart</div>
            <div class="chart-control-items">${valHtml.join("")}</div>
          </div>
          <div class="chart-control-group">
            <div class="chart-control-title">Return lines</div>
            <div class="chart-control-items">${retHtml.join("")}</div>
          </div>
          <div class="chart-control-group">
            <div class="chart-control-title">Outperformance</div>
            <div class="chart-control-items">${scorePills}</div>
          </div>
          <div class="chart-control-group">
            <div class="chart-control-title">Events</div>
            <div class="chart-control-items">${transHtml}</div>
          </div>
        </div>
      `;
      bindReturnLegend();

      document.getElementById("freq-pill").addEventListener("click", () => {
        returnVisibility.freq_score = !returnVisibility.freq_score;
        if (dashboardData) {
          renderValueCharts(dashboardData.valuation_series || []);
        }
      });
      document.getElementById("weighted-pill").addEventListener("click", () => {
        returnVisibility.weighted_score = !returnVisibility.weighted_score;
        if (dashboardData) {
          renderValueCharts(dashboardData.valuation_series || []);
        }
      });

      const toggleTrans = document.getElementById("toggle-transactions");
      if (toggleTrans) {
        toggleTrans.addEventListener("change", event => {
          showTransactions = event.target.checked;
          if (dashboardData) {
            renderValueCharts(dashboardData.valuation_series || []);
          }
        });
      }
      const toggleAllTrans = document.getElementById("toggle-show-all-transactions");
      if (toggleAllTrans) {
        toggleAllTrans.addEventListener("change", event => {
          showAllTransactions = event.target.checked;
          if (dashboardData) {
            renderValueCharts(dashboardData.valuation_series || []);
          }
        });
      }
    }
    function renderChart(series) {
      series = filterByPeriod(series);
      const svg = document.getElementById("chart");
      svg.innerHTML = "";
      if (!series.length) {
        document.getElementById("legend").innerHTML = "";
        return;
      }
      const activeChartDefs = chartDefs.filter(([key]) => cashVisibility[key]);
      if (!activeChartDefs.length) {
        document.getElementById("legend").innerHTML = chartDefs.map(([key, label, klass]) => cashLegendItem(key, label, klass)).join("");
        bindCashLegend();
        return;
      }
      const { w, h } = initSvgSize(svg);
      const left = 60, right = 20, top = 22, bottom = 36;
      const dates = series.map(p => new Date(p.date).getTime());
      const values = [];
      series.forEach(p => activeChartDefs.forEach(([key]) => values.push(Number(p[key] || 0))));
      const minX = Math.min(...dates), maxX = Math.max(...dates);
      const rawMin = Math.min(...values), rawMax = Math.max(...values);
      const forceZero = selectedPeriod === 'all' || (rawMin < 0 && rawMax > 0);
      const { minY, maxY } = niceYRange(rawMin, rawMax, forceZero);
      const xScale = d => left + ((new Date(d).getTime() - minX) / Math.max(1, maxX - minX)) * (w - left - right);
      const yScale = v => top + (1 - ((v - minY) / Math.max(1, maxY - minY))) * (h - top - bottom);

      if (minY <= 0 && maxY >= 0) {
        const axisY = yScale(0);
        svg.insertAdjacentHTML("beforeend", `<line class="axis" x1="${left}" y1="${axisY}" x2="${w-right}" y2="${axisY}" stroke-opacity="0.3"></line>`);
      }
      svg.insertAdjacentHTML("beforeend", `<line class="axis" x1="${left}" y1="${top}" x2="${left}" y2="${h-bottom}"></line>`);
      const tickCount = 5;
      for (let i = 0; i <= tickCount; i++) {
        const t = i / tickCount;
        const y = top + t * (h - top - bottom);
        const value = maxY - t * (maxY - minY);
        svg.insertAdjacentHTML("beforeend", `<line class="grid-line" x1="${left}" y1="${y}" x2="${w-right}" y2="${y}"></line>`);
        svg.insertAdjacentHTML("beforeend", `<text x="${left - 6}" y="${y + 4}" fill="#64748b" font-size="11" text-anchor="end">${smartTickFormat(value)}</text>`);
      }
      activeChartDefs.forEach(([key, label, klass]) => {
        svg.insertAdjacentHTML("beforeend", `<path class="series-line ${klass}" d="${pointPath(series, key, xScale, yScale)}"></path>`);
      });
      xTicks(series, Math.min(8, Math.floor(w / 110))).forEach(date => {
        const x = xScale(date);
        svg.insertAdjacentHTML("beforeend", `<text x="${x}" y="${h - 10}" fill="#64748b" font-size="11" text-anchor="middle">${formatShortDate(date)}</text>`);
      });
      document.getElementById("legend").innerHTML = chartDefs.map(([key, label, klass]) => cashLegendItem(key, label, klass)).join("");
      bindCashLegend();
      addHover(svg, series, activeChartDefs, xScale, yScale, w, h, top, bottom, value => money(value));
    }
    function cashLegendColor(klass) {
      return getComputedStyle(document.documentElement).getPropertyValue(
        klass.includes("invested") ? "--blue" : klass.includes("net") ? "--green" : klass.includes("cost") ? "--teal" : klass.includes("proceeds") ? "--amber" : "--red"
      );
    }
    function cashLegendItem(key, label, klass) {
      return `<label><input type="checkbox" data-cash-series="${key}" ${cashVisibility[key] ? "checked" : ""}> <i class="dot" style="background:${cashLegendColor(klass)}"></i>${label}</label>`;
    }
    function bindCashLegend() {
      document.querySelectorAll("[data-cash-series]").forEach(input => {
        input.addEventListener("change", event => {
          cashVisibility[event.target.dataset.cashSeries] = event.target.checked;
          if (dashboardData) renderChart(dashboardData.series);
        });
      });
    }
    function sortValue(row, key) {
      const value = row[key];
      if (value === null || value === undefined) return "";
      return value;
    }
    function sortedPositions(positions) {
      return [...positions].sort((a, b) => {
        const av = sortValue(a, sortState.key);
        const bv = sortValue(b, sortState.key);
        if (typeof av === "number" || typeof bv === "number" || sortState.key === "is_open") {
          return (Number(av || 0) - Number(bv || 0)) * (sortState.direction === "asc" ? 1 : -1);
        }
        return String(av).localeCompare(String(bv), undefined, { numeric: true, sensitivity: "base" }) * (sortState.direction === "asc" ? 1 : -1);
      });
    }
    function updateSortHeaders() {
      document.querySelectorAll("th[data-sort]").forEach(th => {
        const base = th.textContent.replace(/\s[↑↓]$/, "");
        th.textContent = th.dataset.sort === sortState.key ? `${base} ${sortState.direction === "asc" ? "↑" : "↓"}` : base;
      });
    }
    function badgeHtml(type) {
      if (!type) return "";
      let color = "";
      let bg = "";
      if (type === "ETF") {
        color = "#10B981";
        bg = "rgba(16, 185, 129, 0.12)";
      } else if (type === "STOCK") {
        color = "#F59E0B";
        bg = "rgba(245, 158, 11, 0.12)";
      } else if (type === "CUR") {
        color = "#8B5CF6";
        bg = "rgba(139, 92, 246, 0.12)";
      } else {
        return "";
      }
      return `<span style="font-size: 9px; font-weight: 700; text-transform: uppercase; color: ${color}; background: ${bg}; border: 1px solid ${color}33; padding: 1px 5px; border-radius: 4px; letter-spacing: 0.5px; display: inline-flex; align-items: center; line-height: 12px; margin-left: 4px; flex-shrink: 0;">${type}</span>`;
    }
    function focusedOpenHoldings(open) {
      if (!open.length) return { rows: [], targetCount: 0 };
      const targetCount = Math.max(1, Math.ceil(open.length * 0.5));
      const ranked = [...open].sort((a, b) => Number(b.market_value_eur || 0) - Number(a.market_value_eur || 0));
      const selected = new Set(ranked.slice(0, targetCount));
      return { rows: open.filter(row => selected.has(row)), targetCount };
    }
    function updateHoldingsControls(open, closed, visibleOpen, focusedCount) {
      const title = document.getElementById("holdings-view-title");
      const detail = document.getElementById("holdings-view-detail");
      const showAllBtn = document.getElementById("btn-show-all-holdings");
      const showAllLabel = document.getElementById("btn-show-all-label");
      const showAllSub = document.getElementById("btn-show-all-sub");
      const closedBtn = document.getElementById("btn-toggle-closed");
      const closedLabel = document.getElementById("btn-closed-label");
      const closedSub = document.getElementById("btn-closed-sub");
      const canFocus = open.length > focusedCount;

      if (title) title.textContent = showAllHoldings || !canFocus ? "All open holdings" : "Top holdings";
      if (detail) {
        detail.textContent = showAllHoldings || !canFocus
          ? `${visibleOpen} open positions shown${closed.length ? `, ${closed.length} closed ${showClosed ? "included" : "available"}` : ""}.`
          : `Showing top ${visibleOpen}/${open.length} open positions by current value.`;
      }
      if (showAllBtn) {
        showAllBtn.disabled = !canFocus;
        showAllBtn.classList.toggle("active", showAllHoldings && canFocus);
      }
      if (showAllLabel) showAllLabel.textContent = showAllHoldings && canFocus ? "Top 50%" : "Show all";
      if (showAllSub) showAllSub.textContent = canFocus ? (showAllHoldings ? "Refocus" : `${open.length - visibleOpen} more`) : "All shown";
      if (closedBtn) {
        closedBtn.disabled = !closed.length;
        closedBtn.classList.toggle("active", showClosed && closed.length > 0);
      }
      if (closedLabel) closedLabel.textContent = showClosed && closed.length ? "Hide closed" : "Closed";
      if (closedSub) closedSub.textContent = closed.length ? `${closed.length} exited` : "None";
    }
    function renderPositions(positions) {
      const open = positions.filter(p => p.is_open);
      const closed = positions.filter(p => !p.is_open);
      const focused = focusedOpenHoldings(open);
      const openDisplayed = showAllHoldings ? open : focused.rows;
      const displayed = showClosed ? [...openDisplayed, ...closed] : openDisplayed;
      const hiddenOpen = Math.max(0, open.length - openDisplayed.length);
      document.getElementById("holdings-count").textContent = `${openDisplayed.length}/${open.length} open shown${hiddenOpen ? ` · ${hiddenOpen} hidden` : ""}${showClosed && closed.length ? ` · ${closed.length} closed shown` : ""}`;
      updateHoldingsControls(open, closed, openDisplayed.length, focused.targetCount);
      const sortedDisplayed = sortedPositions(displayed);
      document.getElementById("positions").innerHTML = sortedDisplayed.length ? sortedDisplayed.map(p => {
        const logoUrl = p.isin ? `https://assets.parqet.com/logos/isin/${p.isin}?format=png` : (p.symbol ? `https://assets.parqet.com/logos/symbol/${p.symbol}?format=png` : '');
        const logoImg = logoUrl ? `<img src="${logoUrl}" onerror="if(this.src.indexOf('/isin/') !== -1 && '${p.symbol}') { this.src = 'https://assets.parqet.com/logos/symbol/${p.symbol}?format=png'; } else { this.style.display='none'; }" style="width: 20px; height: 20px; border-radius: 50%; vertical-align: middle; margin-right: 8px; background: rgba(255,255,255,0.05); flex-shrink: 0;">` : '';
        
        let assetNameHtml = `<span>${p.asset}</span>`;
        if (p.asset.toLowerCase().includes("europension taxbenefit")) {
          assetNameHtml = `
            <span>${p.asset}</span>
            <span class="info-icon" onclick="showAssetInfoPopup('europension', event)" style="
              display: inline-flex;
              align-items: center;
              justify-content: center;
              width: 14px;
              height: 14px;
              border-radius: 50%;
              background: var(--line-strong);
              color: var(--ink-secondary);
              font-size: 10px;
              font-weight: bold;
              font-family: serif;
              font-style: italic;
              margin-left: 6px;
              cursor: pointer;
              border: 1px solid var(--muted);
              vertical-align: middle;
            " title="Click for details">i</span>
          `;
        } else if (p.asset.toLowerCase().includes("mystyle")) {
          assetNameHtml = `
            <span>${p.asset}</span>
            <span class="info-icon" onclick="showAssetInfoPopup('mystyle', event)" style="
              display: inline-flex;
              align-items: center;
              justify-content: center;
              width: 14px;
              height: 14px;
              border-radius: 50%;
              background: var(--line-strong);
              color: var(--ink-secondary);
              font-size: 10px;
              font-weight: bold;
              font-family: serif;
              font-style: italic;
              margin-left: 6px;
              cursor: pointer;
              border: 1px solid var(--muted);
              vertical-align: middle;
            " title="Click for details">i</span>
          `;
        }
        
        return `
          <tr>
            <td style="text-align: left; display: flex; align-items: center;">${logoImg}${assetNameHtml}${badgeHtml(p.asset_type)}</td>
            <td>${num.format(p.quantity)}</td>
            <td>${p.isin || ""}</td>
            <td>${p.symbol || ""}</td>
            <td>${p.price ? `${num.format(p.price)} ${p.price_currency}` : "-"}</td>
            <td>${money(p.market_value_eur)}</td>
            <td>${money(p.cost_basis_eur)}</td>
            <td class="${signedClass(p.display_pl_eur)}">${money(p.display_pl_eur)}</td>
            <td class="${signedClass(p.display_pl_pct)}">${percent(p.display_pl_pct)}</td>
            <td><span class="status ${p.pricing_status}">${p.pricing_status}</span></td>
          </tr>
        `;
      }).join("") : `<tr><td colspan="10" class="empty-state">No holdings available for this selection.</td></tr>`;
      updateSortHeaders();
    }
    window.toggleSector = function(subId, rowEl) {
      const subRow = document.getElementById(subId);
      if (!subRow) return;
      const chevron = rowEl.querySelector(".chevron");
      if (subRow.style.display === "none") {
        subRow.style.display = "table-row";
        if (chevron) chevron.style.transform = "rotate(90deg)";
      } else {
        subRow.style.display = "none";
        if (chevron) chevron.style.transform = "rotate(0deg)";
      }
    };
    function distributionRows(rows, key) {
      if (!rows || !rows.length) return `<tr><td colspan="3" class="empty-state">No distribution data available.</td></tr>`;
      
      if (key === "sector") {
        return rows.map((row, index) => {
          const subId = `sector-sub-${index}`;
          const hasHoldings = row.holdings && row.holdings.length;
          
          let holdingsHtml = "";
          if (hasHoldings) {
            holdingsHtml = `
              <tr id="${subId}" style="display: none; background: rgba(255,255,255,0.015);">
                <td colspan="3" style="padding: 4px 12px 8px 20px;">
                  <table style="width: 100%; border-collapse: collapse; margin: 2px 0;">
                    <tbody>
                      ${row.holdings.map(h => {
                        const hTicker = h.holding_ticker;
                        const logoUrl = hTicker ? `https://assets.parqet.com/logos/symbol/${hTicker}?format=png` : '';
                        const logoImg = logoUrl ? `<img src="${logoUrl}" onerror="this.style.display='none';" style="width: 14px; height: 14px; border-radius: 50%; vertical-align: middle; margin-right: 6px; background: rgba(255,255,255,0.05); flex-shrink: 0;">` : '';
                        return `
                          <tr style="border-bottom: 1px solid rgba(255,255,255,0.01); line-height: 24px;">
                            <td style="text-align: left; padding: 2px 0; font-size: 0.82em; display: flex; align-items: center; color: var(--muted);">${logoImg}<span>${escapeHtml(h.holding)}</span></td>
                            <td style="text-align: right; padding: 2px 0; font-size: 0.82em; color: var(--muted);">${money(h.market_value_eur)}</td>
                            <td style="text-align: right; padding: 2px 0; font-size: 0.82em; color: var(--muted);">${percent(h.weight_pct)}</td>
                          </tr>
                        `;
                      }).join("")}
                    </tbody>
                  </table>
                </td>
              </tr>
            `;
          }
          
          const chevron = hasHoldings ? `<span class="chevron" style="display: inline-block; transition: transform 0.2s; margin-right: 6px; font-size: 0.75em; color: var(--muted); width: 10px; text-align: center;">▶</span>` : "";
          const clickableStyle = hasHoldings ? "cursor: pointer; user-select: none;" : "";
          const onclickAttr = hasHoldings ? `onclick="toggleSector('${subId}', this)"` : "";
          
          return `
            <tr style="${clickableStyle}" ${onclickAttr}>
              <td style="text-align: left; display: flex; align-items: center;">${chevron}${distributionNameCell(row, key)}</td>
              <td>${money(row.market_value_eur)}</td>
              <td>${percent(row.weight_pct)}</td>
            </tr>
            ${holdingsHtml}
          `;
        }).join("");
      }

      return rows.map(row => {
        const ticker = row.holding_ticker;
        const logoUrl = (key === "holding" && ticker) ? `https://assets.parqet.com/logos/symbol/${ticker}?format=png` : '';
        const logoImg = logoUrl ? `<img src="${logoUrl}" onerror="this.style.display='none';" style="width: 16px; height: 16px; border-radius: 50%; vertical-align: middle; margin-right: 6px; background: rgba(255,255,255,0.05); flex-shrink: 0;">` : '';
        return `
          <tr>
            <td style="text-align: left; display: flex; align-items: center;">${logoImg}${distributionNameCell(row, key)}</td>
            <td>${money(row.market_value_eur)}</td>
            <td>${percent(row.weight_pct)}</td>
          </tr>
        `;
      }).join("");
    }
    function distributionNameCell(row, key) {
      const name = escapeHtml(row[key]);
      const badge = key === "holding" ? badgeHtml(row.asset_type) : "";
      if (key !== "holding" || !row.source_assets || !row.source_assets.length) return `<span>${name}</span>${badge}`;
      const pills = row.source_assets.map(asset => `<span class="source-pill" title="${escapeHtml(asset)}">${escapeHtml(asset)}</span>`).join("");
      return `<div class="underlying-name"><span>${name}</span>${badge}<span class="source-pills">${pills}</span></div>`;
    }
    function sourceStatusLabel(row) {
      const message = row.message ? ` - ${row.message}` : "";
      return `${row.status || ""}${message}`;
    }
    function sourceKey(row) {
      return `${row.asset || ""}|${row.isin || ""}`;
    }
    function sourceRowsForSource(data, source) {
      return (data.source_rows || data.rows || []).filter(row => (
        row.source_asset === source.asset && (!source.isin || !row.source_isin || row.source_isin === source.isin)
      ));
    }
    function selectedUnderlyingRows(data, source) {
      const rows = sourceRowsForSource(data, source);
      const total = rows.reduce((sum, row) => sum + Number(row.market_value_eur || 0), 0);
      return rows.map(row => ({
        holding: row.holding_name,
        holding_ticker: row.holding_ticker,
        market_value_eur: row.market_value_eur,
        weight_pct: total > 0 ? Number(((Number(row.market_value_eur || 0) / total) * 100).toFixed(2)) : 0,
        asset_class: row.asset_class,
        asset_type: determineAssetTypeFromClass(row.asset_class),
        source_assets: [source.asset]
      })).sort((a, b) => Number(b.market_value_eur || 0) - Number(a.market_value_eur || 0));
    }
    function determineAssetTypeFromClass(assetClass) {
      const value = String(assetClass || "").toLowerCase();
      if (value.includes("single share") || value.includes("equity")) return "STOCK";
      if (value.includes("cash")) return "CUR";
      if (value.includes("etf") || value.includes("bond") || value.includes("fund")) return "ETF";
      return "";
    }
    function renderDistribution(distribution) {
      const data = distribution || {};
      const sources = data.composition_sources || [];
      let selectedSource = sources.find(row => sourceKey(row) === selectedDistributionSource);
      if (selectedDistributionSource && !selectedSource) selectedDistributionSource = "";
      const underlyingRows = selectedSource ? selectedUnderlyingRows(data, selectedSource) : data.underlying;
      const sourceCoverage = data.composition_source_coverage || {resolved: 0, total: 0};
      document.getElementById("distribution-summary").textContent =
        `${data.covered_assets || 0}/${data.open_assets || 0} open assets mapped | ${sourceCoverage.resolved}/${sourceCoverage.total} composition sources | ${money(data.total_value_eur)} total${selectedSource ? ` | selected: ${selectedSource.asset}` : ""}`;
      document.getElementById("distribution-sources").innerHTML = sources.length
        ? sources.map(row => {
            const isSelected = sourceKey(row) === selectedDistributionSource;
            const symbol = window.assetToSymbolMap ? window.assetToSymbolMap[row.asset] : '';
            const logoUrl = row.isin ? `https://assets.parqet.com/logos/isin/${row.isin}?format=png` : (symbol ? `https://assets.parqet.com/logos/symbol/${symbol}?format=png` : '');
            const logoImg = logoUrl ? `<img src="${logoUrl}" onerror="if(this.src.indexOf('/isin/') !== -1 && '${symbol}') { this.src = 'https://assets.parqet.com/logos/symbol/${symbol}?format=png'; } else { this.style.display='none'; }" style="width: 16px; height: 16px; border-radius: 50%; vertical-align: middle; margin-right: 6px; background: rgba(255,255,255,0.05); flex-shrink: 0;">` : '';
            return `
              <tr class="composition-source-row ${isSelected ? "selected" : ""}" data-source-key="${escapeHtml(sourceKey(row))}">
                <td style="text-align: left; display: flex; align-items: center;">${logoImg}<div><div style="display:flex; align-items:center; gap:4px;"><span>${row.asset}</span>${badgeHtml(window.assetToTypeMap ? window.assetToTypeMap[row.asset] : '')}${isSelected ? '<span class="selected-flag">Selected</span>' : ''}</div><div class="subtle">${row.isin || ""}</div></div></td>
                <td style="text-align: left;">${escapeHtml(row.fund_name || row.asset || "")}</td>
                <td>${row.issuer || ""}</td>
                <td>${sourceStatusLabel(row)}</td>
                <td>${row.rows || 0}${row.weight_sum ? ` / ${row.weight_sum}%` : ""}</td>
                <td>${row.fetched_at || ""}</td>
              </tr>
            `;
          }).join("")
        : `<tr><td colspan="6" class="empty-state">No ETF composition source metadata available.</td></tr>`;
      document.getElementById("distribution-underlying").innerHTML = distributionRows(underlyingRows, "holding");
      document.querySelectorAll(".composition-source-row").forEach(rowEl => {
        rowEl.addEventListener("click", () => {
          selectedDistributionSource = selectedDistributionSource === rowEl.dataset.sourceKey ? "" : rowEl.dataset.sourceKey;
          renderDistribution(data);
        });
      });
      document.getElementById("distribution-sectors").innerHTML = distributionRows(data.sectors, "sector");
      document.getElementById("distribution-geographies").innerHTML = distributionRows(data.geographies, "geo");
      document.getElementById("distribution-classes").innerHTML = distributionRows(data.asset_classes, "asset_class");
      document.getElementById("distribution-missing").innerHTML = data.missing && data.missing.length
        ? data.missing.map(row => {
            const symbol = window.assetToSymbolMap ? window.assetToSymbolMap[row.asset] : '';
            const logoUrl = row.isin ? `https://assets.parqet.com/logos/isin/${row.isin}?format=png` : (symbol ? `https://assets.parqet.com/logos/symbol/${symbol}?format=png` : '');
            const logoImg = logoUrl ? `<img src="${logoUrl}" onerror="if(this.src.indexOf('/isin/') !== -1 && '${symbol}') { this.src = 'https://assets.parqet.com/logos/symbol/${symbol}?format=png'; } else { this.style.display='none'; }" style="width: 16px; height: 16px; border-radius: 50%; vertical-align: middle; margin-right: 6px; background: rgba(255,255,255,0.05); flex-shrink: 0;">` : '';
            return `
              <tr>
                <td style="text-align: left; display: flex; align-items: center;">${logoImg}<span>${row.asset}</span>${badgeHtml(window.assetToTypeMap ? window.assetToTypeMap[row.asset] : '')}</td>
                <td>${row.isin || ""}</td>
                <td>${money(row.market_value_eur)}</td>
                <td>${sourceStatusLabel(row)}</td>
              </tr>
            `;
          }).join("")
        : `<tr><td colspan="4" class="empty-state">All open assets have distribution rows.</td></tr>`;
    }
    window.activeNewsFilter = null;
    window.currentNewsData = null;

    function symbolLogoHtml(symbol) {
      if (!symbol) return '';
      const upperSymbol = symbol.toUpperCase();
      const isin = window.symbolToIsinMap ? window.symbolToIsinMap[upperSymbol] : '';
      const logoUrl = isin ? `https://assets.parqet.com/logos/isin/${isin}?format=png` : `https://assets.parqet.com/logos/symbol/${upperSymbol}?format=png`;
      return `<img src="${logoUrl}" onerror="if(this.src.indexOf('/isin/') !== -1) { this.src = 'https://assets.parqet.com/logos/symbol/${upperSymbol}?format=png'; } else { this.style.display='none'; }" style="width: 14px; height: 14px; border-radius: 50%; vertical-align: middle; margin-right: 5px; background: rgba(255,255,255,0.15); flex-shrink: 0;">`;
    }

    function toggleNewsFilter(symbol) {
      if (!symbol) return;
      const upperSymbol = symbol.toUpperCase();
      if (window.activeNewsFilter === upperSymbol) {
        window.activeNewsFilter = null;
      } else {
        window.activeNewsFilter = upperSymbol;
      }
      if (window.currentNewsData) {
        renderNews(window.currentNewsData);
      }
    }

    function renderNews(news) {
      window.currentNewsData = news || {};
      const data = window.currentNewsData;
      const symbols = data.symbols || [];
      
      let itemsToRender = data.items || [];
      if (window.activeNewsFilter) {
        itemsToRender = itemsToRender.filter(item => (item.symbol || '').toUpperCase() === window.activeNewsFilter);
      }
      
      document.getElementById("news-summary").innerHTML = data.status === "available"
        ? `${itemsToRender.length}/${data.count || 0} headlines | ${symbols.length} tickers${window.activeNewsFilter ? ` | filter: <span style="color:var(--blue); font-weight:bold; cursor:pointer; text-decoration:underline;" onclick="toggleNewsFilter('${escapeHtml(window.activeNewsFilter)}')">${escapeHtml(window.activeNewsFilter)} (clear)</span>` : ''}`
        : `No headlines available | ${symbols.length} tickers`;
        
      document.getElementById("news-symbols").innerHTML = symbols.length
        ? symbols.map(symbol => {
            const upperSymbol = symbol.toUpperCase();
            const activeClass = (window.activeNewsFilter === upperSymbol) ? 'active' : '';
            return `<span class="source-pill ${activeClass}" style="cursor:pointer;" onclick="toggleNewsFilter('${escapeHtml(symbol)}')">${symbolLogoHtml(symbol)}${escapeHtml(symbol)}</span>`;
          }).join("")
        : `<span class="empty-state">No stock tickers detected from current holdings.</span>`;
        
      document.getElementById("news-list").innerHTML = itemsToRender.length
        ? itemsToRender.map(item => {
            const upperSymbol = (item.symbol || '').toUpperCase();
            const cardActive = (window.activeNewsFilter === upperSymbol) ? 'active' : '';
            return `
              <article class="news-card">
                <div class="news-meta">
                  <span class="source-pill ${cardActive}" style="cursor:pointer;" onclick="toggleNewsFilter('${escapeHtml(item.symbol || '')}')">${symbolLogoHtml(item.symbol)}${escapeHtml(item.symbol || "")}</span>
                  <span>${escapeHtml(item.source || "")}</span>
                  <span>${escapeHtml(item.published || "")}</span>
                </div>
                <a href="${escapeHtml(item.link || "#")}" target="_blank" rel="noopener noreferrer">${escapeHtml(item.title || "")}</a>
              </article>
            `;
          }).join("")
        : `<div class="empty-state">No stock news available${window.activeNewsFilter ? ` for ticker ${window.activeNewsFilter}` : ''}.</div>`;
    }

    // ─── Watchlist JS Rendering ───
    function renderWatchlistCard(item) {
      if (item.error) {
        return `
          <div class="glass-card" style="padding: 15px; display: flex; flex-direction: column; justify-content: space-between; position: relative;">
            <div>
              <div style="display: flex; justify-content: space-between; align-items: start;">
                <h4 style="color: var(--red); font-size: 14px; margin-bottom: 4px;">${escapeHtml(item.ticker)}</h4>
                <button type="button" class="watchlist-remove-btn" data-ticker="${escapeHtml(item.ticker)}" style="
                  background: rgba(248, 113, 113, 0.1);
                  border: 1px solid rgba(248, 113, 113, 0.2);
                  color: var(--red);
                  border-radius: 50%;
                  width: 24px;
                  height: 24px;
                  display: flex;
                  align-items: center;
                  justify-content: center;
                  cursor: pointer;
                  font-size: 14px;
                  font-weight: bold;
                  transition: all 0.2s ease;
                " title="Remove from Watchlist">−</button>
              </div>
              <p style="font-size: 11px; color: var(--muted);">${escapeHtml(item.error)}</p>
            </div>
          </div>
        `;
      }

      const sign = item.change >= 0 ? "+" : "";
      const changeColor = item.change >= 0 ? "var(--green)" : "var(--red)";
      const priceText = `${item.price.toFixed(2)} ${item.currency}`;
      const changeText = `${sign}${item.change.toFixed(2)} (${sign}${item.change_pct.toFixed(2)}%)`;

      return `
        <div class="glass-card" style="
          padding: 15px; 
          display: flex; 
          flex-direction: column; 
          justify-content: space-between; 
          border-radius: var(--radius-sm);
          position: relative;
          transition: transform 0.2s ease, box-shadow 0.2s ease;
        " onmouseover="this.style.transform='translateY(-2px)';" onmouseout="this.style.transform='translateY(0)';">
          <div>
            <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 6px;">
              <span style="font-weight: 700; font-size: 14px; color: var(--ink);">${escapeHtml(item.ticker)}</span>
              <button type="button" class="watchlist-remove-btn" data-ticker="${escapeHtml(item.ticker)}" style="
                background: rgba(248, 113, 113, 0.1);
                border: 1px solid rgba(248, 113, 113, 0.2);
                color: var(--red);
                border-radius: 50%;
                width: 24px;
                height: 24px;
                display: flex;
                align-items: center;
                justify-content: center;
                cursor: pointer;
                font-size: 14px;
                font-weight: bold;
                transition: all 0.2s ease;
              " title="Remove from Watchlist">−</button>
            </div>
            <h4 style="
              font-size: 12px; 
              color: var(--muted); 
              font-weight: 500;
              margin-bottom: 12px;
              white-space: nowrap;
              overflow: hidden;
              text-overflow: ellipsis;
            " title="${escapeHtml(item.name)}">${escapeHtml(item.name)}</h4>
          </div>
          
          <div style="display: flex; justify-content: space-between; align-items: end; margin-top: auto;">
            <div>
              <div style="font-size: 18px; font-weight: 700; color: var(--ink); margin-bottom: 2px;">${priceText}</div>
              <div style="font-size: 12px; font-weight: 600; color: ${changeColor};">${changeText}</div>
            </div>
            
            <div style="display: flex; gap: 8px;">
              <a href="${escapeHtml(item.justetf_url)}" target="_blank" style="
                font-size: 11px;
                font-weight: 600;
                color: var(--cyan);
                background: rgba(34, 211, 238, 0.1);
                border: 1px solid rgba(34, 211, 238, 0.2);
                border-radius: 6px;
                padding: 4px 8px;
                text-decoration: none;
                transition: all 0.2s ease;
              " onmouseover="this.style.background='rgba(34, 211, 238, 0.2)';" onmouseout="this.style.background='rgba(34, 211, 238, 0.1)';">JustETF</a>
              <a href="${escapeHtml(item.yfinance_url)}" target="_blank" style="
                font-size: 11px;
                font-weight: 600;
                color: var(--amber);
                background: rgba(251, 191, 36, 0.1);
                border: 1px solid rgba(251, 191, 36, 0.2);
                border-radius: 6px;
                padding: 4px 8px;
                text-decoration: none;
                transition: all 0.2s ease;
              " onmouseover="this.style.background='rgba(251, 191, 36, 0.2)';" onmouseout="this.style.background='rgba(251, 191, 36, 0.1)';">Yahoo</a>
            </div>
          </div>
        </div>
      `;
    }

    function renderWatchlist(list) {
      const summary = document.getElementById("watchlist-summary");
      if (summary) {
        summary.textContent = `${list.length} item${list.length !== 1 ? "s" : ""} watched`;
      }
      
      const grid = document.getElementById("watchlist-grid");
      if (!grid) return;
      
      if (!list.length) {
        grid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: var(--muted); padding: 30px; border: 1px dashed var(--line); border-radius: var(--radius-sm); font-size: 13px;">Watchlist is empty. Enter a ticker to start tracking.</div>`;
        return;
      }
      
      grid.innerHTML = list.map(item => renderWatchlistCard(item)).join("");
      
      grid.querySelectorAll(".watchlist-remove-btn").forEach(btn => {
        btn.addEventListener("click", async () => {
          const ticker = btn.dataset.ticker;
          if (!ticker) return;
          btn.disabled = true;
          btn.textContent = "…";
          try {
            const res = await fetch("/api/watchlist", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ ticker: ticker, action: "remove" })
            });
            const rData = await res.json();
            if (!res.ok) throw new Error(rData.error || "Failed to remove ticker.");
            renderWatchlist(rData.watchlist || []);
          } catch (err) {
            alert(err.message);
            btn.disabled = false;
            btn.textContent = "−";
          }
        });
      });
    }

    async function loadWatchlist(refresh = false) {
      const summary = document.getElementById("watchlist-summary");
      if (summary) summary.textContent = "Loading watchlist…";
      try {
        const response = await fetch(`/api/watchlist${refresh ? "?refresh=true" : ""}`);
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Failed to load watchlist.");
        renderWatchlist(data.watchlist || []);
      } catch (err) {
        console.error("Watchlist error:", err);
        const grid = document.getElementById("watchlist-grid");
        if (grid) grid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: var(--red); padding: 20px;">Error: ${escapeHtml(err.message)}</div>`;
        if (summary) summary.textContent = "Error loading watchlist";
      }
    }

    async function loadNews(refresh = false, symbols = []) {
      window.activeNewsFilter = null; // Clear active news filter on reloading news
      const summary = document.getElementById("news-summary");
      const list = document.getElementById("news-list");
      summary.textContent = "Loading feeds…";
      try {
        const params = currentQueryParams();
        if (refresh) params.set("refresh", "1");
        if (Array.isArray(symbols) && symbols.length) params.set("symbols", symbols.join(","));
        const response = await fetch(`/api/news?${params.toString()}`);
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "News request failed.");
        renderNews(data);
      } catch (err) {
        summary.textContent = "News unavailable";
        list.innerHTML = `<div class="empty-state">${escapeHtml(err.message)}</div>`;
      }
    }
    function currentQueryParams() {
      return new URLSearchParams({
        person: selectedPerson,
        berkshire: selectedBerkshireMode,
        proxy: selectedProxyMode,
        broker: selectedBroker,
        live_only: selectedLiveMode === "live" ? "on" : "off"
      });
    }
    function updateExportSummary() {
      const summary = document.getElementById("export-summary");
      if (!summary) return;
      const person = selectedPerson.charAt(0).toUpperCase() + selectedPerson.slice(1);
      const broker = selectedBroker === "all" ? "all brokers" : selectedBroker;
      const live = selectedLiveMode === "live" ? "live assets only" : "all assets";
      summary.textContent = `${person} | ${selectedWindowLabel()} | ${broker} | ${selectedBerkshireMode === "lookthrough" ? "BRK 13F" : "BRK stock"} | ${selectedProxyMode === "on" ? "proxy gaps" : "official only"} | ${live}`;
    }
    function exportDashboard() {
      const formatEl = document.getElementById("export-format");
      const format = formatEl ? formatEl.value : "pdf";
      const params = currentQueryParams();
      params.set("period", selectedPeriod);
      params.set("format", format);
      window.location.href = `/api/export?${params.toString()}`;
    }
    function renderDividends(dividends) {
      document.getElementById("dividends-summary").textContent = `${dividends.count} payments | ${money(dividends.total_eur)} net | ${money(dividends.tax_eur)} tax | ${money(dividends.gross_eur)} gross`;
      
      const agg = {};
      (dividends.rows || []).forEach(row => {
        if (!agg[row.asset]) agg[row.asset] = { asset: row.asset, isin: row.isin || "", count: 0, amount: 0, tax: 0, gross: 0 };
        agg[row.asset].count++;
        agg[row.asset].amount += row.amount_eur;
        agg[row.asset].tax += row.tax_eur;
        agg[row.asset].gross += row.gross_eur;
      });
      const sortedAgg = Object.values(agg).sort((a, b) => b.amount - a.amount);
      
      document.getElementById("dividends-aggregate").innerHTML = sortedAgg.map(r => {
        const symbol = window.assetToSymbolMap ? window.assetToSymbolMap[r.asset] : '';
        const logoUrl = r.isin ? `https://assets.parqet.com/logos/isin/${r.isin}?format=png` : (symbol ? `https://assets.parqet.com/logos/symbol/${symbol}?format=png` : '');
        const logoImg = logoUrl ? `<img src="${logoUrl}" onerror="if(this.src.indexOf('/isin/') !== -1 && '${symbol}') { this.src = 'https://assets.parqet.com/logos/symbol/${symbol}?format=png'; } else { this.style.display='none'; }" style="width: 16px; height: 16px; border-radius: 50%; vertical-align: middle; margin-right: 6px; background: rgba(255,255,255,0.05); flex-shrink: 0;">` : '';
        return `
          <tr>
            <td style="text-align: left; display: flex; align-items: center;">${logoImg}<span>${r.asset}</span>${badgeHtml(window.assetToTypeMap ? window.assetToTypeMap[r.asset] : '')}</td>
            <td>${r.isin}</td>
            <td>${r.count}</td>
            <td>${money(r.amount)}</td>
            <td>${money(r.tax)}</td>
            <td>${money(r.gross)}</td>
          </tr>
        `;
      }).join("");

      // Calculate Yearly Dividend Summary
      const yearlyData = {};
      
      // Sum dividends by year
      (dividends.rows || []).forEach(row => {
        const year = new Date(row.date).getFullYear();
        if (Number.isNaN(year)) return;
        if (!yearlyData[year]) {
          yearlyData[year] = { year: year, total_net: 0, market_values: [], net_contribs: [] };
        }
        yearlyData[year].total_net += row.amount_eur;
      });
      
      // Group valuation series points by year to calculate averages
      const valueSeries = (dashboardData && dashboardData.valuation_series) || [];
      valueSeries.forEach(pt => {
        const year = new Date(pt.date).getFullYear();
        if (Number.isNaN(year)) return;
        if (!yearlyData[year]) {
          yearlyData[year] = { year: year, total_net: 0, market_values: [], net_contribs: [] };
        }
        const isTotal = (selectedReturnMode === "total");
        yearlyData[year].market_values.push(Number(isTotal ? pt.total_market_value : pt.market_value || 0));
        yearlyData[year].net_contribs.push(Number(isTotal ? pt.total_net_contributions : pt.net_contributions || 0));
      });
      
      const yearlyRows = Object.values(yearlyData).sort((a, b) => b.year - a.year);
      
      document.getElementById("dividends-yearly").innerHTML = yearlyRows.map(y => {
        const avgMarket = y.market_values.length 
          ? (y.market_values.reduce((sum, val) => sum + val, 0) / y.market_values.length)
          : 0;
        const avgContrib = y.net_contribs.length 
          ? (y.net_contribs.reduce((sum, val) => sum + val, 0) / y.net_contribs.length)
          : 0;
          
        const divYield = avgMarket > 0 ? (y.total_net / avgMarket * 100) : 0;
        const yieldOnCost = avgContrib > 0 ? (y.total_net / avgContrib * 100) : 0;
        
        return `
          <tr>
            <td>${y.year}</td>
            <td>${money(y.total_net)}</td>
            <td>${avgMarket > 0 ? money(avgMarket) : "-"}</td>
            <td class="positive" style="font-weight: 600;">${avgMarket > 0 ? `${pct.format(divYield)}%` : "-"}</td>
            <td>${avgContrib > 0 ? money(avgContrib) : "-"}</td>
            <td class="positive" style="font-weight: 600;">${avgContrib > 0 ? `${pct.format(yieldOnCost)}%` : "-"}</td>
          </tr>
        `;
      }).join("");

      document.getElementById("dividends").innerHTML = (dividends.rows || []).map(row => {
        const symbol = window.assetToSymbolMap ? window.assetToSymbolMap[row.asset] : '';
        const logoUrl = row.isin ? `https://assets.parqet.com/logos/isin/${row.isin}?format=png` : (symbol ? `https://assets.parqet.com/logos/symbol/${symbol}?format=png` : '');
        const logoImg = logoUrl ? `<img src="${logoUrl}" onerror="if(this.src.indexOf('/isin/') !== -1 && '${symbol}') { this.src = 'https://assets.parqet.com/logos/symbol/${symbol}?format=png'; } else { this.style.display='none'; }" style="width: 16px; height: 16px; border-radius: 50%; vertical-align: middle; margin-right: 6px; background: rgba(255,255,255,0.05); flex-shrink: 0;">` : '';
        return `
          <tr>
            <td>${row.date}</td>
            <td>${row.broker}</td>
            <td style="text-align: left; display: flex; align-items: center;">${logoImg}<span>${row.asset}</span>${badgeHtml(window.assetToTypeMap ? window.assetToTypeMap[row.asset] : '')}</td>
            <td>${row.isin || ""}</td>
            <td>${money(row.amount_eur)}</td>
            <td>${money(row.tax_eur)}</td>
            <td>${money(row.gross_eur)}</td>
          </tr>
        `;
      }).join("");
    }
    function renderCashInterests(data) {
      const info = data || { summary: { total_net_eur: 0.0, total_tax_eur: 0.0, total_gross_eur: 0.0, payments_count: 0 }, by_broker: [], payments: [] };
      
      document.getElementById("cash-interest-summary").textContent = 
        `${info.summary.payments_count} payments | ${money(info.summary.total_net_eur)} net`;
        
      // Render summary by broker
      document.getElementById("cash-interest-broker").innerHTML = info.by_broker && info.by_broker.length
        ? info.by_broker.map(row => `
            <tr>
              <td style="text-align: left; font-weight: 500;">${escapeHtml(row.broker)}</td>
              <td>${row.payments_count}</td>
              <td class="positive" style="font-weight: 600;">${money(row.net_eur)}</td>
              <td class="negative">${money(row.tax_eur)}</td>
              <td>${money(row.gross_eur)}</td>
            </tr>
          `).join("")
        : `<tr><td colspan="5" class="empty-state">No cash interest summary available.</td></tr>`;
        
      // Render all payments
      document.getElementById("cash-interest-payments").innerHTML = info.payments && info.payments.length
        ? info.payments.map(row => `
            <tr>
              <td>${row.date}</td>
              <td style="text-align: left; font-weight: 500;">${escapeHtml(row.broker)}</td>
              <td class="positive" style="font-weight: 600;">${money(row.net_eur)}</td>
              <td class="negative">${money(row.tax_eur)}</td>
              <td>${money(row.gross_eur)}</td>
              <td style="text-align: left; color: var(--muted); font-size: 0.9em;">${escapeHtml(row.description)}</td>
            </tr>
          `).join("")
        : `<tr><td colspan="6" class="empty-state">No interest payments recorded.</td></tr>`;
    }
    function expenseKind(row) {
      const flow = String(row.flow_kind || "");
      const category = String(row.category || "");
      if (flow === "income" || category === "Income") return "income";
      if (flow === "credit" || category === "Credits") return "credits";
      if (flow === "investment" || category === "Investments") return "investments";
      if (flow === "personal_transfer" || category === "Personal Transfers") return "transfers";
      return "spend";
    }
    function summarizeExpenseRows(rows) {
      const categoryMap = {};
      const sourceMap = {};
      const merchantMap = {};
      const monthMap = {};
      let spend = 0;
      let income = 0;
      let transfers = 0;
      let investments = 0;
      let credits = 0;
      const creditRows = [];

      (rows || []).forEach(row => {
        const amount = Number(row.amount_eur || 0);
        if (!Number.isFinite(amount) || amount === 0) return;
        const kind = expenseKind(row);
        if (kind === "income") income += amount;
        else if (kind === "credits") {
          credits += amount;
          creditRows.push(row);
        }
        else if (kind === "investments") investments += amount;
        else if (kind === "transfers") transfers += amount;
        else spend += amount;

        const category = row.category || "Uncategorized";
        categoryMap[category] ||= { category, amount: 0, count: 0 };
        categoryMap[category].amount += amount;
        categoryMap[category].count += 1;

        const source = row.source_label || row.source || "Source";
        sourceMap[source] ||= { source, spend: 0, income: 0, transfers: 0, investments: 0, credits: 0, count: 0 };
        sourceMap[source][kind] += amount;
        sourceMap[source].count += 1;

        const month = String(row.date || "").slice(0, 7);
        if (month) {
          monthMap[month] ||= { month, spend: 0, income: 0, transfers: 0, investments: 0, credits: 0, count: 0 };
          monthMap[month][kind] += amount;
          monthMap[month].count += 1;
        }

        if (kind !== "income" && kind !== "credits") {
          const merchant = row.merchant || "Unknown";
          merchantMap[merchant] ||= { merchant, category, amount: 0, count: 0 };
          merchantMap[merchant].amount += amount;
          merchantMap[merchant].count += 1;
        }
      });

      const totalOutflow = spend + investments;
      const netOutflow = totalOutflow - income;
      const categories = Object.values(categoryMap)
        .filter(row => row.category !== "Income" && row.category !== "Credits" && row.category !== "Personal Transfers")
        .map(row => ({ ...row, share: totalOutflow > 0 ? row.amount / totalOutflow * 100 : null }))
        .sort((a, b) => b.amount - a.amount);
      const sources = Object.values(sourceMap)
        .map(row => ({
          ...row,
          outflow: row.spend + row.investments,
          net: row.spend + row.investments - row.income
        }))
        .sort((a, b) => Math.abs(b.net) - Math.abs(a.net));
      const months = Object.values(monthMap)
        .map(row => ({
          ...row,
          outflow: row.spend + row.investments,
          net: row.spend + row.investments - row.income
        }))
        .sort((a, b) => String(a.month).localeCompare(String(b.month)));
      const merchants = Object.values(merchantMap).sort((a, b) => b.amount - a.amount);

      return {
        spend,
        income,
        transfers,
        investments,
        credits,
        totalOutflow,
        netOutflow,
        rows: rows || [],
        creditRows: creditRows.sort((a, b) => String(b.date || "").localeCompare(String(a.date || ""))),
        categories,
        sources,
        months,
        merchants
      };
    }
    function periodExpenses(data) {
      const source = (data && data.expenses) || { status: "empty", rows: [], message: "" };
      const start = periodStartDate(data || {});
      const rows = (source.rows || []).filter(row => !start || new Date(row.date) >= start);
      return {
        ...source,
        ...summarizeExpenseRows(rows),
        rows
      };
    }
    function renderExpenseTrend(months) {
      const svg = document.getElementById("expense-trend");
      if (!svg) return;

      const legend = document.getElementById("expense-trend-legend");
      if (legend) {
        if (selectedExpenseTrendMode === "cumulative") {
          legend.innerHTML = `
            <span style="display: inline-flex; align-items: center; gap: 4px; color: var(--text-sub, #94a3b8);">
              <i style="display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #60a5fa;"></i>
              Cumulative Outflow
            </span>
            <span style="display: inline-flex; align-items: center; gap: 4px; color: var(--text-sub, #94a3b8);">
              <i style="display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #34d399;"></i>
              Cumulative Income
            </span>
            <span style="display: inline-flex; align-items: center; gap: 4px; color: var(--text-sub, #94a3b8);">
              <i style="display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #fbbf24;"></i>
              Cumulative Net Outflow
            </span>
          `;
        } else {
          legend.innerHTML = `
            <span style="display: inline-flex; align-items: center; gap: 4px; color: var(--text-sub, #94a3b8);">
              <i style="display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #60a5fa;"></i>
              Outflow
            </span>
            <span style="display: inline-flex; align-items: center; gap: 4px; color: var(--text-sub, #94a3b8);">
              <i style="display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #34d399;"></i>
              Income
            </span>
          `;
        }
      }

      const width = 560;
      const height = 230;
      const margin = { top: 18, right: 16, bottom: 34, left: 46 };
      const rows = months || [];
      svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
      svg.setAttribute("preserveAspectRatio", "none");
      if (!rows.length) {
        svg.innerHTML = `<text x="${width / 2}" y="${height / 2}" text-anchor="middle" class="expense-label">No monthly expense rows in this window</text>`;
        return;
      }
      const plotW = width - margin.left - margin.right;
      const plotH = height - margin.top - margin.bottom;

      function getMonthYearLabel(monthStr) {
        const parts = monthStr.split("-");
        const yearShort = parts[0].slice(2);
        const monthNum = parts[1];
        const monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
        return `${monthNames[parseInt(monthNum, 10) - 1]} '${yearShort}`;
      }

      if (selectedExpenseTrendMode === "cumulative") {
        let runningOutflow = 0;
        let runningIncome = 0;
        let runningNet = 0;
        const cumulativeRows = rows.map(row => {
          runningOutflow += Number(row.outflow || 0);
          runningIncome += Number(row.income || 0);
          runningNet += Number(row.net || 0);
          return {
            month: row.month,
            outflow: runningOutflow,
            income: runningIncome,
            net: runningNet
          };
        });

        const maxVal = Math.max(1, ...cumulativeRows.flatMap(row => [row.outflow, row.income, Math.abs(row.net)]));
        const minVal = Math.min(0, ...cumulativeRows.flatMap(row => [row.outflow, row.income, row.net]));
        const yRange = maxVal - minVal;
        const yScale = v => margin.top + plotH - ((Number(v || 0) - minVal) / Math.max(1, yRange)) * plotH;
        const xScale = index => margin.left + (plotW / Math.max(1, cumulativeRows.length - 1)) * index;

        let gridLines = "";
        const tickCount = 4;
        for (let i = 0; i <= tickCount; i++) {
          const t = i / tickCount;
          const val = minVal + t * yRange;
          const y = yScale(val);
          gridLines += `
            <line class="expense-grid-line" x1="${margin.left}" y1="${y.toFixed(2)}" x2="${width - margin.right}" y2="${y.toFixed(2)}"></line>
            <text class="expense-label" x="${margin.left - 6}" y="${(y + 4).toFixed(2)}" text-anchor="end">${smartTickFormat(val)}</text>
          `;
        }

        let outflowPath = "";
        let incomePath = "";
        let netPath = "";

        cumulativeRows.forEach((row, index) => {
          const x = xScale(index).toFixed(2);
          const yOut = yScale(row.outflow).toFixed(2);
          const yInc = yScale(row.income).toFixed(2);
          const yNet = yScale(row.net).toFixed(2);

          outflowPath += `${index ? "L" : "M"}${x} ${yOut}`;
          incomePath += `${index ? "L" : "M"}${x} ${yInc}`;
          netPath += `${index ? "L" : "M"}${x} ${yNet}`;
        });

        const outflowLine = `<path class="expense-line spend" d="${outflowPath}" fill="none" stroke="#60a5fa" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"></path>`;
        const incomeLine = `<path class="expense-line income" d="${incomePath}" fill="none" stroke="#34d399" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"></path>`;
        const netLine = `<path class="expense-line net" d="${netPath}" fill="none" stroke="#fbbf24" stroke-width="2" stroke-dasharray="3,3" stroke-linecap="round" stroke-linejoin="round"></path>`;

        const dotsAndLabels = cumulativeRows.map((row, index) => {
          const x = xScale(index);
          const yOut = yScale(row.outflow);
          const yInc = yScale(row.income);
          const yNet = yScale(row.net);
          const label = getMonthYearLabel(row.month);

          const labelStep = cumulativeRows.length > 12 ? Math.ceil(cumulativeRows.length / 8) : 1;
          const showLabel = (index % labelStep === 0) || (index === cumulativeRows.length - 1);

          return `
            <circle cx="${x.toFixed(2)}" cy="${yOut.toFixed(2)}" r="4" fill="#60a5fa" stroke="var(--panel, #1e293b)" stroke-width="1.5">
              <title>${row.month} cumulative outflow: ${money(row.outflow)}</title>
            </circle>
            <circle cx="${x.toFixed(2)}" cy="${yInc.toFixed(2)}" r="4" fill="#34d399" stroke="var(--panel, #1e293b)" stroke-width="1.5">
              <title>${row.month} cumulative income: ${money(row.income)}</title>
            </circle>
            <circle cx="${x.toFixed(2)}" cy="${yNet.toFixed(2)}" r="4" fill="#fbbf24" stroke="var(--panel, #1e293b)" stroke-width="1.5">
              <title>${row.month} cumulative net: ${money(row.net)}</title>
            </circle>
            ${showLabel ? `<text class="expense-label" x="${x.toFixed(2)}" y="${height - 10}" text-anchor="middle">${escapeHtml(label)}</text>` : ""}
          `;
        }).join("");

        svg.innerHTML = `
          ${gridLines}
          ${outflowLine}
          ${incomeLine}
          ${netLine}
          ${dotsAndLabels}
        `;
      } else {
        const maxValue = Math.max(1, ...rows.flatMap(row => [row.outflow || 0, row.income || 0, Math.abs(row.net || 0)]));
        const yFor = value => margin.top + plotH - (Number(value || 0) / maxValue) * plotH;
        const groupW = plotW / rows.length;
        const barW = Math.max(5, Math.min(18, groupW * 0.24));
        const grid = [0.25, 0.5, 0.75, 1].map(step => {
          const y = margin.top + plotH - plotH * step;
          return `<line class="expense-grid-line" x1="${margin.left}" y1="${y.toFixed(2)}" x2="${width - margin.right}" y2="${y.toFixed(2)}"></line>`;
        }).join("");
        const bars = rows.map((row, index) => {
          const center = margin.left + groupW * index + groupW / 2;
          const spendY = yFor(row.outflow);
          const incomeY = yFor(row.income);
          const spendH = margin.top + plotH - spendY;
          const incomeH = margin.top + plotH - incomeY;
          const label = getMonthYearLabel(row.month);

          const labelStep = rows.length > 12 ? Math.ceil(rows.length / 8) : 1;
          const showLabel = (index % labelStep === 0) || (index === rows.length - 1);

          return `
            <rect class="expense-bar spend" x="${(center - barW - 2).toFixed(2)}" y="${spendY.toFixed(2)}" width="${barW.toFixed(2)}" height="${Math.max(0, spendH).toFixed(2)}" rx="3"><title>${row.month} outflow ${money(row.outflow)} | net ${money(row.net)}</title></rect>
            <rect class="expense-bar income" x="${(center + 2).toFixed(2)}" y="${incomeY.toFixed(2)}" width="${barW.toFixed(2)}" height="${Math.max(0, incomeH).toFixed(2)}" rx="3"><title>${row.month} income ${money(row.income)}</title></rect>
            ${showLabel ? `<text class="expense-label" x="${center.toFixed(2)}" y="${height - 10}" text-anchor="middle">${escapeHtml(label)}</text>` : ""}
          `;
        }).join("");
        svg.innerHTML = `
          ${grid}
          <line class="expense-axis" x1="${margin.left}" y1="${margin.top + plotH}" x2="${width - margin.right}" y2="${margin.top + plotH}"></line>
          <text class="expense-label" x="${margin.left - 6}" y="${margin.top + 4}" text-anchor="end">${smartTickFormat(maxValue)}</text>
          <text class="expense-label" x="${margin.left - 6}" y="${margin.top + plotH}" text-anchor="end">0</text>
          ${bars}
        `;
      }
    }
    function renderExpenses(data) {
      const expenses = periodExpenses(data);
      const unavailable = (expenses.status === "empty" || expenses.status === "unavailable") && !expenses.rows.length;
      const message = expenses.message || "No classified expense rows are available for this window.";

      window.currentExpenseRows = expenses.rows || [];

      document.getElementById("expenses-summary").textContent = unavailable
        ? "No rows"
        : `${selectedWindowLabel()} | ${money(expenses.netOutflow)} net outflow | ${expenses.rows.length} rows`;
      document.getElementById("expense-metrics").innerHTML = unavailable ? `<div class="empty-state">${escapeHtml(message)}</div>` : `
        <div class="expense-item"><span>Spend</span><strong class="negative">${money(expenses.spend)}</strong></div>
        <div class="expense-item"><span>Transfers</span><strong class="negative">${money(expenses.transfers)}</strong></div>
        <div class="expense-item"><span>Investments</span><strong class="negative">${money(expenses.investments)}</strong></div>
        <div class="expense-item"><span>Credits</span><strong>${money(expenses.credits)}</strong></div>
        <div class="expense-item"><span>Income</span><strong class="positive">${money(expenses.income)}</strong></div>
        <div class="expense-item"><span>Net outflow</span><strong class="${signedClass(-expenses.netOutflow)}">${money(expenses.netOutflow)}</strong></div>
      `;
      document.getElementById("expense-categories").innerHTML = !expenses.categories.length
        ? `<tr><td colspan="4" class="empty-state">${escapeHtml(message)}</td></tr>`
        : expenses.categories.slice(0, 12).map(row => `
          <tr style="cursor: pointer;" onclick="toggleCategorySubcategories(this, '${escapeHtml(row.category)}')">
            <td style="text-align: left; display: flex; align-items: center;">
              <svg class="category-chevron" style="width: 10px; height: 10px; margin-right: 6px; transition: transform 0.2s; fill: var(--ink-secondary); flex-shrink: 0;" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M7.21 14.77a.75.75 0 01.02-1.06L11.168 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z" clip-rule="evenodd"/></svg>
              <span>${escapeHtml(row.category)}</span>
            </td>
            <td>${row.count}</td>
            <td>${money(row.amount)}</td>
            <td>${row.share === null ? "-" : percent(row.share)}</td>
          </tr>
        `).join("");
      document.getElementById("expense-sources").innerHTML = !expenses.sources.length
        ? `<tr><td colspan="6" class="empty-state">${escapeHtml(message)}</td></tr>`
        : expenses.sources.map(row => `
          <tr>
            <td>${escapeHtml(row.source)}</td>
            <td>${row.count}</td>
            <td>${money(row.outflow)}</td>
            <td class="positive">${money(row.income)}</td>
            <td>${money(row.credits)}</td>
            <td class="${signedClass(-row.net)}">${money(row.net)}</td>
          </tr>
        `).join("");
      document.getElementById("expense-credits").innerHTML = !expenses.creditRows.length
        ? `<tr><td colspan="5" class="empty-state">No credit rows in this window.</td></tr>`
        : expenses.creditRows.slice(0, 20).map(row => `
          <tr>
            <td>${escapeHtml(row.date || "")}</td>
            <td>${escapeHtml(row.source_label || row.source || "")}</td>
            <td>${escapeHtml(row.subcategory || "")}</td>
            <td>${escapeHtml(row.merchant || "")}</td>
            <td>${money(row.amount_eur || 0)}</td>
          </tr>
        `).join("");
      document.getElementById("expense-merchants").innerHTML = !expenses.merchants.length
        ? `<tr><td colspan="4" class="empty-state">${escapeHtml(message)}</td></tr>`
        : expenses.merchants.slice(0, 15).map(row => `
          <tr>
            <td>${escapeHtml(row.merchant)}</td>
            <td>${escapeHtml(row.category)}</td>
            <td>${row.count}</td>
            <td>${money(row.amount)}</td>
          </tr>
        `).join("");
      document.getElementById("expense-rows").innerHTML = !expenses.rows.length
        ? `<tr><td colspan="6" class="empty-state">${escapeHtml(message)}</td></tr>`
        : expenses.rows.slice(0, 30).map(row => {
          const kind = expenseKind(row);
          const signedAmount = kind === "income" ? Number(row.amount_eur || 0) : (kind === "credits" ? Number(row.amount_eur || 0) : -Number(row.amount_eur || 0));
          return `
            <tr>
              <td>${escapeHtml(row.date)}</td>
              <td>${escapeHtml(row.source_label || row.source || "")}</td>
              <td>${escapeHtml(row.category || "")}</td>
              <td>${escapeHtml(row.merchant || "")}</td>
              <td style="text-align: left; color: var(--muted); max-width: 340px; overflow: hidden; text-overflow: ellipsis;">${escapeHtml(row.description || "")}</td>
              <td class="${signedClass(signedAmount)}">${money(signedAmount)}</td>
            </tr>
          `;
        }).join("");
      renderExpenseTrend(expenses.months);
    }
    window.toggleCategorySubcategories = function(rowElement, categoryName) {
      const nextRow = rowElement.nextElementSibling;
      if (nextRow && nextRow.classList.contains("subcategory-breakdown-row")) {
        nextRow.remove();
        const chevron = rowElement.querySelector(".category-chevron");
        if (chevron) chevron.style.transform = "rotate(0deg)";
        return;
      }
      
      // Remove any other expanded subcategory rows to keep UI clean
      document.querySelectorAll(".subcategory-breakdown-row").forEach(el => el.remove());
      document.querySelectorAll(".category-chevron").forEach(el => el.style.transform = "rotate(0deg)");
      
      const allRows = window.currentExpenseRows || [];
      const catRows = allRows.filter(row => (row.category || "Uncategorized") === categoryName);
      
      const subcatMap = {};
      let totalAmount = 0;
      catRows.forEach(row => {
        const subcat = (row.subcategory || "").trim() || "Unspecified";
        const amount = Number(row.amount_eur || 0);
        subcatMap[subcat] ||= { subcategory: subcat, amount: 0, count: 0 };
        subcatMap[subcat].amount += amount;
        subcatMap[subcat].count += 1;
        totalAmount += amount;
      });
      
      const subcategories = Object.values(subcatMap).sort((a, b) => b.amount - a.amount);
      
      const subtableHtml = `
        <tr class="subcategory-breakdown-row" style="background: rgba(255, 255, 255, 0.015);">
          <td colspan="4" style="padding: 12px 16px 16px 28px; border-bottom: 1px solid var(--line);">
            <div style="border-left: 2px solid var(--green); padding-left: 12px; margin-top: 4px;">
              <h4 style="font-size: 11px; font-weight: 600; text-transform: uppercase; color: var(--ink-secondary); margin-bottom: 8px; letter-spacing: 0.05em; text-align: left;">Subcategories for ${escapeHtml(categoryName)}</h4>
              <table style="width: 100%; font-size: 12px; border-collapse: collapse;">
                <thead>
                  <tr style="border-bottom: 1px solid rgba(255, 255, 255, 0.05); color: var(--ink-secondary); font-weight: 500;">
                    <th style="text-align: left; padding: 4px 8px;">Subcategory</th>
                    <th style="text-align: right; padding: 4px 8px; width: 60px;">Rows</th>
                    <th style="text-align: right; padding: 4px 8px; width: 100px;">Amount</th>
                    <th style="text-align: right; padding: 4px 8px; width: 80px;">Share</th>
                  </tr>
                </thead>
                <tbody>
                  ${subcategories.map(sub => {
                    const pctShare = totalAmount > 0 ? (sub.amount / totalAmount * 100).toFixed(1) : "0.0";
                    return `
                      <tr style="border-bottom: 1px solid rgba(255, 255, 255, 0.03); color: var(--ink;); cursor: pointer;" onclick="showSubcategoryDetails('${escapeHtml(categoryName)}', '${escapeHtml(sub.subcategory)}')">
                        <td style="text-align: left; padding: 6px 8px; font-weight: 500; text-decoration: underline; text-underline-offset: 2px; text-decoration-color: rgba(255,255,255,0.2);">${escapeHtml(sub.subcategory)}</td>
                        <td style="text-align: right; padding: 6px 8px;">${sub.count}</td>
                        <td style="text-align: right; padding: 6px 8px; font-weight: 600; color: var(--green);">${money(sub.amount)}</td>
                        <td style="text-align: right; padding: 6px 8px; color: var(--ink-secondary);">${pctShare}%</td>
                      </tr>
                    `;
                  }).join("")}
                </tbody>
              </table>
            </div>
          </td>
        </tr>
      `;
      
      rowElement.insertAdjacentHTML("afterend", subtableHtml);
      const chevron = rowElement.querySelector(".category-chevron");
      if (chevron) chevron.style.transform = "rotate(90deg)";
    };
    window.showSubcategoryDetails = function(categoryName, subcategoryName) {
      const allRows = window.currentExpenseRows || [];
      window.currentSubcatRows = allRows.filter(row => 
        (row.category || "Uncategorized") === categoryName &&
        ((row.subcategory || "").trim() || "Unspecified") === subcategoryName
      );
      window.currentSubcatSort = { column: "date", direction: "desc" };
      window.currentSubcatCategory = categoryName;
      window.currentSubcatName = subcategoryName;

      // Sort initially by date desc
      window.currentSubcatRows.sort((a, b) => String(b.date || "").localeCompare(String(a.date || "")));

      window.renderSubcategoryDetailsModal();
    };

    window.renderSubcategoryDetailsModal = function() {
      const categoryName = window.currentSubcatCategory;
      const subcategoryName = window.currentSubcatName;
      const rows = window.currentSubcatRows || [];
      const sort = window.currentSubcatSort || { column: "date", direction: "desc" };

      const indicator = col => {
        if (sort.column !== col) return "";
        return sort.direction === "asc" ? " &#9650;" : " &#9660;"; // ▲ or ▼
      };

      const subcatRowsHtml = rows.map(row => {
        const kind = expenseKind(row);
        const signedAmount = kind === "income" ? Number(row.amount_eur || 0) : (kind === "credits" ? Number(row.amount_eur || 0) : -Number(row.amount_eur || 0));
        const amountClass = signedAmount > 0 ? "positive" : (signedAmount < 0 ? "negative" : "");
        return `
          <tr style="border-bottom: 1px solid rgba(255, 255, 255, 0.03);">
            <td style="padding: 6px 8px; font-family: monospace;">${escapeHtml(row.date)}</td>
            <td style="padding: 6px 8px;">${escapeHtml(row.source_label || row.source || "")}</td>
            <td style="padding: 6px 8px; font-weight: 500; color: var(--ink);">${escapeHtml(row.merchant || "")}</td>
            <td style="padding: 6px 8px; color: var(--ink-secondary); max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${escapeHtml(row.description || "")}">${escapeHtml(row.description || "")}</td>
            <td style="padding: 6px 8px; text-align: right; font-weight: 600;" class="${amountClass}">${money(signedAmount)}</td>
          </tr>
        `;
      }).join("");

      const html = `
        <div class="table-wrap" style="margin-top: 8px;">
          <table style="width: 100%; border-collapse: collapse; font-size: 12.5px;">
            <thead>
              <tr style="border-bottom: 1px solid var(--line-strong); color: var(--ink-secondary); font-weight: 500;">
                <th style="text-align: left; padding: 6px 8px; width: 85px; cursor: pointer; user-select: none;" onclick="window.sortSubcategoryDetails('date')">Date${indicator('date')}</th>
                <th style="text-align: left; padding: 6px 8px; width: 85px; cursor: pointer; user-select: none;" onclick="window.sortSubcategoryDetails('source')">Source${indicator('source')}</th>
                <th style="text-align: left; padding: 6px 8px; width: 120px; cursor: pointer; user-select: none;" onclick="window.sortSubcategoryDetails('merchant')">Merchant${indicator('merchant')}</th>
                <th style="text-align: left; padding: 6px 8px; cursor: pointer; user-select: none;" onclick="window.sortSubcategoryDetails('description')">Description${indicator('description')}</th>
                <th style="text-align: right; padding: 6px 8px; width: 95px; cursor: pointer; user-select: none;" onclick="window.sortSubcategoryDetails('amount')">Amount${indicator('amount')}</th>
              </tr>
            </thead>
            <tbody>
              ${subcatRowsHtml}
            </tbody>
          </table>
        </div>
      `;

      const title = `${escapeHtml(categoryName)} &gt; ${escapeHtml(subcategoryName)} (${rows.length} rows)`;
      window.showInfoModal(title, html);
    };

    window.sortSubcategoryDetails = function(columnName) {
      const sort = window.currentSubcatSort;
      if (sort.column === columnName) {
        sort.direction = sort.direction === "asc" ? "desc" : "asc";
      } else {
        sort.column = columnName;
        sort.direction = (columnName === "date" || columnName === "amount") ? "desc" : "asc";
      }

      const multiplier = sort.direction === "asc" ? 1 : -1;

      window.currentSubcatRows.sort((a, b) => {
        if (columnName === "date") {
          return multiplier * String(a.date || "").localeCompare(String(b.date || ""));
        }
        if (columnName === "source") {
          const sA = String(a.source_label || a.source || "");
          const sB = String(b.source_label || b.source || "");
          return multiplier * sA.localeCompare(sB);
        }
        if (columnName === "merchant") {
          return multiplier * String(a.merchant || "").localeCompare(String(b.merchant || ""));
        }
        if (columnName === "description") {
          return multiplier * String(a.description || "").localeCompare(String(b.description || ""));
        }
        if (columnName === "amount") {
          const getVal = row => {
            const kind = expenseKind(row);
            return kind === "income" ? Number(row.amount_eur || 0) : (kind === "credits" ? Number(row.amount_eur || 0) : -Number(row.amount_eur || 0));
          };
          return multiplier * (getVal(a) - getVal(b));
        }
        return 0;
      });

      window.renderSubcategoryDetailsModal();
    };
    function renderNetContributions(contributions) {
      document.getElementById("contributions-summary").textContent = `${money(contributions.net_eur)} net | ${money(contributions.total_buys_eur)} buys | ${money(contributions.total_sells_eur)} sells`;
      document.getElementById("contributions-broker").innerHTML = contributions.by_broker.map(row => `
        <tr>
          <td>${row.broker}</td>
          <td>${money(row.buys_eur)}</td>
          <td>${money(row.sells_eur)}</td>
          <td class="${signedClass(row.net_eur)}">${money(row.net_eur)}</td>
          <td>${percent(row.share_pct)}</td>
        </tr>
      `).join("");
      document.getElementById("contributions-date").innerHTML = contributions.by_date.slice(0, 20).map(row => `
        <tr>
          <td>${row.date}</td>
          <td>${money(row.buys_eur)}</td>
          <td>${money(row.sells_eur)}</td>
          <td class="${signedClass(row.net_eur)}">${money(row.net_eur)}</td>
        </tr>
      `).join("");
    }
    function periodStartDate(data) {
      if (selectedPeriod === "all") return null;
      if (selectedPeriod === "since24") return new Date("2024-01-11");
      const valueSeries = data.valuation_series || [];
      const endValue = valueSeries.length ? valueSeries[valueSeries.length - 1].date : data.date_range.end;
      const start = new Date(endValue || Date.now());
      if (selectedPeriod === "ytd") {
        start.setMonth(0);
        start.setDate(1);
      }
      if (selectedPeriod === "1w") start.setDate(start.getDate() - 7);
      if (selectedPeriod === "1m") start.setMonth(start.getMonth() - 1);
      if (selectedPeriod === "1y") start.setFullYear(start.getFullYear() - 1);
      return start;
    }
    function periodFrictions(data) {
      const source = data.frictions || { status: "unavailable", rows: [], message: "" };
      if (source.status !== "available") return { ...source, by_broker: [], rows: [] };

      const start = periodStartDate(data);
      const rows = (source.rows || []).filter(row => !start || new Date(row.date) >= start);
      const brokerMap = {};
      let costs = 0;
      let taxes = 0;
      let dividendTax = 0;
      rows.forEach(row => {
        const amount = Number(row.amount_eur || 0);
        brokerMap[row.broker] ||= { broker: row.broker, costs_eur: 0, taxes_eur: 0, dividend_tax_eur: 0, total_eur: 0 };
        if (row.type === "cost") {
          costs += amount;
          brokerMap[row.broker].costs_eur += amount;
        } else if (row.type === "dividend_tax") {
          dividendTax += amount;
          brokerMap[row.broker].dividend_tax_eur += amount;
          brokerMap[row.broker].taxes_eur += amount;
        } else {
          taxes += amount;
          brokerMap[row.broker].taxes_eur += amount;
        }
        brokerMap[row.broker].total_eur += amount;
      });
      const totalTaxes = taxes + dividendTax;
      const totalDrag = costs + totalTaxes;
      const totals = periodMetrics(data);
      return {
        status: "available",
        message: "",
        total_costs_eur: costs,
        total_taxes_eur: totalTaxes,
        trade_taxes_eur: taxes,
        dividend_tax_eur: dividendTax,
        total_drag_eur: totalDrag,
        net_liquidation_eur: Number(totals.market_value || 0) - totalDrag,
        by_broker: Object.values(brokerMap).sort((a, b) => Math.abs(b.total_eur) - Math.abs(a.total_eur)),
        rows
      };
    }
    function renderFrictions(data) {
      const frictions = periodFrictions(data);
      const unavailable = frictions.status !== "available";
      const message = frictions.message || "No tax or broker cost events are available for this portfolio.";
      document.getElementById("frictions-summary").textContent = unavailable
        ? "Not available"
        : `${selectedWindowLabel()} | ${money(frictions.total_drag_eur)} total drag`;
      document.getElementById("friction-metrics").innerHTML = unavailable ? `<div class="empty-state">${message}</div>` : `
        <div class="friction-item"><span>Taxes paid</span><strong>${money(frictions.total_taxes_eur)}</strong></div>
        <div class="friction-item"><span>Costs paid</span><strong>${money(frictions.total_costs_eur)}</strong></div>
        <div class="friction-item"><span>Total drag</span><strong>${money(frictions.total_drag_eur)}</strong></div>
        <div class="friction-item"><span>Net liquidation</span><strong>${money(frictions.net_liquidation_eur)}</strong></div>
      `;
      document.getElementById("frictions-broker").innerHTML = unavailable || !frictions.by_broker.length
        ? `<tr><td colspan="5" class="empty-state">${message}</td></tr>`
        : frictions.by_broker.map(row => `
          <tr>
            <td>${row.broker}</td>
            <td>${money(row.costs_eur)}</td>
            <td>${money(row.taxes_eur)}</td>
            <td>${money(row.dividend_tax_eur)}</td>
            <td>${money(row.total_eur)}</td>
          </tr>
        `).join("");
      document.getElementById("frictions-events").innerHTML = unavailable || !frictions.rows.length
        ? `<tr><td colspan="5" class="empty-state">${message}</td></tr>`
        : frictions.rows.slice(0, 30).map(row => `
          <tr>
            <td>${row.date}</td>
            <td>${row.broker}</td>
            <td>${row.type_label}</td>
            <td>${row.description}</td>
            <td class="${signedClass(row.amount_eur)}">${money(row.amount_eur)}</td>
          </tr>
        `).join("");

      // Render Tax Loss Carry-forwards
      const losses = data.tax_losses || [];
      const lossesWrap = document.getElementById("tax-losses-wrap");
      if (lossesWrap) {
        if (losses.length > 0) {
          lossesWrap.style.display = "block";
          document.getElementById("tax-losses-tbody").innerHTML = losses.map(row => `
            <tr>
              <td>${row.year}</td>
              <td>${row.broker}</td>
              <td class="red">${money(row.amount_eur)}</td>
              <td>31/12/${row.expires_year}</td>
            </tr>
          `).join("");
        } else {
          lossesWrap.style.display = "none";
        }
      }
    }
    function renderCoverage(data) {
      const open = data.positions.filter(p => p.is_open);
      const priced = open.filter(p => p.pricing_status === "priced").length;
      const pct = open.length ? Math.round(priced / open.length * 100) : 0;
      if (data.valuation_status.status === "snapshot") {
        document.getElementById("coverage-bar").style.width = open.length ? "100%" : "0%";
        document.getElementById("coverage-text").textContent = `${open.length} snapshot assets`;
        document.getElementById("mapping-status").innerHTML = `<div>Values come from the uploaded monthly CSV snapshot.</div>`;
        return;
      }
      document.getElementById("coverage-bar").style.width = `${pct}%`;
      document.getElementById("coverage-text").textContent = `${priced}/${open.length} open assets priced`;
      document.getElementById("mapping-status").innerHTML = `
        <div>${data.mapping_status.filled_isins}/${data.mapping_status.total_rows} mapping rows have ISINs.</div>
        <div>${data.mapping_status.missing_in_mapping.length} assets are missing from the mapping CSV.</div>
      `;
    }
    function calculateReturnStats(portfolioReturns, msciReturns, xeonReturns) {
      const rfDaily = 0.03 / 252;
      const sqrt252 = Math.sqrt(252);
      const mean = values => values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0;
      const variance = (values, avg) => values.length ? values.reduce((sum, value) => sum + Math.pow(value - avg, 2), 0) / values.length : 0;
      const statsFor = values => {
        const avg = mean(values);
        const varValue = variance(values, avg);
        const std = Math.sqrt(varValue);
        const sharpe = std > 0 ? ((avg - rfDaily) / std * sqrt252) : 0;
        return {
          daily_variance_pct: varValue * 10000,
          daily_volatility_pct: std * 100,
          annualized_volatility_pct: std * sqrt252 * 100,
          sharpe_ratio: sharpe,
          mean_daily_return_pct: avg * 100
        };
      };
      return {
        portfolio: statsFor(portfolioReturns),
        msci: statsFor(msciReturns),
        xeon: statsFor(xeonReturns)
      };
    }
    function statsForSelectedWindow(data, mode) {
      const stats = data.stats;
      const rows = (stats && stats.daily_returns) || [];
      if (!rows.length) {
        return {
          statsData: stats ? stats[mode] : null,
          daysEvaluated: stats ? stats.days_evaluated : 0,
          startDate: stats ? stats.start_date : "",
          endDate: stats ? stats.end_date : "",
          returns: { portfolio: [], msci: [], xeon: [] }
        };
      }

      const start = periodStartDate(data);
      const windowRows = rows.filter(row => !start || new Date(row.date) >= start);
      const key = mode === "price_return" ? "price_return" : "total_return";
      const numericValue = value => value === null || value === undefined ? null : Number(value);
      const portfolioReturns = windowRows.map(row => numericValue(row[key])).filter(Number.isFinite);
      const msciReturns = windowRows.map(row => numericValue(row.msci_return)).filter(Number.isFinite);
      const xeonReturns = windowRows.map(row => numericValue(row.xeon_return)).filter(Number.isFinite);

      if (portfolioReturns.length < 2) {
        return {
          statsData: null,
          daysEvaluated: portfolioReturns.length,
          startDate: windowRows[0] ? windowRows[0].date : "",
          endDate: windowRows.length ? windowRows[windowRows.length - 1].date : "",
          returns: { portfolio: portfolioReturns, msci: msciReturns, xeon: xeonReturns }
        };
      }

      return {
        statsData: calculateReturnStats(portfolioReturns, msciReturns, xeonReturns),
        daysEvaluated: portfolioReturns.length,
        startDate: windowRows[0] ? windowRows[0].date : "",
        endDate: windowRows.length ? windowRows[windowRows.length - 1].date : "",
        returns: { portfolio: portfolioReturns, msci: msciReturns, xeon: xeonReturns }
      };
    }
    function signedReturnPct(value) {
      if (!Number.isFinite(Number(value))) return "-";
      const n = Number(value);
      return `${n >= 0 ? "+" : ""}${pct.format(n)}%`;
    }
    function quantile(sortedValues, q) {
      if (!sortedValues.length) return 0;
      const pos = (sortedValues.length - 1) * q;
      const base = Math.floor(pos);
      const rest = pos - base;
      const next = sortedValues[base + 1];
      return next === undefined ? sortedValues[base] : sortedValues[base] + rest * (next - sortedValues[base]);
    }
    function distributionMeta(values) {
      const pctValues = (values || []).map(value => Number(value) * 100).filter(Number.isFinite).sort((a, b) => a - b);
      if (!pctValues.length) return "No data";
      const meanValue = pctValues.reduce((sum, value) => sum + value, 0) / pctValues.length;
      const medianValue = quantile(pctValues, 0.5);
      const lowValue = quantile(pctValues, 0.05);
      const highValue = quantile(pctValues, 0.95);
      return `n=${pctValues.length}<br>mean ${signedReturnPct(meanValue)} | median ${signedReturnPct(medianValue)}<br>5-95% ${signedReturnPct(lowValue)} to ${signedReturnPct(highValue)}`;
    }
    function returnDistributionDomain(portfolioReturns, msciReturns) {
      const values = [...(portfolioReturns || []), ...(msciReturns || [])]
        .map(value => Number(value) * 100)
        .filter(Number.isFinite);
      const maxAbs = Math.max(0.25, ...values.map(value => Math.abs(value)));
      const padded = maxAbs * 1.08;
      const step = padded <= 1 ? 0.25 : padded <= 3 ? 0.5 : padded <= 8 ? 1 : 2;
      const limit = Math.ceil(padded / step) * step;
      return { min: -limit, max: limit };
    }
    function histogramForReturns(values, domain, bins) {
      const pctValues = (values || []).map(value => Number(value) * 100).filter(Number.isFinite);
      const counts = Array.from({ length: bins }, () => 0);
      const width = (domain.max - domain.min) / bins;
      pctValues.forEach(value => {
        const rawIndex = Math.floor((value - domain.min) / width);
        const index = Math.max(0, Math.min(bins - 1, rawIndex));
        counts[index] += 1;
      });
      const meanValue = pctValues.length ? pctValues.reduce((sum, value) => sum + value, 0) / pctValues.length : 0;
      return { counts, meanValue, values: pctValues };
    }
    function renderHistogramSvg(svgId, histogram, domain, yMax, seriesClass) {
      const svg = document.getElementById(svgId);
      if (!svg) return;
      const values = histogram.values || [];
      if (values.length < 2) {
        svg.setAttribute("viewBox", "0 0 520 210");
        svg.innerHTML = `<text x="260" y="108" text-anchor="middle" class="hist-label">Not enough daily returns for this window</text>`;
        return;
      }

      const width = 520;
      const height = 210;
      const margin = { top: 14, right: 18, bottom: 32, left: 36 };
      const plotW = width - margin.left - margin.right;
      const plotH = height - margin.top - margin.bottom;
      const bins = histogram.counts.length;
      const binW = plotW / bins;
      const domainWidth = domain.max - domain.min;
      const xFor = value => margin.left + ((value - domain.min) / domainWidth) * plotW;
      const yFor = count => margin.top + plotH - (count / Math.max(1, yMax)) * plotH;
      const bars = histogram.counts.map((count, index) => {
        const x = margin.left + index * binW + 1.5;
        const y = yFor(count);
        const h = margin.top + plotH - y;
        return `<rect class="hist-bar ${seriesClass}" x="${x.toFixed(2)}" y="${y.toFixed(2)}" width="${Math.max(1, binW - 3).toFixed(2)}" height="${Math.max(0, h).toFixed(2)}" rx="3"><title>${count} days</title></rect>`;
      }).join("");
      const zeroLine = domain.min < 0 && domain.max > 0
        ? `<line class="hist-zero-line" x1="${xFor(0).toFixed(2)}" y1="${margin.top}" x2="${xFor(0).toFixed(2)}" y2="${margin.top + plotH}"></line>`
        : "";
      const meanX = xFor(histogram.meanValue);
      const grid = [0.25, 0.5, 0.75, 1].map(step => {
        const y = margin.top + plotH - plotH * step;
        return `<line class="hist-grid-line" x1="${margin.left}" y1="${y.toFixed(2)}" x2="${margin.left + plotW}" y2="${y.toFixed(2)}"></line>`;
      }).join("");
      svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
      svg.innerHTML = `
        ${grid}
        <line class="hist-axis" x1="${margin.left}" y1="${margin.top + plotH}" x2="${margin.left + plotW}" y2="${margin.top + plotH}"></line>
        ${zeroLine}
        ${bars}
        <line class="hist-mean-line ${seriesClass}" x1="${meanX.toFixed(2)}" y1="${margin.top}" x2="${meanX.toFixed(2)}" y2="${margin.top + plotH}"><title>Mean ${signedReturnPct(histogram.meanValue)}</title></line>
        <text class="hist-label" x="${margin.left}" y="${height - 10}" text-anchor="start">${signedReturnPct(domain.min)}</text>
        <text class="hist-label" x="${xFor(0).toFixed(2)}" y="${height - 10}" text-anchor="middle">0%</text>
        <text class="hist-label" x="${margin.left + plotW}" y="${height - 10}" text-anchor="end">${signedReturnPct(domain.max)}</text>
        <text class="hist-label" x="${margin.left}" y="${margin.top + 10}" text-anchor="start">${yMax} days</text>
      `;
    }
    function renderReturnDistributions(windowStats) {
      const returns = windowStats.returns || { portfolio: [], msci: [] };
      const portfolioReturns = returns.portfolio || [];
      const msciReturns = returns.msci || [];
      const domain = returnDistributionDomain(portfolioReturns, msciReturns);
      const bins = 18;
      const portfolioHistogram = histogramForReturns(portfolioReturns, domain, bins);
      const msciHistogram = histogramForReturns(msciReturns, domain, bins);
      const yMax = Math.max(1, ...portfolioHistogram.counts, ...msciHistogram.counts);

      const summary = document.getElementById("stats-dist-summary");
      if (summary) {
        summary.textContent = `${selectedWindowLabel()} | same daily-return bins | dashed line = mean`;
      }
      const portfolioMeta = document.getElementById("stats-port-dist-meta");
      if (portfolioMeta) portfolioMeta.innerHTML = distributionMeta(portfolioReturns);
      const msciMeta = document.getElementById("stats-msci-dist-meta");
      if (msciMeta) msciMeta.innerHTML = distributionMeta(msciReturns);

      renderHistogramSvg("stats-port-dist", portfolioHistogram, domain, yMax, "portfolio");
      renderHistogramSvg("stats-msci-dist", msciHistogram, domain, yMax, "msci");
    }
    function renderStats(data) {
      const statsSection = document.getElementById("stats-section");
      if (!statsSection) return;
      
      const stats = data.stats;
      if (!stats) {
        statsSection.style.display = "none";
        return;
      }
      
      statsSection.style.display = "block";
      
      const mode = (selectedReturnMode === "price") ? "price_return" : "total_return";
      const modeLabel = (selectedReturnMode === "price") ? "Price Return (securities only)" : "Total Return (including cash & dividends)";
      const windowStats = statsForSelectedWindow(data, mode);
      const statsData = windowStats.statsData;
      
      if (!statsData) {
        statsSection.style.display = "none";
        return;
      }
      
      document.getElementById("stats-summary").textContent = 
        `${windowStats.daysEvaluated} trading days evaluated | period: ${windowStats.startDate} to ${windowStats.endDate} | window: ${selectedWindowLabel()} | mode: ${modeLabel}`;
      
      const p = statsData.portfolio;
      document.getElementById("stats-port-mean").textContent = `${p.mean_daily_return_pct.toFixed(4)}%`;
      document.getElementById("stats-port-var").textContent = `${p.daily_variance_pct.toFixed(4)}%² (${(p.daily_variance_pct / 10000).toFixed(8)})`;
      document.getElementById("stats-port-daily-vol").textContent = `${p.daily_volatility_pct.toFixed(4)}%`;
      document.getElementById("stats-port-ann-vol").textContent = `${p.annualized_volatility_pct.toFixed(2)}%`;
      document.getElementById("stats-port-sharpe").textContent = p.sharpe_ratio.toFixed(2);
      renderReturnDistributions(windowStats);
      
      const m = statsData.msci;
      document.getElementById("stats-msci-mean").textContent = `${m.mean_daily_return_pct.toFixed(4)}%`;
      document.getElementById("stats-msci-var").textContent = `${m.daily_variance_pct.toFixed(4)}%² (${(m.daily_variance_pct / 10000).toFixed(8)})`;
      document.getElementById("stats-msci-daily-vol").textContent = `${m.daily_volatility_pct.toFixed(4)}%`;
      document.getElementById("stats-msci-ann-vol").textContent = `${m.annualized_volatility_pct.toFixed(2)}%`;
      document.getElementById("stats-msci-sharpe").textContent = m.sharpe_ratio.toFixed(2);
      
      const x = statsData.xeon;
      if (x) {
        document.getElementById("stats-xeon-mean").textContent = `${x.mean_daily_return_pct.toFixed(4)}%`;
        document.getElementById("stats-xeon-var").textContent = `${x.daily_variance_pct.toFixed(4)}%² (${(x.daily_variance_pct / 10000).toFixed(8)})`;
        document.getElementById("stats-xeon-daily-vol").textContent = `${x.daily_volatility_pct.toFixed(4)}%`;
        document.getElementById("stats-xeon-ann-vol").textContent = `${x.annualized_volatility_pct.toFixed(2)}%`;
        document.getElementById("stats-xeon-sharpe").textContent = x.sharpe_ratio.toFixed(2);
      }
    }
    function selectorButtonLabel(button) {
      return button.dataset.label || (button.querySelector(".selector-label")?.textContent || button.textContent || "").trim();
    }
    function brokerLogoClass(broker) {
      const key = String(broker || "all").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
      return key || "all";
    }
    function brokerLogoMark(broker) {
      const key = String(broker || "all").toLowerCase();
      if (key === "all") {
        return `<svg viewBox="0 0 24 24"><rect x="4" y="4" width="6" height="6" rx="1.5"/><rect x="14" y="4" width="6" height="6" rx="1.5"/><rect x="4" y="14" width="6" height="6" rx="1.5"/><rect x="14" y="14" width="6" height="6" rx="1.5"/></svg>`;
      }
      if (key === "crypto wallet") {
        return `<svg viewBox="0 0 24 24"><path d="M19 7H5a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2Z"/><path d="M16 12h3"/><path d="M17 7V5a2 2 0 0 0-2-2H6"/></svg>`;
      }
      const marks = {
        "fineco": "F",
        "interactive brokers": "IB",
        "trade republic": "TR",
        "etoro": "eT",
        "bbva": "BB",
        "mediolanum": "M",
        "manual": "M"
      };
      if (marks[key]) return escapeHtml(marks[key]);
      const initials = String(broker || "")
        .replace(/[^A-Za-z0-9 ]+/g, " ")
        .trim()
        .split(/\s+/)
        .filter(Boolean)
        .map(word => word[0])
        .join("")
        .slice(0, 2)
        .toUpperCase();
      return escapeHtml(initials || "W");
    }
    function brokerLogoHtml(broker) {
      return `<span class="broker-logo ${brokerLogoClass(broker)}" aria-hidden="true">${brokerLogoMark(broker)}</span>`;
    }
    function renderBrokerButtons(brokers) {
      const container = document.getElementById("brokers");
      if (!brokers || brokers.length <= 1) {
        container.style.display = "none";
        container.innerHTML = "";
        return;
      }
      container.style.display = "flex";
      
      const list = brokers.includes("all") ? brokers : ["all", ...brokers];
      
      container.innerHTML = list.map(b => {
        const brokerKey = String(b || "all").toLowerCase();
        const activeClass = selectedBroker === brokerKey ? "active" : "";
        const label = b === "all" ? "All Brokers" : b;
        return `<button type="button" data-broker="${escapeHtml(brokerKey)}" data-label="${escapeHtml(label)}" title="${escapeHtml(label)}" class="${activeClass}">
          ${brokerLogoHtml(b)}
          <span class="selector-label">${escapeHtml(label)}</span>
        </button>`;
      }).join("");

      container.querySelectorAll("button").forEach(button => {
        button.addEventListener("click", () => {
          if (selectedBroker === button.dataset.broker) return;
          selectedBroker = button.dataset.broker;
          resetHoldingsView();
          selectedPeriod = defaultPeriodForSelection();
          updatePeriodButtons();
          container.querySelectorAll("button").forEach(item => item.classList.toggle("active", item === button));
          load(false, `Filtering ${selectorButtonLabel(button)}`);
        });
      });
    }
    function formatRankingPct(val) {
      if (val === null || val === undefined) return `<span style="color:var(--muted)">—</span>`;
      const num = Number(val);
      const sign = num > 0 ? "+" : "";
      const color = num > 0 ? "var(--green)" : (num < 0 ? "var(--red)" : "var(--muted)");
      return `<span style="color:${color};font-weight:600">${sign}${num.toFixed(2)}%</span>`;
    }

    function renderRankings(data) {
      if (!data) return;
      const rankingsTbody = document.getElementById("rankings-tbody");
      const windowLabel = document.getElementById("rankings-window-label");
      if (!rankingsTbody || !windowLabel) return;
      
      const isTotal = (selectedReturnMode === "total");
      const modeKey = isTotal ? "total" : "price";
      
      const commonDateStr = data.common_start_date || "—";
      const ytdDateStr = data.ytd_start_date || "—";
      windowLabel.innerHTML = `Common alignment from <span style="color:var(--violet);font-weight:600">${commonDateStr}</span> | YTD from <span style="color:var(--amber);font-weight:600">${ytdDateStr}</span>`;

      const sorted = [...data.rankings].sort((a, b) => {
        let valA = 0.0;
        let valB = 0.0;
        if (a.returns && a.returns[modeKey]) {
          valA = a.returns[modeKey][rankingsSort.key] || 0.0;
        }
        if (b.returns && b.returns[modeKey]) {
          valB = b.returns[modeKey][rankingsSort.key] || 0.0;
        }
        return rankingsSort.direction === "desc" ? valB - valA : valA - valB;
      });

      rankingsTbody.innerHTML = sorted.map(user => {
        const ret = user.returns[modeKey] || {};
        const startVal = ret.start;
        const commonVal = ret.common;
        const ytdVal = ret.ytd;
        
        const isCurrentPerson = (user.person === selectedPerson);
        const rowStyle = isCurrentPerson ? 'background: rgba(96, 165, 250, 0.08); font-weight: 500;' : '';
        const nameStyle = isCurrentPerson ? 'color: var(--blue); font-weight: 700;' : '';

        return `
          <tr style="${rowStyle}">
            <td style="text-align: left; display: flex; align-items: center; gap: 8px;">
              <span class="user-avatar ${user.person}" aria-hidden="true">
                <svg viewBox="0 0 24 24"><path d="M20 21a8 8 0 0 0-16 0"/><circle cx="12" cy="7" r="4"/></svg>
              </span>
              <span style="${nameStyle}">${escapeHtml(user.name)}</span>
            </td>
            <td>${formatRankingPct(startVal)}</td>
            <td>${formatRankingPct(commonVal)}</td>
            <td>${formatRankingPct(ytdVal)}</td>
          </tr>
        `;
      }).join("");
    }

    function updateRankingsHeaders() {
      ["start", "common", "ytd"].forEach(k => {
        const el = document.getElementById(`rank-header-${k}`);
        if (!el) return;
        let title = k === "start" ? "Return (Start of Portfolio)" : (k === "common" ? "Return (Common Alignment)" : "Return (YTD)");
        if (rankingsSort.key === k) {
          const arrow = rankingsSort.direction === "desc" ? " ↓" : " ↑";
          el.textContent = title + arrow;
          el.style.color = "var(--ink)";
        } else {
          el.textContent = title;
          el.style.color = "";
        }
      });
    }

    window.sortRankings = function(key) {
      if (rankingsSort.key === key) {
        rankingsSort.direction = rankingsSort.direction === "desc" ? "asc" : "desc";
      } else {
        rankingsSort.key = key;
        rankingsSort.direction = "desc";
      }
      updateRankingsHeaders();
      if (rankingsData) {
        renderRankings(rankingsData);
      }
    };

    function renderDashboard(data) {
      updatePeriodButtons();
      // Check if MyStyle is in the portfolio to show/hide and setup fee calculator
      const hasMyStyle = (data.positions || []).some(p => p.asset.toLowerCase().includes("mystyle"));
      const calcSection = document.getElementById("mystyle-calc-section");
      const breakdownSection = document.getElementById("mystyle-breakdown-section");
      if (calcSection) {
        if (hasMyStyle) {
          calcSection.style.display = "block";
          if (breakdownSection) breakdownSection.style.display = "block";
          const mystylePos = data.positions.find(p => p.asset.toLowerCase().includes("mystyle"));
          if (mystylePos) {
            const cap = Math.round(mystylePos.market_value_eur);
            document.getElementById("input-start-cap").value = cap;
            document.getElementById("input-start-cap").max = Math.max(1000000, cap * 2);
          }
          updateCalculator();
        } else {
          calcSection.style.display = "none";
          if (breakdownSection) breakdownSection.style.display = "none";
        }
      }

      // Build symbol and type lookup maps for company logos and badges
      const assetToSymbol = {};
      const assetToType = {};
      const symbolToIsin = {};
      (data.positions || []).forEach(p => {
        if (p.symbol) assetToSymbol[p.asset] = p.symbol;
        if (p.asset_type) assetToType[p.asset] = p.asset_type;
        if (p.symbol && p.isin) symbolToIsin[p.symbol.toUpperCase()] = p.isin;
      });
      window.assetToSymbolMap = assetToSymbol;
      window.assetToTypeMap = assetToType;
      window.symbolToIsinMap = symbolToIsin;
      if (!((data.distribution || {}).composition_sources || []).some(row => sourceKey(row) === selectedDistributionSource)) {
        selectedDistributionSource = "";
      }

      renderMetrics(periodMetrics(data));
      renderRankings(rankingsData);
      renderValueCharts(data.valuation_series || []);
      renderChart(data.series);
      renderPositions(data.positions);
      renderDistribution(data.distribution);
      renderDividends(data.dividends);
      renderCashInterests(data.cash_interests);
      renderExpenses(data);
      renderNetContributions(data.net_contributions);
      renderFrictions(data);
      renderCoverage(data);
      renderStats(data);
      renderBrokerButtons(data.brokers);
      
      // Render optional actions supplied by the selected portfolio profile.
      const todosSection = document.getElementById("todos-section");
      if (todosSection) {
        const todoItems = Array.isArray(data.todo_items) ? data.todo_items : [];
        if (todoItems.length) {
          todosSection.style.display = "block";
          document.getElementById("todos-list").innerHTML = todoItems
            .map(item => `<li style="margin-bottom: 8px;">${escapeHtml(item)}</li>`)
            .join("");
        } else {
          todosSection.style.display = "none";
        }
      }

      document.getElementById("range").textContent = chartRangeLabel(data.series || []);
      document.getElementById("value-window").textContent = selectedWindowLabel();
      document.getElementById("meta").textContent = `${data.trade_source}: ${data.trade_count} trades, ${data.asset_count} assets, updated ${data.generated_at}`;
      updateExportSummary();
    }
    function renderChartsOnly() {
      if (!dashboardData) return;
      renderValueCharts(dashboardData.valuation_series || []);
      renderChart(dashboardData.series || []);
      document.getElementById("range").textContent = chartRangeLabel(dashboardData.series || []);
      document.getElementById("value-window").textContent = selectedWindowLabel();
      updateExportSummary();
    }
    function scheduleChartResize() {
      if (!dashboardData) return;
      window.clearTimeout(chartResizeTimer);
      chartResizeTimer = window.setTimeout(renderChartsOnly, 80);
    }
    async function load(refresh = false, label = "Updating dashboard") {
      const requestId = ++loadRequestId;
      const button = document.getElementById("refresh");
      const error = document.getElementById("error");
      button.disabled = true;
      error.style.display = "none";
      setDashboardBusy(true, label);
      try {
        const params = currentQueryParams();
        if (refresh) params.set("refresh", "1");
        const [portfolioRes, rankingsRes] = await Promise.all([
          fetch(`/api/portfolio?${params.toString()}`),
          fetch(`/api/rankings?${params.toString()}`)
        ]);
        const data = await portfolioRes.json();
        if (!portfolioRes.ok) throw new Error(data.error || "Dashboard request failed.");
        if (rankingsRes.ok) {
          rankingsData = await rankingsRes.json();
        } else {
          const rankErr = await rankingsRes.json();
          console.warn("Rankings failed to load:", rankErr.error);
        }
        if (requestId !== loadRequestId) return;
        dashboardData = data;
        renderDashboard(data);
        loadNews(refresh, data.news_symbols || []);
        loadWatchlist(refresh);
      } catch (err) {
        if (requestId !== loadRequestId) return;
        error.textContent = err.message;
        error.style.display = "block";
      } finally {
        if (requestId === loadRequestId) {
          button.disabled = false;
          setDashboardBusy(false);
        }
      }
    }
    document.querySelectorAll("#periods button").forEach(button => {
      button.addEventListener("click", () => {
        if (button.dataset.period === "since24" && !canUseSince24Window()) return;
        if (selectedPeriod === button.dataset.period) return;
        selectedPeriod = button.dataset.period;
        updatePeriodButtons();
        if (dashboardData) withRedrawVeil("Redrawing selected window", () => renderDashboard(dashboardData));
      });
    });
    document.querySelectorAll("#persons button").forEach(button => {
      button.addEventListener("click", () => {
        if (selectedPerson === button.dataset.person) return;
        selectedPerson = button.dataset.person;
        selectedBroker = "all";
        resetHoldingsView();
        selectedPeriod = defaultPeriodForSelection();
        updatePeriodButtons();
        document.querySelectorAll("#persons button").forEach(item => item.classList.toggle("active", item === button));
        load(false, `Switching to ${selectorButtonLabel(button)}`);
      });
    });
    document.querySelectorAll("#berkshire-mode button").forEach(button => {
      button.addEventListener("click", () => {
        if (selectedBerkshireMode === button.dataset.berkshire) return;
        selectedBerkshireMode = button.dataset.berkshire;
        document.querySelectorAll("#berkshire-mode button").forEach(item => item.classList.toggle("active", item === button));
        load(false, `Applying ${button.textContent.trim()}`);
      });
    });
    document.querySelectorAll("#proxy-mode button").forEach(button => {
      button.addEventListener("click", () => {
        if (selectedProxyMode === button.dataset.proxy) return;
        selectedProxyMode = button.dataset.proxy;
        document.querySelectorAll("#proxy-mode button").forEach(item => item.classList.toggle("active", item === button));
        load(false, `Applying ${button.textContent.trim()}`);
      });
    });
    document.querySelectorAll("#live-mode button").forEach(button => {
      button.addEventListener("click", () => {
        if (selectedLiveMode === button.dataset.live) return;
        selectedLiveMode = button.dataset.live;
        resetHoldingsView();
        document.querySelectorAll("#live-mode button").forEach(item => item.classList.toggle("active", item === button));
        load(false, `Applying ${button.textContent.trim()}`);
      });
    });
    document.querySelectorAll("#return-mode button").forEach(button => {
      button.addEventListener("click", () => {
        if (selectedReturnMode === button.dataset.returnMode) return;
        selectedReturnMode = button.dataset.returnMode;
        document.querySelectorAll("#return-mode button").forEach(item => item.classList.toggle("active", item === button));
        if (dashboardData) {
          withRedrawVeil(`Switching to ${button.textContent.trim()}`, () => renderDashboard(dashboardData));
        }
      });
    });
    document.querySelectorAll("th[data-sort]").forEach(th => {
      th.addEventListener("click", () => {
        const key = th.dataset.sort;
        if (sortState.key === key) {
          sortState.direction = sortState.direction === "asc" ? "desc" : "asc";
        } else {
          sortState = { key, direction: ["asset", "isin", "symbol", "pricing_status"].includes(key) ? "asc" : "desc" };
        }
        if (dashboardData) renderPositions(dashboardData.positions);
      });
    });
    document.getElementById("refresh").addEventListener("click", () => {
      load(true, "Refreshing live prices");
    });
    document.getElementById("export-button").addEventListener("click", exportDashboard);

    const toggleMonthly = document.getElementById("expense-toggle-monthly");
    const toggleCumulative = document.getElementById("expense-toggle-cumulative");
    if (toggleMonthly && toggleCumulative) {
      toggleMonthly.addEventListener("click", () => {
        if (selectedExpenseTrendMode === "monthly") return;
        selectedExpenseTrendMode = "monthly";
        toggleMonthly.classList.add("active");
        toggleCumulative.classList.remove("active");
        toggleMonthly.style.background = "var(--blue)";
        toggleMonthly.style.color = "white";
        toggleCumulative.style.background = "transparent";
        toggleCumulative.style.color = "var(--text-sub, #94a3b8)";
        if (dashboardData) {
          const expenses = periodExpenses(dashboardData);
          renderExpenseTrend(expenses.months);
        }
      });
      toggleCumulative.addEventListener("click", () => {
        if (selectedExpenseTrendMode === "cumulative") return;
        selectedExpenseTrendMode = "cumulative";
        toggleCumulative.classList.add("active");
        toggleMonthly.classList.remove("active");
        toggleCumulative.style.background = "var(--blue)";
        toggleCumulative.style.color = "white";
        toggleMonthly.style.background = "transparent";
        toggleMonthly.style.color = "var(--text-sub, #94a3b8)";
        if (dashboardData) {
          const expenses = periodExpenses(dashboardData);
          renderExpenseTrend(expenses.months);
        }
      });
    }

    // Watchlist add bindings
    const addInput = document.getElementById("watchlist-add-input");
    const addBtn = document.getElementById("watchlist-add-btn");
    if (addBtn && addInput) {
      const addTickerAction = async () => {
        const ticker = addInput.value.trim();
        if (!ticker) return;
        addBtn.disabled = true;
        const originalText = addBtn.textContent;
        addBtn.textContent = "Adding…";
        try {
          const res = await fetch("/api/watchlist", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ticker: ticker, action: "add" })
          });
          const rData = await res.json();
          if (!res.ok) throw new Error(rData.error || "Failed to add ticker.");
          addInput.value = "";
          renderWatchlist(rData.watchlist || []);
        } catch (err) {
          alert(err.message);
        } finally {
          addBtn.disabled = false;
          addBtn.textContent = originalText;
        }
      };
      addBtn.addEventListener("click", addTickerAction);
      addInput.addEventListener("keydown", event => {
        if (event.key === "Enter") {
          addTickerAction();
        }
      });
    }
    const btnShowAllHoldings = document.getElementById("btn-show-all-holdings");
    btnShowAllHoldings.addEventListener("click", () => {
      showAllHoldings = !showAllHoldings;
      if (dashboardData) renderPositions(dashboardData.positions);
    });
    const btnClosed = document.getElementById("btn-toggle-closed");
    btnClosed.addEventListener("click", () => {
      showClosed = !showClosed;
      if (dashboardData) renderPositions(dashboardData.positions);
    });
    if ("ResizeObserver" in window) {
      const chartObserver = new ResizeObserver(scheduleChartResize);
      document.querySelectorAll(".chart-wrap").forEach(item => chartObserver.observe(item));
    }
    window.addEventListener("resize", scheduleChartResize);

    // Fee Compounding Calculator Logic
    function updateCalculator() {
      const cap = parseFloat(document.getElementById("input-start-cap").value);
      const years = parseInt(document.getElementById("input-horizon").value);
      const gross = parseFloat(document.getElementById("input-gross-ret").value) / 100.0;
      const mystyleFee = parseFloat(document.getElementById("input-mystyle-fee").value) / 100.0;
      const etfFee = parseFloat(document.getElementById("input-etf-fee").value) / 100.0;
      
      document.getElementById("lbl-start-cap").textContent = "€" + cap.toLocaleString("it-IT");
      document.getElementById("lbl-horizon").textContent = years + " years";
      document.getElementById("lbl-gross-ret").textContent = (gross * 100).toFixed(1) + "%";
      document.getElementById("lbl-mystyle-fee").textContent = (mystyleFee * 100).toFixed(2) + "%";
      document.getElementById("lbl-etf-fee").textContent = (etfFee * 100).toFixed(2) + "%";
      
      const mystyleNet = gross - mystyleFee;
      const etfNet = gross - etfFee;
      
      document.getElementById("val-mystyle-net-ret").textContent = (mystyleNet * 100).toFixed(2) + "%";
      document.getElementById("val-etf-net-ret").textContent = (etfNet * 100).toFixed(2) + "%";
      
      const mystyleProj = cap * Math.pow(1 + mystyleNet, years);
      const etfProj = cap * Math.pow(1 + etfNet, years);
      const lost = etfProj - mystyleProj;
      
      document.getElementById("val-proj-mystyle").textContent = "€" + Math.round(mystyleProj).toLocaleString("it-IT");
      document.getElementById("val-proj-etf").textContent = "€" + Math.round(etfProj).toLocaleString("it-IT");
      document.getElementById("val-lost-fees").textContent = "€" + Math.round(lost).toLocaleString("it-IT");
      
      const pct = etfProj > 0 ? (mystyleProj / etfProj * 100) : 0;
      document.getElementById("bar-pct-mystyle").textContent = pct.toFixed(1) + "%";
      document.getElementById("bar-mystyle").style.width = pct.toFixed(1) + "%";
    }

    ["input-start-cap", "input-horizon", "input-gross-ret", "input-mystyle-fee", "input-etf-fee"].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.addEventListener("input", updateCalculator);
    });

    initializeSectionIdentity();
    initializeSectionWrapButtons();
    load(false, "Loading dashboard");
  </script>
</body>
</html>
"""


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8050)
