from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from src.portfolio_dashboard.cache import HistoryStore


class HistoryStoreTest(unittest.TestCase):
    def test_merges_ranges_into_one_symbol_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "history"
            store = HistoryStore(directory)
            store.merge(
                "ABC",
                {"symbol": "ABC", "currency": "EUR", "status": "priced", "fetched_at": 100, "prices": {"2024-01-02": 10}},
                date(2024, 1, 1),
                date(2024, 1, 31),
            )
            store.merge(
                "ABC",
                {"symbol": "ABC", "currency": "EUR", "status": "priced", "fetched_at": 200, "prices": {"2024-02-01": 11}},
                date(2024, 2, 1),
                date(2024, 2, 29),
            )

            files = list(directory.glob("*.json"))
            cached = store.get_range("ABC", date(2024, 2, 1), date(2024, 2, 29), now=201, ttl_seconds=100)

        self.assertEqual(len(files), 1)
        self.assertEqual(cached["prices"], {"2024-01-02": 10.0, "2024-02-01": 11.0})

    def test_migrates_legacy_overlapping_ranges_once(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            legacy = root / "history.json"
            legacy.write_text(
                json.dumps(
                    {
                        "ABC|2024-01-01|2024-01-31": {
                            "symbol": "ABC",
                            "currency": "EUR",
                            "status": "priced",
                            "fetched_at": 100,
                            "prices": {"2024-01-02": 10},
                        },
                        "ABC|2024-01-01|2024-02-29": {
                            "symbol": "ABC",
                            "currency": "EUR",
                            "status": "priced",
                            "fetched_at": 200,
                            "prices": {"2024-01-02": 10.5, "2024-02-01": 11},
                        },
                    }
                ),
                encoding="utf-8",
            )
            store = HistoryStore(root / "history", legacy_file=legacy)
            cached = store.get_range("ABC", date(2024, 1, 1), date(2024, 2, 29), now=201, ttl_seconds=100)

            archive = root / "legacy" / "history-monolithic-v1.json"
            archive_exists = archive.exists()
            legacy_exists = legacy.exists()

        self.assertEqual(cached["prices"]["2024-01-02"], 10.5)
        self.assertTrue(archive_exists)
        self.assertFalse(legacy_exists)

    def test_get_cached_returns_stale_or_partially_covered_history(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = HistoryStore(Path(temporary) / "history")
            store.merge(
                "ABC",
                {
                    "symbol": "ABC",
                    "currency": "EUR",
                    "status": "priced",
                    "fetched_at": 100,
                    "prices": {"2024-01-02": 10},
                },
                date(2024, 1, 1),
                date(2024, 1, 31),
            )

            cached = store.get_cached("ABC", date(2024, 1, 1), date(2024, 2, 1))

        self.assertEqual(cached["prices"], {"2024-01-02": 10.0})
        self.assertTrue(cached["cache_stale"])

    def test_get_covered_rejects_a_partial_range(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = HistoryStore(Path(temporary) / "history")
            store.merge(
                "ABC",
                {
                    "symbol": "ABC",
                    "currency": "EUR",
                    "status": "priced",
                    "fetched_at": 100,
                    "prices": {"2026-07-16": 10},
                },
                date(2026, 7, 16),
                date(2026, 8, 30),
            )

            partial = store.get_covered("ABC", date(2024, 1, 1), date(2026, 8, 30))
            covered = store.get_covered("ABC", date(2026, 7, 16), date(2026, 8, 30))

        self.assertIsNone(partial)
        self.assertEqual(covered["prices"], {"2026-07-16": 10.0})
        self.assertTrue(covered["cache_stale"])

    def test_latest_price_preserves_the_real_fetch_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = HistoryStore(Path(temporary) / "history")
            store.merge(
                "ABC",
                {
                    "symbol": "ABC",
                    "currency": "EUR",
                    "status": "priced",
                    "fetched_at": 123,
                    "prices": {"2026-08-27": 40},
                },
                date(2026, 8, 1),
                date(2026, 8, 27),
            )

            latest = store.latest_price("ABC")

        self.assertEqual(latest["price_date"], "2026-08-27")
        self.assertEqual(latest["fetched_at"], 123)

    def test_start_coverage_survives_a_recent_incremental_merge(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = HistoryStore(Path(temporary) / "history")
            store.merge(
                "ABC",
                {"symbol": "ABC", "currency": "EUR", "status": "priced", "fetched_at": 1, "prices": {"2024-01-02": 10}},
                date(2024, 1, 1),
                date(2026, 8, 27),
            )
            store.merge(
                "ABC",
                {"symbol": "ABC", "currency": "EUR", "status": "priced", "fetched_at": 2, "prices": {"2026-09-15": 11}},
                date(2026, 9, 1),
                date(2026, 9, 15),
            )

            self.assertTrue(store.has_start_coverage("ABC", date(2024, 1, 1)))
            self.assertFalse(store.has_start_coverage("ABC", date(2023, 1, 1)))


if __name__ == "__main__":
    unittest.main()
