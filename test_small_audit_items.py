"""Risk statistics without fake crashes, fetcher paths, and a lighter startup."""

from __future__ import annotations

import subprocess
import sys
import unittest
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

import app
import crypto_wallet_fetcher


def trade(asset: str, day: date, quantity: str, amount: str) -> app.Trade:
    return app.Trade(
        asset=asset, isin="", broker="Example", action="Acquisto", currency_hint="EUR", cash_currency="EUR",
        date=day, price=Decimal(amount) / Decimal(quantity), quantity=Decimal(quantity), quantity_diff=Decimal(quantity),
        total_spend=-Decimal(amount), fees=Decimal(0), tax=Decimal(0), grand_total=-Decimal(amount),
        grand_total_present=True, source="test",
    )


def business_days(start: date, count: int) -> list[date]:
    days: list[date] = []
    day = start
    while len(days) < count:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days


class RiskStatisticsTest(unittest.TestCase):
    def test_a_position_without_a_quote_yet_is_not_a_crash(self) -> None:
        days = business_days(date.today() - timedelta(days=20), 10)  # noqa: DTZ011 - statistics run up to today
        flat = {day.isoformat(): 100.0 for day in days}
        late = {day.isoformat(): 100.0 for day in days[5:]}
        context = {
            "histories": {
                "AAA": {"status": "priced", "currency": "EUR", "prices": flat},
                # Bought on day 2, first quote on day 5.
                "BBB": {"status": "priced", "currency": "EUR", "prices": late},
            },
            "msci_prices": flat, "msci_symbol": "MSCI", "xeon_prices": flat,
        }
        refs = {"AAA": {"symbol": "AAA"}, "BBB": {"symbol": "BBB"}}
        trades = [trade("AAA", days[0], "10", "1000"), trade("BBB", days[2], "10", "1000")]
        with (
            patch.object(app, "load_cash_histories", return_value=([], [], [])),
            patch.object(app, "read_portfolio_dividends", return_value=[]),
            patch.object(app, "read_cash_interests", return_value=[]),
            patch.object(app, "build_instrument_refs", return_value=refs),
            patch.object(app, "fetch_history", return_value={"status": "history_error", "prices": {}}),
        ):
            stats = app.calculate_portfolio_statistics(trades, {}, history_context=context)
        returns = [row["price_return"] for row in stats["daily_returns"] if row["price_return"] is not None]
        self.assertTrue(all(abs(value) < 1e-9 for value in returns), returns)

    def test_unit_values_need_a_quote_and_an_exchange_rate(self) -> None:
        day = date(2026, 1, 5)
        histories = {
            "EUR1": {"status": "priced", "currency": "EUR", "prices": {"2026-01-05": 10.0}},
            "USD1": {"status": "priced", "currency": "USD", "prices": {"2026-01-05": 10.0}},
            "GBX1": {"status": "priced", "currency": "GBp", "prices": {"2026-01-05": 500.0}},
        }
        refs = {name: {"symbol": name} for name in histories}
        fx = {"GBPEUR=X": {"prices": {"2026-01-05": 1.2}}}

        def value(asset: str, fx_histories: dict) -> Decimal | None:
            return app.statistics_unit_value_eur(asset, day, refs, histories, fx_histories, {}, {})

        self.assertEqual(value("EUR1", {}), Decimal(10))
        self.assertIsNone(value("USD1", {}), "USD must not be added as EUR without a rate")
        self.assertEqual(value("USD1", {"EURUSD=X": {"prices": {"2026-01-05": 1.25}}}), Decimal(8))
        self.assertEqual(value("GBX1", fx), Decimal("6.0"))
        self.assertIsNone(value("missing", {}))

    def test_running_totals_follow_the_days(self) -> None:
        totals = app.RunningTotals([(date(2026, 1, 3), Decimal(5), Decimal(1)), (date(2026, 1, 1), Decimal(2), Decimal(0))])
        self.assertEqual(totals.through(date(2025, 12, 31)), (Decimal(0), Decimal(0)))
        self.assertEqual(totals.through(date(2026, 1, 2)), (Decimal(2), Decimal(0)))
        self.assertEqual(totals.through(date(2026, 1, 5)), (Decimal(7), Decimal(1)))


class FetcherPathTest(unittest.TestCase):
    def test_wallet_tool_writes_where_the_dashboard_reads(self) -> None:
        self.assertEqual(crypto_wallet_fetcher.POSITIONS_CSV, app.CRYPTO_WALLET_POSITIONS_CSV)
        self.assertEqual(crypto_wallet_fetcher.TRANSACTIONS_CSV, app.CRYPTO_WALLET_TRANSACTIONS_CSV)
        self.assertEqual(crypto_wallet_fetcher.CONFIG_CSV, app.CRYPTO_WALLETS_CSV)


class StartupTest(unittest.TestCase):
    def test_importing_the_app_does_not_load_yfinance(self) -> None:
        loaded = subprocess.run(
            [sys.executable, "-c", "import sys, app; print('yfinance' in sys.modules, 'pandas' in sys.modules)"],
            capture_output=True, text=True, check=True,
        ).stdout.split()
        self.assertEqual(loaded, ["False", "False"])


if __name__ == "__main__":
    unittest.main()
