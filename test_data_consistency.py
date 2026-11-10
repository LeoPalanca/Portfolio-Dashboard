"""Regression checks for benchmark dating, crypto history and per-broker cash flows."""

from __future__ import annotations

import unittest
from datetime import date, timedelta
from decimal import Decimal

import app


def trade(broker: str, day: str, quantity: str, amount: str) -> app.Trade:
    quantity_value = Decimal(quantity)
    return app.Trade(
        asset="ACME",
        isin="",
        broker=broker,
        action="buy" if quantity_value > 0 else "sell",
        currency_hint="EUR",
        cash_currency="EUR",
        date=date.fromisoformat(day),
        price=Decimal(amount) / abs(quantity_value),
        quantity=abs(quantity_value),
        quantity_diff=quantity_value,
        total_spend=Decimal(amount),
        fees=Decimal(0),
        tax=Decimal(0),
        grand_total=Decimal(amount),
        grand_total_present=True,
        source="test",
    )


class BenchmarkDatingTest(unittest.TestCase):
    def test_a_live_quote_keeps_its_own_market_date(self) -> None:
        today = date.today()
        friday = today - timedelta(days=2)
        live = {"status": "priced", "price": 101.0, "price_date": friday.isoformat(), "source": "yahoo_chart"}
        self.assertEqual(app.price_point_for_date({}, today, live), (101.0, friday))

    def test_closed_market_has_no_benchmark_move(self) -> None:
        # Two points carrying the same close must not report a 0.00% MSCI day.
        latest = {"msci_return_pct": 10.0, "msci_price_date": "2026-11-06"}
        past = {"msci_return_pct": 10.0, "msci_price_date": "2026-11-06"}
        self.assertIsNone(app.benchmark_delta(latest, past, "msci"))

    def test_previous_business_day_skips_the_weekend(self) -> None:
        self.assertEqual(app.previous_business_day(date(2026, 11, 9)), date(2026, 11, 6))
        self.assertEqual(app.previous_business_day(date(2026, 11, 10)), date(2026, 11, 9))


class CryptoHistoryMergeTest(unittest.TestCase):
    def test_wallet_values_are_carried_into_the_history(self) -> None:
        base = {"date": "2026-11-10", "market_value": 100.0, "net_contributions": 80.0, "profit": 20.0,
                "total_market_value": 110.0, "total_net_contributions": 80.0, "total_profit": 30.0,
                "priced_positions": 2, "unpriced_positions": 0, "equity_market_value": 100.0}
        wallet = {"date": "2026-11-08", "market_value": 50.0, "net_contributions": 40.0, "profit": 10.0,
                  "total_market_value": 50.0, "total_net_contributions": 40.0, "total_profit": 10.0,
                  "priced_positions": 1, "unpriced_positions": 0}
        merged = app.merge_crypto_wallet_series({"series": [base]}, {"series": [wallet]})["series"][0]
        self.assertEqual(merged["market_value"], 150.0)
        self.assertEqual(merged["profit"], 30.0)
        self.assertEqual(merged["return_pct"], 25.0)
        self.assertEqual(merged["equity_market_value"], 100.0)
        self.assertEqual(merged["priced_positions"], 3)


class BrokerCashFlowTest(unittest.TestCase):
    def test_flows_are_split_by_broker_and_day(self) -> None:
        summary = app.summarize_net_contributions([
            trade("Fineco", "2026-01-02", "2", "200"),
            trade("Fineco", "2026-01-02", "-1", "120"),
            trade("Trade Republic", "2026-02-03", "1", "50"),
        ])
        self.assertEqual(summary["by_broker_date"], [
            {"date": "2026-01-02", "broker": "Fineco", "buys_eur": 200.0, "sells_eur": 120.0},
            {"date": "2026-02-03", "broker": "Trade Republic", "buys_eur": 50.0, "sells_eur": 0.0},
        ])


if __name__ == "__main__":
    unittest.main()
