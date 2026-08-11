from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from src.portfolio_dashboard.movements import MovementStore


class MovementStoreTest(unittest.TestCase):
    def test_records_imports_and_deduplicates_movements_across_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = MovementStore(Path(temporary) / "movements.sqlite3")
            movement = {
                "date": date(2026, 1, 2),
                "event_type": "trade",
                "broker": "Example",
                "asset": "Example ETF",
                "isin": "IE0000000001",
                "currency": "EUR",
                "amount": "100",
                "quantity": "2",
            }
            first = store.record_import(
                sha256="a" * 64,
                source_kind="example",
                original_name="one.csv",
                stored_path="broker_exports/example/one.csv",
                parser_version="0.1.0",
                movements=[movement],
            )
            second = store.record_import(
                sha256="b" * 64,
                source_kind="example",
                original_name="two.csv",
                stored_path="broker_exports/example/two.csv",
                parser_version="0.1.0",
                movements=[movement],
            )
            summary = store.summary()

        self.assertEqual(first.movement_count, 1)
        self.assertEqual(second.movement_count, 0)
        self.assertEqual(second.duplicate_count, 1)
        self.assertEqual(summary["imports"], 2)
        self.assertEqual(summary["movements"], 1)

    def test_finds_an_existing_import_by_file_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = MovementStore(Path(temporary) / "movements.sqlite3")
            created = store.record_import(
                sha256="c" * 64,
                source_kind="example",
                original_name="statement.csv",
                stored_path="cash_exports/example/statement.csv",
                parser_version="0.1.0",
                movements=[],
            )
            found = store.import_by_hash("c" * 64)

        self.assertEqual(found, created)


if __name__ == "__main__":
    unittest.main()
