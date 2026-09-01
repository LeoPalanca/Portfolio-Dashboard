from __future__ import annotations

import tempfile
import unittest
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import app
from src.portfolio_dashboard.cache import HistoryStore


class FakeSplits(dict):
    """Minimal stand-in for the pandas Series yfinance exposes as ``Ticker.splits``."""


def splits(entries: dict[str, float]) -> FakeSplits:
    return FakeSplits({datetime.fromisoformat(day): ratio for day, ratio in entries.items()})


class SplitAdjustedPricesTest(unittest.TestCase):
    def test_back_adjusts_closes_the_provider_has_not_rebased(self) -> None:
        prices = {"2026-08-06": 94.0, "2026-08-07": 90.0, "2026-08-11": 45.5, "2026-08-12": 46.0}
        adjusted = app.split_adjusted_prices(prices, splits({"2026-08-11": 2.0}))
        self.assertAlmostEqual(adjusted["2026-08-06"], 47.0)
        self.assertAlmostEqual(adjusted["2026-08-07"], 45.0)
        self.assertAlmostEqual(adjusted["2026-08-11"], 45.5)

    def test_is_idempotent_once_the_series_is_adjusted(self) -> None:
        prices = {"2026-08-06": 94.0, "2026-08-07": 90.0, "2026-08-11": 45.5, "2026-08-12": 46.0}
        split_events = splits({"2026-08-11": 2.0})
        once = app.split_adjusted_prices(prices, split_events)
        twice = app.split_adjusted_prices(once, split_events)
        self.assertEqual(once, twice)

    def test_repairs_mixed_double_adjusted_cache_blocks(self) -> None:
        prices = {
            "2026-07-30": 48.82,
            "2026-07-31": 24.09,
            "2026-08-03": 46.77,
            "2026-08-05": 47.23,
            "2026-08-06": 23.54,
            "2026-08-07": 45.18,
            "2026-08-11": 45.53,
        }
        split_events = splits({"2026-08-11": 2.0})

        adjusted = app.split_adjusted_prices(prices, split_events)

        self.assertAlmostEqual(adjusted["2026-07-31"], 48.18)
        self.assertAlmostEqual(adjusted["2026-08-06"], 47.08)
        self.assertEqual(app.split_adjusted_prices(adjusted, split_events), adjusted)

    def test_leaves_history_alone_when_the_gap_does_not_match_the_ratio(self) -> None:
        prices = {"2026-08-06": 94.0, "2026-08-07": 90.0, "2026-08-11": 88.0, "2026-08-12": 89.0}
        adjusted = app.split_adjusted_prices(prices, splits({"2026-08-11": 2.0}))
        self.assertEqual(adjusted, prices)

    def test_splits_outside_the_series_are_ignored(self) -> None:
        prices = {"2026-08-11": 45.5, "2026-08-12": 46.0}
        adjusted = app.split_adjusted_prices(prices, splits({"2023-03-28": 2.0}))
        self.assertEqual(adjusted, prices)


class HistoryStoreReplacePricesTest(unittest.TestCase):
    def test_replace_prices_rewrites_the_stored_series(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            store = HistoryStore(Path(folder))
            store.merge(
                "MNST",
                {
                    "symbol": "MNST",
                    "currency": "USD",
                    "status": "priced",
                    "prices": {"2026-08-06": 94.0, "2026-08-11": 45.5},
                    "fetched_at": 1,
                },
                date(2026, 8, 6),
                date(2026, 8, 11),
            )
            store.replace_prices("MNST", {"2026-08-06": 47.0, "2026-08-11": 45.5})
            store.clear_memory()

            prices = store.get_cached("MNST", date(2026, 8, 6), date(2026, 8, 11))["prices"]
            self.assertAlmostEqual(prices["2026-08-06"], 47.0)

    def test_replace_prices_ignores_symbols_without_a_priced_record(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            store = HistoryStore(Path(folder))
            store.replace_prices("MNST", {"2026-08-06": 47.0})
            self.assertIsNone(store.get_cached("MNST", date(2026, 8, 6), date(2026, 8, 6)))

    def test_cached_history_self_heals_from_known_broker_split(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            store = HistoryStore(Path(folder))
            store.merge(
                "MNST",
                {
                    "symbol": "MNST",
                    "currency": "USD",
                    "status": "priced",
                    "prices": {"2026-08-06": 23.54, "2026-08-07": 45.18, "2026-08-11": 45.53},
                    "fetched_at": 1,
                },
                date(2026, 8, 6),
                date(2026, 8, 11),
            )

            payload = app.apply_history_splits(
                store,
                "MNST",
                store.get_cached("MNST", date(2026, 8, 6), date(2026, 8, 11)),
                {"2026-08-11": 2.0},
            )

            self.assertAlmostEqual(payload["prices"]["2026-08-06"], 47.08)
            store.clear_memory()
            persisted = store.get_cached("MNST", date(2026, 8, 6), date(2026, 8, 11))
            self.assertAlmostEqual(persisted["prices"]["2026-08-06"], 47.08)



def trade(asset: str, action: str, day: str, quantity: str, amount: str, source: str = "fineco") -> app.Trade:
    quantity_value = Decimal(quantity)
    return app.Trade(
        asset=asset,
        isin="",
        broker="Fineco",
        action=action,
        currency_hint="EUR",
        cash_currency="EUR",
        date=date.fromisoformat(day),
        price=(Decimal(amount) / quantity_value) if quantity_value else Decimal(0),
        quantity=abs(quantity_value),
        quantity_diff=quantity_value,
        total_spend=Decimal(amount),
        fees=Decimal(0),
        tax=Decimal(0),
        grand_total=Decimal(amount),
        grand_total_present=True,
        source=source,
    )


class SplitAdjustedTradeHistoryTest(unittest.TestCase):
    def test_earlier_rows_are_restated_and_the_split_row_drops_out(self) -> None:
        history = [
            trade("MONSTER", "Acquisto", "2024-01-23", "1", "-59.27"),
            trade("MONSTER", "Assegnazione", "2026-08-11", "1", "0", source="fineco_corporate_action"),
        ]
        adjusted = app.split_adjusted_trade_history(history)

        self.assertEqual(len(adjusted), 1)
        self.assertEqual(adjusted[0].quantity_diff, Decimal(2))
        self.assertEqual(adjusted[0].grand_total, Decimal("-59.27"))
        self.assertEqual(adjusted[0].price, Decimal("-29.635"))

    def test_only_the_affected_asset_is_restated(self) -> None:
        history = [
            trade("MONSTER", "Acquisto", "2024-01-23", "1", "-59.27"),
            trade("APPLE", "Acquisto", "2024-02-01", "3", "-500"),
            trade("MONSTER", "Assegnazione", "2026-08-11", "1", "0", source="fineco_corporate_action"),
        ]
        adjusted = {item.asset: item for item in app.split_adjusted_trade_history(history)}

        self.assertEqual(adjusted["MONSTER"].quantity_diff, Decimal(2))
        self.assertEqual(adjusted["APPLE"].quantity_diff, Decimal(3))

    def test_a_reverse_split_shrinks_the_earlier_rows(self) -> None:
        history = [
            trade("SOME STOCK", "Acquisto", "2024-01-23", "10", "-100"),
            trade("SOME STOCK", "Rettifica quantita", "2026-08-11", "-5", "0", source="fineco_corporate_action"),
        ]
        adjusted = app.split_adjusted_trade_history(history)

        self.assertEqual(len(adjusted), 1)
        self.assertEqual(adjusted[0].quantity_diff, Decimal(5))

    def test_history_without_corporate_actions_is_returned_unchanged(self) -> None:
        history = [trade("MONSTER", "Acquisto", "2024-01-23", "1", "-59.27")]
        self.assertIs(app.split_adjusted_trade_history(history), history)

    def test_a_split_with_no_prior_position_is_kept_as_booked(self) -> None:
        history = [trade("MONSTER", "Assegnazione", "2026-08-11", "1", "0", source="fineco_corporate_action")]
        adjusted = app.split_adjusted_trade_history(history)

        self.assertEqual(len(adjusted), 1)
        self.assertEqual(adjusted[0].quantity_diff, Decimal(1))

if __name__ == "__main__":
    unittest.main()
