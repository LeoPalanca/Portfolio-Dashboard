from __future__ import annotations

import tempfile
import unittest
from datetime import date, datetime
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


if __name__ == "__main__":
    unittest.main()
