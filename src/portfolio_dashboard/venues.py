"""Price a fund on the listing its broker would sell it on.

A fund is listed on many exchanges, in several currencies. Trade Republic trades it on
Lang & Schwarz in EUR, whose quotes follow the fund's Xetra EUR line; Fineco holds
funds on Borsa Italiana, or on Xetra when Milan does not list them. Yahoo's ISIN
search returns whichever listing it ranks first (often a USD line in London), so the
listing is looked up with OpenFIGI, which maps an ISIN to its ticker on every
exchange, and is kept only when Yahoo has prices for it.

Shares are left to the ISIN search, which already returns their home market, and a
manual mapping always wins. Set ``PORTFOLIO_VENUE_LOOKUP=off`` to skip the lookups.
"""

from __future__ import annotations

import json
import os
import urllib.request
from collections.abc import Callable, Iterable, Mapping, MutableMapping
from datetime import date
from decimal import Decimal
from typing import Any, Protocol

OPENFIGI_URL = "https://api.openfigi.com/v3/mapping"
# OpenFIGI refuses larger requests from a client without an API key.
OPENFIGI_BATCH = 5
LISTINGS_TTL = 90 * 86400
RETRY_AFTER = 86400
# OpenFIGI exchange codes and the Yahoo suffix of the same listing (GR: German composite, Xetra).
YAHOO_SUFFIX = {"GR": ".DE", "GY": ".DE", "IM": ".MI"}
FUND_VENUES: dict[str, tuple[str, ...]] = {
    "Trade Republic": ("GR", "GY"),
    "Fineco": ("IM", "GR", "GY"),
}
FUND_TYPES = frozenset({"ETP"})

Listing = tuple[str, str, str]  # exchange code, ticker, security type


class TradeLike(Protocol):
    asset: str
    isin: str
    broker: str
    date: date
    quantity_diff: Decimal


def lookups_enabled() -> bool:
    return os.environ.get("PORTFOLIO_VENUE_LOOKUP", "on").strip().casefold() not in {"off", "0", "false", "no"}


def openfigi_listings(isins: list[str], timeout: float = 20) -> dict[str, list[Listing] | None]:
    """Every listing OpenFIGI knows for each ISIN; None for an ISIN whose lookup failed."""

    found: dict[str, list[Listing] | None] = {}
    for start in range(0, len(isins), OPENFIGI_BATCH):
        batch = isins[start : start + OPENFIGI_BATCH]
        body = json.dumps([{"idType": "ID_ISIN", "idValue": isin} for isin in batch]).encode()
        request = urllib.request.Request(OPENFIGI_URL, data=body, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                results = json.load(response)
        except (OSError, ValueError):
            found.update(dict.fromkeys(batch))
            continue
        for isin, item in zip(batch, results if isinstance(results, list) else [], strict=False):
            if not isinstance(item, dict) or item.get("error"):
                found[isin] = None
                continue
            # "No identifier found" comes back as a warning: a known answer, not a failure.
            found[isin] = [
                (str(row.get("exchCode") or ""), str(row.get("ticker") or ""), str(row.get("securityType") or ""))
                for row in item.get("data") or []
            ]
    return found


def holding_brokers(trades: Iterable[TradeLike]) -> dict[str, tuple[str, str]]:
    """``isin -> (broker, asset name)``: the broker holding most of it now, or the last one that did."""

    held: dict[str, dict[str, Decimal]] = {}
    last: dict[str, tuple[date, str, str]] = {}
    names: dict[tuple[str, str], str] = {}
    for trade in trades:
        if not trade.isin or not trade.broker:
            continue
        isin = trade.isin.upper()
        brokers = held.setdefault(isin, {})
        brokers[trade.broker] = brokers.get(trade.broker, Decimal(0)) + trade.quantity_diff
        names[(isin, trade.broker)] = trade.asset
        if isin not in last or trade.date >= last[isin][0]:
            last[isin] = (trade.date, trade.broker, trade.asset)
    chosen: dict[str, tuple[str, str]] = {}
    for isin, brokers in held.items():
        broker, quantity = max(brokers.items(), key=lambda item: (item[1], item[0]))
        if quantity <= 0:
            broker = last[isin][1]
        chosen[isin] = (broker, names[(isin, broker)])
    return chosen


def venue_mappings(
    trades: Iterable[TradeLike],
    manual: Mapping[str, Mapping[str, str]],
    cache: MutableMapping[str, Any],
    has_prices: Callable[[str], bool],
    now: int,
    fetch: Callable[[list[str]], dict[str, list[Listing] | None]] | None = None,
) -> dict[str, dict[str, str]]:
    """Mappings, keyed by asset name, for funds held at a broker with a venue rule.

    ``cache`` keeps OpenFIGI's answers and which Yahoo symbols have prices between
    calls; the caller persists it. Funds whose listing the user chose by hand (a
    manual row with a ticker) are left alone.
    """

    if not lookups_enabled():
        return {}
    # A manual row without a ticker only records the ISIN; it does not pick a listing.
    pinned = {name for name, entry in manual.items() if entry.get("ticker")}
    pinned_isins = {str(manual[name].get("isin") or "").upper() for name in pinned}
    wanted = {
        isin: (broker, asset)
        for isin, (broker, asset) in holding_brokers(trades).items()
        if broker in FUND_VENUES and isin not in pinned_isins and asset not in pinned
    }

    def due(isin: str) -> bool:
        entry = cache.get(isin)
        if not isinstance(entry, dict):
            return True
        age = now - int(entry.get("fetched_at") or 0)
        return age >= (RETRY_AFTER if entry.get("listings") is None else LISTINGS_TTL)

    missing = sorted(isin for isin in wanted if due(isin))
    if missing:
        for isin, listings in (fetch or openfigi_listings)(missing).items():
            cache[isin] = {"listings": listings, "fetched_at": now, "checked": {}}

    mappings: dict[str, dict[str, str]] = {}
    for isin, (broker, asset) in sorted(wanted.items()):
        entry = cache.get(isin) or {}
        listings = [tuple(item) for item in entry.get("listings") or []]
        if not any(kind in FUND_TYPES for _code, _ticker, kind in listings):
            continue
        checked = entry.setdefault("checked", {})
        for code in FUND_VENUES[broker]:
            for ticker in sorted({ticker for exchange, ticker, _kind in listings if exchange == code and ticker}):
                symbol = f"{ticker}{YAHOO_SUFFIX[code]}"
                result = checked.get(symbol)
                if not isinstance(result, dict) or (not result.get("ok") and now - int(result.get("at") or 0) >= RETRY_AFTER):
                    result = {"ok": bool(has_prices(symbol)), "at": now}
                    checked[symbol] = result
                if result["ok"]:
                    mappings[asset] = {"isin": isin, "ticker": symbol, "exchange": "", "source": "venue"}
                    break
            if asset in mappings:
                break
    return mappings


def with_venue_mappings(manual: Mapping[str, Mapping[str, str]], venues: Mapping[str, Mapping[str, str]]) -> dict[str, dict[str, str]]:
    """Manual mappings plus venue listings; a venue fills in only a row without a ticker."""

    merged = {name: dict(entry) for name, entry in manual.items()}
    for name, entry in venues.items():
        if not (merged.get(name) or {}).get("ticker"):
            # The row's other columns (its benchmark class) stay as the user set them.
            merged[name] = {"benchmark_class": "", **merged.get(name, {}), **entry}
    return merged
