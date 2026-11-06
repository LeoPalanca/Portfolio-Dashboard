"""Public research evidence: existing dashboard news, price history and analyst views."""

from __future__ import annotations

import json
import math
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def numeric(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def shortlist(snapshot: dict[str, Any], limit: int = 6) -> list[str]:
    rows = [
        r
        for r in snapshot["rows"]
        if r.get("reference_usable")
        and (numeric(r.get("whole_shares_with_cash")) or 0) > 0
        and numeric(r.get("change_pct")) is not None
    ]
    rows.sort(key=lambda r: (r["change_pct"], r["symbol"]))
    return [r["symbol"] for r in rows[:limit]]


def read_json(url: str, timeout: int = 15) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 PortfolioDashboard"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError("Research response too large")
    return json.loads(raw)


def dashboard_news(url: str, symbols: list[str]) -> dict[str, Any]:
    """Explicit symbols prevent the dashboard from selecting private portfolio holdings."""
    result: dict[str, Any] = {
        "source": "Portfolio Dashboard / Yahoo Finance RSS",
        "retrieved_at": now_iso(),
        "status": "unavailable",
        "items": [],
        "errors": [],
    }
    if not symbols:
        return result
    try:
        query = urllib.parse.urlencode({"symbols": ",".join(symbols)})
        payload = read_json(url.rstrip("/") + "/api/news?" + query, timeout=90)
        result["dashboard_generated_at"] = payload.get("generated_at")
        counts: dict[str, int] = {}
        for item in payload.get("items", []):
            symbol = item.get("symbol")
            if symbol not in symbols or counts.get(symbol, 0) >= 4:
                continue
            link = str(item.get("link") or "")
            if urllib.parse.urlsplit(link).scheme not in {"http", "https"}:
                continue
            title = " ".join(str(item.get("title") or "").split())[:350]
            if not title:
                continue
            counts[symbol] = counts.get(symbol, 0) + 1
            result["items"].append(
                {
                    "id": f"NEWS-{len(result['items']) + 1}",
                    "symbol": symbol,
                    "title": title,
                    "link": link[:1500],
                    "published": str(item.get("published") or "")[:80],
                    "source": str(item.get("source") or "Yahoo Finance")[:100],
                    "coverage": "headline only; full article not fetched",
                }
            )
        result["errors"] = [
            {"symbol": item.get("symbol"), "status": "unavailable"}
            for item in payload.get("errors", [])
            if item.get("symbol") in symbols
        ]
        result["status"] = "available" if result["items"] else "unavailable"
    except (OSError, ValueError, KeyError, TypeError):
        result["errors"] = [{"symbol": s, "status": "dashboard news unavailable"} for s in symbols]
    return result


def history_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload["chart"]["result"][0]
    series = result["indicators"]["adjclose"][0]["adjclose"]
    bars = []
    for stamp, raw in zip(result["timestamp"], series):
        value = numeric(raw)
        if value is not None and value > 0:
            bars.append((int(stamp), value))
    bars.sort()
    if not bars:
        raise ValueError("No adjusted price history")
    latest_time, latest = bars[-1]
    result_data: dict[str, Any] = {
        "status": "available",
        "source": "Yahoo Finance daily chart",
        "basis": "split/dividend-adjusted daily closes; partial current-session bar may be present",
        "last_bar_date": datetime.fromtimestamp(latest_time, UTC).date().isoformat(),
        "last_bar_timestamp": datetime.fromtimestamp(latest_time, UTC).isoformat(),
        "retrieved_at": now_iso(),
        "observations": len(bars),
        "windows": {},
    }
    for window in (20, 60, 252):
        if len(bars) < window:
            result_data["windows"][str(window)] = None
            continue
        sample = bars[-window:]
        peak_time, peak = max(sample, key=lambda p: p[1])
        running_peak = sample[0][1]
        worst = 0.0
        for _, value in sample:
            running_peak = max(running_peak, value)
            worst = min(worst, (value / running_peak - 1) * 100)
        result_data["windows"][str(window)] = {
            "sessions": window,
            "drawdown_from_window_high_pct": (latest / peak - 1) * 100,
            "high_as_of": datetime.fromtimestamp(peak_time, UTC).isoformat(),
            "max_drawdown_in_window_pct": worst,
        }
    for sessions in (5, 20):
        result_data[f"return_{sessions}_sessions_pct"] = (
            (latest / bars[-sessions - 1][1] - 1) * 100 if len(bars) > sessions else None
        )
    return result_data


def price_history(symbol: str) -> dict[str, Any]:
    try:
        encoded = urllib.parse.quote(symbol, safe="")
        return history_metrics(
            read_json(f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}?interval=1d&range=2y")
        )
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        return {"status": "unavailable", "retrieved_at": now_iso(), "source": "Yahoo Finance daily chart"}


def analyst_views(symbol: str) -> dict[str, Any]:
    """Retrieval time is never presented as the date analysts issued their ratings."""
    import yfinance as yf  # type: ignore[import-untyped]

    result: dict[str, Any] = {
        "source": "Yahoo Finance / yfinance",
        "retrieved_at": now_iso(),
        "status": "unavailable",
        "rating_as_of": None,
        "target_as_of": None,
        "rating_counts": None,
        "targets": None,
        "recent_changes": [],
        "errors": [],
    }
    ticker = yf.Ticker(symbol)
    try:
        info = ticker.get_info()
        consensus = {
            "recommendationKey": str(info.get("recommendationKey") or "")[:80],
            "recommendationMean": numeric(info.get("recommendationMean")),
            "numberOfAnalystOpinions": numeric(info.get("numberOfAnalystOpinions")),
        }
        result["consensus"] = consensus
        if info.get("currency") == "USD":
            targets = {
                key: numeric(info.get(field))
                for key, field in (
                    ("low", "targetLowPrice"),
                    ("mean", "targetMeanPrice"),
                    ("median", "targetMedianPrice"),
                    ("high", "targetHighPrice"),
                )
            }
            if any(value is not None and value > 0 for value in targets.values()):
                result["targets"] = {
                    **targets,
                    "currency": "USD",
                    "horizon": "provider consensus, typically 12 months; not a short-term exit target",
                }
        result["valuation"] = {key: numeric(info.get(key)) for key in ("trailingPE", "forwardPE", "priceToBook")}
        result["sector"] = info.get("sector")
    except Exception:  # noqa: BLE001 -- partial provider failures must not erase other evidence
        result["errors"].append("consensus/target lookup failed")
    try:
        frame = ticker.get_recommendations_summary()
        if frame is not None and not frame.empty:
            current = frame[frame["period"] == "0m"]
            if not current.empty:
                row = current.iloc[0]
                result["rating_counts"] = {
                    key: numeric(row.get(key)) for key in ("strongBuy", "buy", "hold", "sell", "strongSell")
                }
                result["rating_period"] = "0m provider summary; individual issue dates unknown"
    except Exception:  # noqa: BLE001 -- public provider availability varies by field
        result["errors"].append("rating counts unavailable")
    try:
        frame = ticker.get_upgrades_downgrades()
        if frame is not None and not frame.empty:
            for stamp, row in frame.sort_index(ascending=False).head(5).iterrows():
                result["recent_changes"].append(
                    {
                        "issued_at": stamp.isoformat(),
                        "firm": str(row.get("Firm", ""))[:120],
                        "from_grade": str(row.get("FromGrade", ""))[:80],
                        "to_grade": str(row.get("ToGrade", ""))[:80],
                        "action": str(row.get("Action", ""))[:80],
                    }
                )
    except Exception:  # noqa: BLE001 -- missing changes must not imply no analyst changes
        result["errors"].append("recent upgrades/downgrades unavailable")
    if (
        result.get("targets")
        or result.get("rating_counts")
        or result.get("recent_changes")
        or any(result.get("consensus", {}).values())
    ):
        result["status"] = "partial" if result["errors"] else "available"
    return result


def build_evidence(snapshot: dict[str, Any], dashboard_url: str) -> dict[str, Any]:
    symbols = shortlist(snapshot)
    with ThreadPoolExecutor(max_workers=4) as pool:
        news_future = pool.submit(dashboard_news, dashboard_url, symbols)
        benchmark_future = pool.submit(price_history, "SPY")
        histories = {s: pool.submit(price_history, s) for s in symbols}
        analysts = {s: pool.submit(analyst_views, s) for s in symbols}
        news, benchmark = news_future.result(), benchmark_future.result()
        stocks: list[dict[str, Any]] = []
        for symbol in symbols:
            history, views = histories[symbol].result(), analysts[symbol].result()
            if (
                history.get("status") == "available"
                and benchmark.get("status") == "available"
                and history["last_bar_date"] == benchmark["last_bar_date"]
            ):
                stock_return, market_return = (
                    history.get("return_20_sessions_pct"),
                    benchmark.get("return_20_sessions_pct"),
                )
                history["excess_20_session_return_vs_spy_pct"] = (
                    stock_return - market_return if stock_return is not None and market_return is not None else None
                )
            stocks.append(
                {
                    "symbol": symbol,
                    "history_id": f"HISTORY-{symbol}",
                    "history": history,
                    "analyst_id": f"ANALYST-{symbol}",
                    "analysts": views,
                }
            )
    return {
        "generated_at": now_iso(),
        "scope": "Six largest session declines within the local candidate list",
        "symbols": symbols,
        "news": news,
        "benchmark": benchmark,
        "stocks": stocks,
        "coverage": {
            "stocks": len(symbols),
            "news_symbols": len({r["symbol"] for r in news["items"]}),
            "histories": sum(s["history"].get("status") == "available" for s in stocks),
            "analysts": sum(s["analysts"].get("status") in {"available", "partial"} for s in stocks),
        },
    }


if __name__ == "__main__":
    import argparse
    import contextlib
    import io
    import sys

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dashboard-url", default="http://127.0.0.1:8050")
    args = parser.parse_args()
    data = json.loads(sys.stdin.read(2_000_001))
    # Keep incidental provider output out of the structured IPC response.
    with contextlib.redirect_stdout(io.StringIO()):
        evidence = build_evidence(data, args.dashboard_url)
    print(json.dumps(evidence, allow_nan=False))
