from __future__ import annotations

from datetime import date, timedelta
import time
import unittest
from unittest.mock import patch

import app


class PriceHistoryLookupTest(unittest.TestCase):
    def test_previous_price_uses_latest_available_price_before_target(self) -> None:
        prices = {
            "2024-01-02": 10.0,
            "2024-01-05": 12.5,
        }

        self.assertEqual(app.previous_price(prices, date(2024, 1, 4)), 10.0)
        self.assertEqual(app.previous_price(prices, date(2024, 1, 5)), 12.5)
        self.assertIsNone(app.previous_price(prices, date(2024, 1, 1)))
        self.assertEqual(app.previous_price_point(prices, date(2024, 1, 4)), (10.0, date(2024, 1, 2)))

    def test_fetch_history_reuses_covering_cached_range(self) -> None:
        payload = {
            "symbol": "ABC",
            "status": "priced",
            "fetched_at": int(time.time()),
            "prices": {"2024-06-03": 42.0},
        }
        class FakeStore:
            def get_cached(self, *args):
                return payload

            def get_covered(self, *args):
                return payload

        with patch.object(app, "get_history_store", return_value=FakeStore()), patch.object(app, "yf", object()):
            result = app.fetch_history("ABC", date(2024, 6, 1), date(2024, 6, 30))

        self.assertIs(result, payload)

    def test_fetch_history_fills_a_missing_cached_range(self) -> None:
        partial = {
            "symbol": "ABC",
            "currency": "EUR",
            "status": "priced",
            "fetched_at": 1,
            "prices": {"2026-07-16": 42.0},
        }

        class FakeStore:
            merged = None

            def get_cached(self, *args):
                return partial

            def get_covered(self, *args):
                return None

            def has_start_coverage(self, *args):
                return False

            def merge(self, _symbol, payload, _start, _end):
                self.merged = payload
                return payload

            def replace_prices(self, *_args):
                raise AssertionError("no split rewrite expected")

        store = FakeStore()
        chart = {
            "symbol": "ABC",
            "currency": "EUR",
            "prices": {"2024-06-03": 40.0, "2026-07-16": 42.0},
            "splits": {},
        }
        with patch.object(app, "get_history_store", return_value=store), patch.object(
            app, "fetch_yahoo_chart", return_value=chart
        ):
            result = app.fetch_history("ABC", date(2024, 6, 1), date(2026, 8, 30))

        self.assertEqual(result["prices"]["2024-06-03"], 40.0)
        self.assertIsNotNone(store.merged)

    def test_stale_latest_price_is_refreshed_with_actual_market_date(self) -> None:
        cache = {
            "ABC": {
                "symbol": "ABC",
                "currency": "EUR",
                "price": 40.0,
                "price_date": "2026-08-27",
                "status": "priced",
                "fetched_at": 1,
            }
        }
        chart = {
            "symbol": "ABC",
            "currency": "EUR",
            "prices": {"2026-09-11": 49.0, "2026-09-14": 50.0},
            "splits": {},
        }
        with (
            patch.object(app, "get_price_cache", return_value=cache),
            patch.object(app, "fetch_yahoo_chart", return_value=chart),
            patch.object(app, "save_json"),
        ):
            result = app.fetch_price("ABC")

        self.assertEqual(result["price"], 50.0)
        self.assertEqual(result["price_date"], "2026-09-14")
        self.assertEqual(result["source"], "yahoo_chart")

    def test_forced_quote_refresh_reuses_history_and_skips_other_assets(self) -> None:
        cache = {
            "ABC": {
                "symbol": "ABC",
                "currency": "EUR",
                "price": 40.0,
                "price_date": "2026-09-15",
                "status": "priced",
                "fetched_at": int(time.time()),
            }
        }
        chart = {
            "symbol": "ABC",
            "currency": "EUR",
            "prices": {"2026-09-16": 50.0},
            "splits": {},
        }
        with (
            patch.object(app, "get_price_cache", return_value=cache),
            patch.object(app, "fetch_yahoo_chart", return_value=chart) as fetch,
            patch.object(app, "get_history_store") as history_store,
            patch.object(app, "save_json"),
        ):
            app.refresh_price_cache({"ABC"}, force=True)

        fetch.assert_called_once_with("ABC", range_period="1mo")
        history_store.return_value.merge.assert_called_once()
        self.assertEqual(cache["ABC"]["price"], 50.0)
        self.assertEqual(cache["ABC"]["price_date"], "2026-09-16")

    def test_failed_refresh_does_not_relabel_old_history_as_fresh(self) -> None:
        fallback = {
            "symbol": "ABC",
            "currency": "EUR",
            "price": 40.0,
            "price_date": "2026-08-27",
            "status": "priced",
            "fetched_at": 123,
            "source": "history_cache",
        }
        with (
            patch.object(app, "get_price_cache", return_value={}),
            patch.object(app, "fetch_yahoo_chart", side_effect=TimeoutError("timed out")),
            patch.object(app, "latest_cached_history_price", return_value=fallback),
        ):
            result = app.fetch_price("ABC", refresh=True)

        self.assertEqual(result["fetched_at"], 123)
        self.assertEqual(result["price_date"], "2026-08-27")
        self.assertTrue(result["cache_stale"])
        self.assertEqual(result["refresh_error"], "timed out")

    def test_refresh_keeps_resolved_symbol_when_lookup_fails(self) -> None:
        cached = {
            "US0079031078": {
                "isin": "US0079031078",
                "symbol": "AMD",
                "status": "resolved",
                "resolved_at": 1,
            }
        }

        class FailingYFinance:
            @staticmethod
            def Search(*_args, **_kwargs):
                raise RuntimeError("temporary lookup failure")

        with (
            patch.object(app, "get_symbol_cache", return_value=cached),
            patch.object(app, "save_json") as save,
            patch.object(app, "yf", FailingYFinance()),
        ):
            result = app.resolve_isin("US0079031078", refresh=True)

        self.assertEqual(result["symbol"], "AMD")
        self.assertEqual(result["status"], "resolved")
        self.assertTrue(result["cache_stale"])
        self.assertEqual(result["refresh_error"], "temporary lookup failure")
        self.assertEqual(cached["US0079031078"]["symbol"], "AMD")
        save.assert_not_called()

    def test_failed_lookup_retries_after_cooldown(self) -> None:
        cached = {"IE00BL25JL35": {"status": "lookup_error", "resolved_at": 1000}}
        result = type("SearchResult", (), {"quotes": [{"symbol": "XDEQ.MI"}]})()
        with (
            patch.object(app, "get_symbol_cache", return_value=cached),
            patch.object(app, "save_json"),
            patch.object(app.time, "time", return_value=1900),
            patch.object(app.yf, "Search", return_value=result) as search,
        ):
            resolved = app.resolve_isin("IE00BL25JL35")
        search.assert_called_once()
        self.assertEqual(resolved["symbol"], "XDEQ.MI")
        self.assertEqual(resolved["status"], "resolved")

    def test_failed_lookup_respects_cooldown(self) -> None:
        cached = {"IE00BL25JL35": {"status": "lookup_error", "resolved_at": 1000}}
        with (
            patch.object(app, "get_symbol_cache", return_value=cached),
            patch.object(app.time, "time", return_value=1899),
            patch.object(app.yf, "Search") as search,
        ):
            self.assertEqual(app.resolve_isin("IE00BL25JL35")["status"], "lookup_error")
        search.assert_not_called()

    def test_missing_yfinance_reuses_resolved_symbol(self) -> None:
        cached = {
            "US0079031078": {
                "isin": "US0079031078",
                "symbol": "AMD",
                "status": "resolved",
            }
        }

        with patch.object(app, "get_symbol_cache", return_value=cached), patch.object(app, "yf", None):
            result = app.resolve_isin("US0079031078", refresh=True)

        self.assertEqual(result["symbol"], "AMD")
        self.assertEqual(result["status"], "resolved")
        self.assertTrue(result["cache_stale"])

    def test_london_tickers_keep_pence_currency_fallback(self) -> None:
        self.assertEqual(app.infer_currency("IWQU.L"), "GBp")
        self.assertEqual(app.normalize_currency_code("GBp"), "GBp")
        self.assertEqual(app.fx_base_currency("GBp"), "GBP")

    def test_variations_include_msci_comparison(self) -> None:
        series = [
            {"date": "2026-05-18", "market_value": 100.0, "profit": 0.0, "msci_return_pct": 0.0},
            {"date": "2026-06-10", "market_value": 110.0, "profit": 10.0, "msci_return_pct": 4.0},
            {"date": "2026-06-17", "market_value": 120.0, "profit": 20.0, "msci_return_pct": 7.0},
        ]

        variations = app.calculate_variations(series)

        self.assertEqual(variations["1w"]["msci_pct"], 2.88)
        self.assertEqual(variations["1w"]["vs_msci_pct"], 6.21)

    def test_variations_do_not_report_stale_msci_as_zero(self) -> None:
        series = [
            {
                "date": "2026-06-17",
                "market_value": 100.0,
                "profit": 10.0,
                "msci_return_pct": 5.0,
                "msci_price_date": "2026-06-16",
            },
            {
                "date": "2026-06-18",
                "market_value": 101.0,
                "profit": 11.0,
                "msci_return_pct": 5.0,
                "msci_price_date": "2026-06-16",
            },
        ]

        variations = app.calculate_variations(series)

        self.assertEqual(variations["1d"]["pct"], 1.0)
        self.assertIsNone(variations["1d"]["msci_pct"])
        self.assertIsNone(variations["1d"]["vs_msci_pct"])

    def test_build_instrument_refs_prefers_mapping_symbol(self) -> None:
        trade = app.Trade(
            asset="FTSE All-World USD (Acc)",
            isin="IE00BK5BQT80",
            broker="Trade Republic",
            action="BUY",
            currency_hint="EUR",
            cash_currency="EUR",
            date=date(2026, 1, 2),
            price=app.Decimal("100"),
            quantity=app.Decimal("1"),
            quantity_diff=app.Decimal("1"),
            total_spend=app.Decimal("100"),
            fees=app.ZERO,
            tax=app.ZERO,
            grand_total=app.Decimal("100"),
            grand_total_present=True,
            source="test",
        )

        with patch.object(app, "resolve_isin", wraps=app.resolve_isin) as resolve_isin:
            refs = app.build_instrument_refs(
                [trade],
                {"FTSE All-World USD (Acc)": {"isin": "IE00BK5BQT80", "ticker": "VWCE.DE", "exchange": ""}},
            )

        self.assertEqual(refs["IE00BK5BQT80"]["symbol"], "VWCE.DE")
        resolve_isin.assert_called_once_with("IE00BK5BQT80", refresh=False, direct_symbol="VWCE.DE")

    def test_statistics_are_available_for_family_users(self) -> None:
        start = date(2020, 1, 2)
        end = date.today()
        trades = [
            app.Trade(
                asset="Test Asset",
                isin="TEST",
                broker="Mediolanum",
                action="BUY",
                currency_hint="EUR",
                cash_currency="EUR",
                date=start,
                price=app.Decimal("100"),
                quantity=app.Decimal("10"),
                quantity_diff=app.Decimal("10"),
                total_spend=app.Decimal("1000"),
                fees=app.ZERO,
                tax=app.ZERO,
                grand_total=app.Decimal("1000"),
                grand_total_present=True,
                source="test",
            )
        ]
        prices = {start.isoformat(): 100.0, end.isoformat(): 110.0}
        history_context = {
            "histories": {"TEST.MI": {"status": "priced", "currency": "EUR", "prices": prices}},
            "fx_histories": {},
            "msci_prices": prices,
            "xeon_prices": prices,
        }

        with (
            patch.object(app, "build_instrument_refs", return_value={"TEST": {"symbol": "TEST.MI"}}),
            patch.object(app, "load_cash_histories", return_value=([], [], [])),
            patch.object(app, "read_portfolio_dividends", return_value=[]),
            patch.object(app, "read_cash_interests", return_value=[]),
        ):
            stats = app.calculate_portfolio_statistics(trades, {}, person="secondary", history_context=history_context)

        self.assertIsNotNone(stats)
        self.assertIn("price_return", stats)
        self.assertEqual(stats["start_date"], start.isoformat())
        self.assertGreater(stats["days_evaluated"], 0)
        self.assertIn("daily_returns", stats)
        latest_return_date = date.fromisoformat(stats["daily_returns"][-1]["date"])
        self.assertLessEqual(latest_return_date, end)
        self.assertGreaterEqual(latest_return_date, end - timedelta(days=3))
        self.assertTrue(any(row["price_return"] is not None for row in stats["daily_returns"]))

    def test_rankings_ytd_is_time_weighted_from_the_31_december_close(self) -> None:
        # Month-end history: +10% in H2 last year, +10% in January, 1000 added on
        # 1 February (no market move), +10% to June. YTD starts at the 31 December
        # close, so January counts, and the February deposit is not a gain.
        current_year = app.datetime.now().year

        def point(day: str, value: float, contributions: float) -> dict[str, float | str]:
            return {
                "date": day,
                "market_value": value,
                "net_contributions": contributions,
                "profit": value - contributions,
                "total_market_value": value,
                "total_net_contributions": contributions,
                "total_profit": value - contributions,
                "priced_positions": 1,
                "unpriced_positions": 0,
            }

        series = [
            point(f"{current_year - 1}-06-30", 1000.0, 1000.0),
            point(f"{current_year - 1}-12-31", 1100.0, 1000.0),
            point(f"{current_year}-01-31", 1210.0, 1000.0),
            point(f"{current_year}-02-01", 2210.0, 2000.0),
            point(f"{current_year}-06-20", 2431.0, 2000.0),
        ]

        def fake_payload(*args, **kwargs):
            return {"valuation_series": series}

        with patch.object(app, "read_dashboard_cache", side_effect=fake_payload):
            response = app.app.test_client().get("/api/rankings")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["ytd_start_date"], f"{current_year - 1}-12-31")
        primary = next(row for row in response.get_json()["rankings"] if row["person"] == app.PRIMARY_PORTFOLIO_ID)
        self.assertEqual(primary["returns"]["price"]["ytd"], 21.0)
        self.assertEqual(primary["returns"]["total"]["ytd"], 21.0)
        self.assertEqual(primary["returns"]["price"]["start"], 33.1)
        # The old anchor (first point on or after 1 January) skipped January.
        self.assertNotEqual(primary["returns"]["price"]["ytd"], 10.0)

if __name__ == "__main__":
    unittest.main()
