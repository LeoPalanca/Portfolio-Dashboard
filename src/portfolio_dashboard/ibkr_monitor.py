"""Read-only broker cash and indicative whole-share affordability.

No order interfaces are exposed. Yahoo reference prices are never execution quotes.
"""

from __future__ import annotations

import json
import math
import os
import re
import secrets
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from flask import Blueprint

# Dated top-100 S&P 500 securities by market cap; not a live index ranking.
WATCHLIST = (
    "AAPL",
    "NVDA",
    "MSFT",
    "AMZN",
    "GOOGL",
    "GOOG",
    "META",
    "AVGO",
    "TSLA",
    "BRK-B",
    "LLY",
    "WMT",
    "JPM",
    "V",
    "MU",
    "XOM",
    "AMD",
    "JNJ",
    "MA",
    "ABBV",
    "COST",
    "CVX",
    "KO",
    "PG",
    "CSCO",
    "PLTR",
    "MRK",
    "UNH",
    "HD",
    "BAC",
    "ORCL",
    "GE",
    "PM",
    "MS",
    "INTC",
    "NFLX",
    "RTX",
    "TXN",
    "WFC",
    "PANW",
    "AMAT",
    "TMO",
    "CAT",
    "AMGN",
    "GS",
    "LIN",
    "LRCX",
    "IBM",
    "CRWD",
    "AXP",
    "GILD",
    "DIS",
    "GEV",
    "DELL",
    "ABT",
    "ANET",
    "MCD",
    "C",
    "PEP",
    "VZ",
    "NEE",
    "BLK",
    "WELL",
    "DE",
    "CRM",
    "UNP",
    "APH",
    "ADI",
    "PFE",
    "TMUS",
    "KLAC",
    "QCOM",
    "ISRG",
    "COP",
    "ACN",
    "SCHW",
    "DHR",
    "TJX",
    "T",
    "CB",
    "UBER",
    "PGR",
    "SPGI",
    "VRTX",
    "BA",
    "MDT",
    "LMT",
    "BMY",
    "MO",
    "SYK",
    "LOW",
    "ETN",
    "MCK",
    "BKNG",
    "COF",
    "NEM",
    "PLD",
    "ADP",
    "SBUX",
    "MRVL",
)
UNIVERSE_DATE = "2026-11-06"
UNIVERSE_SOURCE = "https://www.slickcharts.com/sp500/marketcap"


def positive(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) and number > 0 else None
    except (TypeError, ValueError):
        return None


def reference_quote(symbol: str) -> dict[str, Any]:
    """Fetch public prices only; broker identifiers never leave this machine."""
    try:
        req = urllib.request.Request(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=5d",
            headers={"User-Agent": "Mozilla/5.0 PortfolioDashboard"},
        )
        with urllib.request.urlopen(req, timeout=12) as response:
            payload = response.read(2_000_001)
        if len(payload) > 2_000_000:
            raise ValueError("Price response too large")
        result = json.loads(payload)["chart"]["result"][0]
        meta = result["meta"]
        closes = [positive(x) for x in result["indicators"]["quote"][0]["close"]]
        previous = positive(meta.get("previousClose")) or (closes[-2] if len(closes) > 1 else None)
        price = positive(meta.get("regularMarketPrice"))
        stamp = positive(meta.get("regularMarketTime"))
        return {
            "symbol": symbol,
            "price_usd": price if meta.get("currency") == "USD" else None,
            "previous_close_usd": previous,
            "change_pct": (price / previous - 1) * 100 if price and previous else None,
            "price_time": stamp,
            "source": "Yahoo Finance reference price",
        }
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        return {"symbol": symbol, "price_usd": None, "price_time": None, "source": "Yahoo Finance reference price"}


def affordability(
    cash: float | None, usd_per_base: float | None, quotes: list[dict[str, Any]], now: float
) -> list[dict[str, Any]]:
    """Unknown/stale data stays unknown. Costs are an explicit estimate, not a quote."""
    rate = positive(usd_per_base)
    budget = max(0.0, cash) * rate if cash is not None and math.isfinite(cash) and rate else None
    rows = []
    for quote in quotes:
        price, stamp = positive(quote.get("price_usd")), positive(quote.get("price_time"))
        usable = bool(price and stamp and -60 <= now - stamp <= 4 * 86400)
        cost = price + 1.0 if price and usable else None
        maximum = max(0, math.floor((budget - 1.0) / price)) if budget is not None and usable and price else None
        rows.append(
            {
                **quote,
                "reference_usable": usable,
                "estimated_one_share_cost_usd": cost,
                "whole_shares_with_cash": maximum,
            }
        )
    return rows


def broker_cash(port: int | None = None, suffix: str | None = None) -> dict[str, Any]:
    """Use the fixed loopback bridge; the web app needs no broker SDK or credentials."""
    url = "http://127.0.0.1:8766/cash"
    if port is not None and suffix is not None:
        url += f"?port={port}&suffix={suffix}"
    with urllib.request.urlopen(url, timeout=30) as response:
        raw = response.read(64001)
    if len(raw) > 64000:
        raise ValueError("Broker response too large")
    result = json.loads(raw)
    if not isinstance(result, dict) or not all(
        key in result
        for key in ("base_currency", "cash_budget_base", "equity_base", "broker_captured_at", "account_masked")
    ):
        raise ValueError("Incomplete broker response")
    return result


def collect(port: int | None = None, suffix: str | None = None) -> dict[str, Any]:
    cash = broker_cash(port, suffix)
    return collect_market(cash)


def collect_market(cash: dict[str, Any]) -> dict[str, Any]:
    """Public market scan, also usable by research with explicitly cached/unknown cash."""
    currency = cash["base_currency"]
    symbols = WATCHLIST + ((currency + "USD=X",) if currency != "USD" else ())
    with ThreadPoolExecutor(max_workers=5) as pool:
        quotes = list(pool.map(reference_quote, symbols))
    fx = quotes.pop() if currency != "USD" else None
    now = datetime.now(UTC)
    rate = fx["price_usd"] if fx else 1.0
    if fx and (not fx["price_time"] or not -60 <= now.timestamp() - fx["price_time"] <= 4 * 86400):
        rate = None
    return {
        **cash,
        "captured_at": now.isoformat(),
        "usd_per_base": rate,
        "fx_reference": fx,
        "execution_enabled": False,
        "prices_are_executable": False,
        "commission_reserve_usd": 1.0,
        "universe_date": UNIVERSE_DATE,
        "universe_source": UNIVERSE_SOURCE,
        "rows": affordability(cash["cash_budget_base"], rate, quotes, now.timestamp()),
    }


def create_ibkr_blueprint(data_dir: Path) -> Blueprint:
    from flask import Blueprint, jsonify, render_template, request

    blueprint = Blueprint("ibkr", __name__)
    token = secrets.token_urlsafe(32)
    lock = threading.Lock()
    state: dict[str, Any] = {"running": False, "snapshot": None, "error": None}
    snapshot_path = data_dir / "ibkr_monitor.json"

    def status() -> dict[str, Any]:
        with lock:
            result = dict(state)
        if result["snapshot"] is None:
            try:
                cached = json.loads(snapshot_path.read_text())
                result["snapshot"] = cached if isinstance(cached, dict) else None
            except (OSError, ValueError):
                pass
        try:
            with urllib.request.urlopen("http://127.0.0.1:8766/analysis", timeout=1) as response:
                raw = response.read(128001)
            report = json.loads(raw) if len(raw) <= 128000 else None
            result["analysis"] = report if isinstance(report, dict) else None
        except (OSError, ValueError):
            result["analysis"] = None
        result["execution_enabled"] = False
        snapshot = result["snapshot"]
        try:
            captured = datetime.fromisoformat(snapshot["captured_at"])
            result["snapshot_stale"] = (datetime.now(UTC) - captured).total_seconds() > 1800
        except (TypeError, KeyError, ValueError):
            result["snapshot_stale"] = True
        return result

    def refresh(port: int | None = None, suffix: str | None = None) -> None:
        try:
            snapshot = collect(port, suffix)
            snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = snapshot_path.with_suffix(".tmp")
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as handle:
                json.dump(snapshot, handle, allow_nan=False)
            os.replace(temporary, snapshot_path)
            with lock:
                state.update(snapshot=snapshot, error=None)
        except Exception:  # noqa: BLE001 -- redact all broker exceptions at the HTTP boundary
            # Broker exception text may include identifiers. Never return it to the browser.
            with lock:
                state["error"] = (
                    "Could not refresh the saved IBKR connection. Check that Gateway on your Mac is signed in and connected to Karin."
                )
        finally:
            with lock:
                state["running"] = False

    @blueprint.get("/ibkr")
    def page():
        from .version import APP_VERSION

        return render_template("ibkr.html", token=token, app_version=APP_VERSION)

    @blueprint.get("/api/ibkr")
    def api_status():
        return jsonify(status())

    @blueprint.post("/api/ibkr/refresh")
    def api_refresh():
        origin = request.headers.get("Origin")
        if not secrets.compare_digest(request.headers.get("X-IBKR-Token", ""), token) or (
            origin and origin.rstrip("/") != request.host_url.rstrip("/")
        ):
            return jsonify(error="Reload the monitor page before refreshing."), 403
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify(error="Invalid refresh request."), 400
        suffix, port = body.get("account_suffix"), body.get("port")
        if body and (
            not isinstance(suffix, str)
            or not re.fullmatch(r"\d{4}", suffix)
            or type(port) is not int
            or port not in (4001, 4002)
        ):
            return jsonify(error="Use four account digits and Gateway port 4001 or 4002."), 400
        with lock:
            if state["running"]:
                return jsonify(error="A refresh is already running."), 409
            state.update(running=True, error=None)
        threading.Thread(target=refresh, args=(port, suffix), daemon=True, name="ibkr-monitor").start()
        return jsonify(running=True), 202

    return blueprint
