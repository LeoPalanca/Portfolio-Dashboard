from __future__ import annotations

import tempfile
import unittest
import sqlite3
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

    def test_scopes_file_and_movement_deduplication_by_portfolio(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = MovementStore(Path(temporary) / "movements.sqlite3")
            movement = {"date": date(2026, 1, 2), "event_type": "trade", "asset": "ETF", "quantity": "1"}
            primary = store.record_import(
                sha256="d" * 64,
                source_kind="manual",
                original_name="trades.csv",
                stored_path="trades.csv",
                parser_version="0.4.0",
                movements=[movement],
                portfolio_id="primary",
            )
            partner = store.record_import(
                sha256="d" * 64,
                source_kind="manual",
                original_name="trades.csv",
                stored_path="trades.csv",
                parser_version="0.4.0",
                movements=[movement],
                portfolio_id="partner",
            )

            primary_rows = store.movements("primary")
            partner_rows = store.movements("partner")

        self.assertEqual(primary.movement_count, 1)
        self.assertEqual(partner.movement_count, 1)
        self.assertEqual(len(primary_rows), 1)
        self.assertEqual(len(partner_rows), 1)

    def test_migrates_v1_database_to_configured_primary_portfolio(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "movements.sqlite3"
            connection = sqlite3.connect(database)
            connection.executescript(
                """
                CREATE TABLE imports (
                    id INTEGER PRIMARY KEY, sha256 TEXT NOT NULL UNIQUE, source_kind TEXT NOT NULL,
                    original_name TEXT NOT NULL, stored_path TEXT NOT NULL, parser_version TEXT NOT NULL,
                    imported_at TEXT NOT NULL, movement_count INTEGER NOT NULL, duplicate_count INTEGER NOT NULL
                );
                CREATE TABLE movements (
                    id INTEGER PRIMARY KEY, fingerprint TEXT NOT NULL UNIQUE,
                    import_id INTEGER NOT NULL REFERENCES imports(id), occurred_on TEXT NOT NULL,
                    event_type TEXT NOT NULL, source_kind TEXT NOT NULL, account TEXT NOT NULL DEFAULT '',
                    asset TEXT NOT NULL DEFAULT '', isin TEXT NOT NULL DEFAULT '', description TEXT NOT NULL DEFAULT '',
                    currency TEXT NOT NULL DEFAULT '', amount TEXT NOT NULL DEFAULT '', quantity TEXT NOT NULL DEFAULT '',
                    price TEXT NOT NULL DEFAULT '', fees TEXT NOT NULL DEFAULT '', tax TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );
                INSERT INTO imports VALUES (1, 'hash', 'manual', 'old.csv', 'old.csv', '0.3.0', '2026-01-01', 1, 0);
                INSERT INTO movements VALUES (1, 'fingerprint', 1, '2026-01-02', 'trade', 'manual',
                    'Personal', 'ETF', '', 'BUY', 'EUR', '100', '1', '100', '0', '0', '{}');
                """
            )
            connection.commit()
            connection.close()

            store = MovementStore(database, default_portfolio_id="owner")
            rows = store.movements("owner")
            imported = store.import_by_hash("hash", "owner")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["portfolio_id"], "owner")
        self.assertIsNotNone(imported)


if __name__ == "__main__":
    unittest.main()
