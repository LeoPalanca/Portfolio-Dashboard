"""Fewer bytes to the browser: trimmed dashboard responses, compressed and cached assets."""

from __future__ import annotations

import gzip
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import app
from src.portfolio_dashboard.web_delivery import SlimResponseCache, distribution_details, slim_dashboard_response

STATIC_JS = Path(app.app.static_folder or "static") / "app.js"


def snapshot() -> dict:
    return {
        "generated_at": "2026-01-01T00:00:00",
        "expenses": {"status": "available", "message": "", "rows": [{"date": "2026-01-01", "amount_eur": 1.0}], "by_month": [1]},
        "distribution": {
            "source_rows": [
                {"source_asset": "ETF", "source_isin": "XX0000000001", "holding_name": "Example", "holding_ticker": "EX",
                 "market_value_eur": 12.3456789, "asset_class": "Equity", "geo": "World", "sector": "Tech", "weight_pct": 1.23456789}
            ],
            "sectors": [{"sector": "Tech", "weight_pct": 33.333333333, "market_value_eur": 1.23456, "holdings": []}],
        },
        "stats": {"daily_returns": [{"date": "2026-01-01", "price_return": 0.0123456789123}]},
        "positions": [{"asset": "ETF", "market_value_eur": 12.3456789}],
    }


class SlimResponseTest(unittest.TestCase):
    def test_only_what_the_page_reads_is_sent(self) -> None:
        full = snapshot()
        slim = slim_dashboard_response(full)
        self.assertEqual(slim["expenses"], {"status": "available", "message": "", "rows": [], "deferred": True})
        self.assertNotIn("source_rows", slim["distribution"])
        self.assertTrue(slim["distribution"]["details_deferred"])
        self.assertEqual(slim["distribution"]["sectors"], [{"sector": "Tech", "weight_pct": 33.333333, "market_value_eur": 1.23, "holdings_count": 0}])
        self.assertEqual(slim["stats"]["daily_returns"][0]["price_return"], 0.012346)
        self.assertEqual(slim["positions"], full["positions"])
        details = distribution_details(full)
        self.assertEqual(
            details["source_rows"],
            [{"source_asset": "ETF", "source_isin": "XX0000000001", "holding_name": "Example", "holding_ticker": "EX",
              "market_value_eur": 12.35, "asset_class": "Equity"}],
        )
        self.assertEqual(details["sector_holdings"], {"Tech": []})
        # The saved snapshot, which exports read, stays complete.
        self.assertEqual(len(full["expenses"]["rows"]), 1)
        self.assertIn("geo", full["distribution"]["source_rows"][0])

    def test_trimmed_form_is_reused_for_the_same_snapshot(self) -> None:
        cache = SlimResponseCache()
        full = snapshot()
        first = cache.get("path", full)
        self.assertIs(cache.get("path", full), first)
        self.assertIsNot(cache.get("path", snapshot()), first)

    def test_portfolio_endpoint_sends_the_trimmed_snapshot(self) -> None:
        full = snapshot()
        with (
            patch.object(app, "read_dashboard_cache", return_value=full),
            patch.object(app, "dashboard_payload", return_value=full),
            patch.object(app, "cash_coverage_disclosure", side_effect=lambda payload, person: payload),
            app.app.test_client() as client,
        ):
            body = client.get("/api/portfolio").get_json()
        self.assertEqual(body["expenses"]["rows"], [])
        self.assertTrue(body["expenses"]["deferred"])
        self.assertNotIn("source_rows", body["distribution"])
        self.assertIn("snapshot", body)

    def test_holdings_are_served_on_request_from_the_same_snapshot(self) -> None:
        with patch.object(app, "read_dashboard_cache", return_value=snapshot()), app.app.test_client() as client:
            details = client.get("/api/portfolio/distribution-details").get_json()
        with patch.object(app, "read_dashboard_cache", return_value=None), app.app.test_client() as client:
            missing = client.get("/api/portfolio/distribution-details")
        self.assertEqual(details["source_rows"][0]["holding_name"], "Example")
        self.assertEqual(missing.status_code, 404)


class AssetDeliveryTest(unittest.TestCase):
    def test_versioned_scripts_are_compressed_and_cached_for_a_year(self) -> None:
        with app.app.test_client() as client:
            compressed = client.get("/static/app.js?v=1", headers={"Accept-Encoding": "gzip"})
            plain = client.get("/static/app.js?v=1")
            unversioned = client.get("/static/app.js", headers={"Accept-Encoding": "gzip"})
        self.assertEqual(compressed.headers["Content-Encoding"], "gzip")
        self.assertIn("immutable", compressed.headers["Cache-Control"])
        self.assertIn("Accept-Encoding", compressed.headers["Vary"])
        self.assertEqual(gzip.decompress(compressed.data), STATIC_JS.read_bytes())
        self.assertLess(len(compressed.data), len(plain.data) / 2)
        self.assertNotIn("Content-Encoding", plain.headers)
        self.assertNotIn("immutable", unversioned.headers.get("Cache-Control", ""))

    def test_the_page_itself_is_compressed(self) -> None:
        with app.app.test_client() as client:
            page = client.get("/", headers={"Accept-Encoding": "gzip"})
        self.assertEqual(page.headers.get("Content-Encoding"), "gzip")
        self.assertIn(b"Portfolio Dashboard v", gzip.decompress(page.data))


class NewsTest(unittest.TestCase):
    def test_feeds_are_fetched_together_and_old_cache_entries_dropped(self) -> None:
        def slow_feed(symbol: str) -> list[dict]:
            time.sleep(0.2)
            return [{"symbol": symbol, "title": f"{symbol} headline", "link": f"https://example.org/{symbol}", "published": symbol}]

        with tempfile.TemporaryDirectory() as temporary:
            stale = {"old|key": {"fetched_at_ts": 0, "payload": {}}}
            with (
                patch.object(app, "NEWS_CACHE", Path(temporary) / "news.json"),
                patch.object(app, "_news_cache_in_memory", stale),
                patch.object(app, "fetch_symbol_news", side_effect=slow_feed),
            ):
                started = time.monotonic()
                result = app.portfolio_news_payload(symbols=["AAA", "BBB", "CCC", "DDD"], refresh=True)
                elapsed = time.monotonic() - started
                cache = app.get_news_cache()
        self.assertLess(elapsed, 0.6)
        self.assertEqual([item["symbol"] for item in result["items"]], ["DDD", "CCC", "BBB", "AAA"])
        self.assertNotIn("old|key", cache)


if __name__ == "__main__":
    unittest.main()
