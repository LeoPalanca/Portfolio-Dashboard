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

        with patch.object(app, "get_history_store", return_value=FakeStore()), patch.object(app, "yf", object()):
            result = app.fetch_history("ABC", date(2024, 6, 1), date(2024, 6, 30))

        self.assertIs(result, payload)

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

    def test_rankings_ytd_uses_period_return_formula(self) -> None:
        current_year = app.datetime.now().year
        series = [
            {
                "date": f"{current_year - 1}-01-01",
                "market_value": 1000.0,
                "profit": 0.0,
                "net_contributions": 1000.0,
                "return_pct": 0.0,
                "total_market_value": 1000.0,
                "total_profit": 0.0,
                "total_net_contributions": 1000.0,
                "total_return_pct": 0.0,
            },
            {
                "date": f"{current_year}-01-02",
                "market_value": 5007.68,
                "profit": 1408.34,
                "net_contributions": 3599.34,
                "return_pct": 39.13,
                "total_market_value": 5266.44,
                "total_profit": 1945.57,
                "total_net_contributions": 3320.86,
                "total_return_pct": 58.59,
            },
            {
                "date": f"{current_year}-06-20",
                "market_value": 5193.09,
                "profit": 2161.13,
                "net_contributions": 3031.97,
                "return_pct": 71.28,
                "total_market_value": 6108.78,
                "total_profit": 2733.82,
                "total_net_contributions": 3374.96,
                "total_return_pct": 81.0,
            },
        ]

        def fake_payload(*args, **kwargs):
            return {"valuation_series": series}

        with patch.object(app, "dashboard_payload", side_effect=fake_payload):
            response = app.app.test_client().get("/api/rankings")

        self.assertEqual(response.status_code, 200)
        primary = next(row for row in response.get_json()["rankings"] if row["person"] == app.PRIMARY_PORTFOLIO_ID)
        self.assertEqual(primary["returns"]["price"]["ytd"], 15.03)
        self.assertEqual(primary["returns"]["total"]["ytd"], 14.82)
        self.assertNotEqual(primary["returns"]["price"]["ytd"], 23.11)


if __name__ == "__main__":
    unittest.main()
