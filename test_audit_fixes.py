from __future__ import annotations

import gzip
import json
import sqlite3
import tempfile
import threading
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import app
from src.portfolio_dashboard.movements import MovementStore


class LedgerIdentityTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.store = MovementStore(Path(self.temporary.name) / "ledger.sqlite3")
        self.movement = {
            "date": "2026-01-01",
            "event_type": "trade",
            "account": "Test",
            "asset": "ETF",
            "quantity": "1",
            "price": "100",
            "amount": "-100",
        }

    def record(self, token, movements):
        return self.store.record_import(
            sha256=token,
            source_kind="bank",
            original_name=token,
            stored_path=token,
            parser_version="old",
            movements=movements,
        )

    def test_source_ids_keep_distinct_identical_fills_and_reimport_idempotently(self):
        rows = [{**self.movement, "metadata": {"transaction_id": token}} for token in ("A", "B")]
        first = self.record("first", rows)
        second = self.record("second", list(reversed(rows)))
        self.assertEqual(first.movement_count, 2)
        self.assertEqual((second.movement_count, second.duplicate_count), (0, 2))
        self.assertEqual(len(self.store.movements()), 2)

    def test_fallback_preserves_same_file_multiplicity_across_overlapping_files(self):
        self.assertEqual(self.record("first", [self.movement, self.movement]).movement_count, 2)
        self.assertEqual(self.record("second", [self.movement, self.movement]).duplicate_count, 2)
        self.assertEqual(self.record("third", [self.movement]).duplicate_count, 1)
        self.assertEqual(len(self.store.movements()), 2)

    def test_reclassification_updates_one_row_and_preserves_its_id(self):
        old = {"date": "2026-01-01", "event_type": "income", "account": "Test", "description": "Refund", "amount": "10"}
        record = self.record("first", [old])
        identifier = self.store.movements()[0]["id"]
        self.store.enrich_import(record, parser_version="new", movements=[{**old, "event_type": "credit"}])
        rows = self.store.movements()
        self.assertEqual([(row["id"], row["event_type"]) for row in rows], [(identifier, "credit")])
        with sqlite3.connect(self.store.path) as connection:
            previous = json.loads(connection.execute("SELECT previous_json FROM movement_revisions").fetchone()[0])
        self.assertEqual(previous["event_type"], "income")
        self.assertEqual(self.store.import_by_hash("first").movement_count, 1)

    def test_legacy_row_promotes_to_source_id_without_new_movement(self):
        record = self.record("first", [self.movement])
        identifier = self.store.movements()[0]["id"]
        self.store.enrich_import(
            record, parser_version="new", movements=[{**self.movement, "metadata": {"transaction_id": "A"}}]
        )
        self.assertEqual(len(self.store.movements()), 1)
        self.assertEqual(self.store.movements()[0]["id"], identifier)

    def test_source_id_corrected_date_is_reconciled_not_discarded(self):
        movement = {**self.movement, "metadata": {"transaction_id": "A"}}
        record = self.record("first", [movement])
        self.store.enrich_import(record, parser_version="new", movements=[{**movement, "date": "2026-01-02"}])
        self.assertEqual(self.store.movements()[0]["occurred_on"], "2026-01-02")
        self.assertEqual(len(self.store.movements()), 1)

    def test_ambiguous_legacy_identity_rolls_back_instead_of_guessing(self):
        self.record("first", [{**self.movement, "metadata": {"transaction_id": token}} for token in ("A", "B")])
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            self.record("second", [self.movement])
        self.assertEqual(len(self.store.movements()), 2)
        self.assertIsNone(self.store.import_by_hash("second"))


class SnapshotAndRankingsTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for patcher in (
            patch.object(app, "DASHBOARD_CACHE_DIR", self.root),
            patch.object(app, "dashboard_source_signature", return_value="new"),
            patch.object(app, "MOVEMENT_DATABASE", self.root / "ledger.sqlite3"),
            patch.object(app, "_movement_store", None),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        app._DASHBOARD_MEMORY_CACHE.clear()
        app._DASHBOARD_GZIP_CACHE.clear()
        app._PRICE_REFRESH_JOBS.clear()
        self.client = app.app.test_client()
        self.path = app.dashboard_cache_path(app.PRIMARY_PORTFOLIO_ID, "stock", app.DEFAULT_PROXY_MODE, "all", "off")

    def test_cold_http_request_queues_without_building(self):
        with (
            patch.object(app, "queue_dashboard_refresh", return_value={"status": "running"}) as queue,
            patch.object(app, "_build_dashboard_payload") as build,
        ):
            response = self.client.get("/api/portfolio")
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json["status"], "building")
        queue.assert_called_once()
        build.assert_not_called()

    def test_refresh_queue_deduplicates_the_same_selection(self):
        with patch.object(app._DASHBOARD_REFRESH_POOL, "submit") as submit:
            for _ in range(5):
                self.assertEqual(
                    app.queue_dashboard_refresh(self.path, {"person": app.PRIMARY_PORTFOLIO_ID})["status"], "running"
                )
        submit.assert_called_once()

    def test_cold_build_does_not_hold_a_global_lock_over_other_selections(self):
        entered, release, other_done = threading.Event(), threading.Event(), threading.Event()

        def build(**options):
            if options["person"] == "first":
                entered.set()
                release.wait(3)
            else:
                other_done.set()
            return {"generated_at": datetime.now().isoformat()}

        with (
            patch.object(app, "configured_portfolio_id", side_effect=lambda value: value),
            patch.object(app, "_build_dashboard_payload", side_effect=build),
        ):
            first = threading.Thread(target=app.dashboard_payload, kwargs={"person": "first"})
            second = threading.Thread(target=app.dashboard_payload, kwargs={"person": "second"})
            first.start()
            self.assertTrue(entered.wait(1))
            second.start()
            try:
                self.assertTrue(other_done.wait(1), "A different selection was blocked by the first rebuild")
            finally:
                release.set()
                first.join(3)
                second.join(3)

    def test_old_snapshot_remains_visible_without_laundering_its_signature(self):
        old = {"generated_at": (datetime.now() - timedelta(days=1)).isoformat(), "padding": "x" * 10000}
        app.write_dashboard_cache(self.path, "old", old)
        with (
            patch.object(app, "queue_dashboard_refresh", return_value={"status": "running"}),
            patch.object(app, "_build_dashboard_payload") as build,
        ):
            response = self.client.get("/api/portfolio", headers={"Accept-Encoding": "gzip"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(gzip.decompress(response.data))["snapshot"]["status"], "stale")
        self.assertEqual(app._DASHBOARD_MEMORY_CACHE[self.path][0], "old")
        build.assert_not_called()

    def test_partial_rankings_keep_successful_users_and_use_null_for_missing_data(self):
        series = [
            {"date": "2026-01-01", "market_value": 100, "net_contributions": 100, "profit": 0},
            {"date": "2026-02-01", "market_value": 110, "net_contributions": 100, "profit": 10},
        ]

        def cached(path, *args, **kwargs):
            return {"valuation_series": series} if path == self.path else None

        with (
            patch.object(app, "FAMILY_PORTFOLIOS", {"missing": {"name": "Missing"}}),
            patch.object(app, "read_dashboard_cache", side_effect=cached),
            patch.object(app, "legacy_statement_candidates", return_value=[]),
        ):
            response = self.client.get("/api/rankings")
        self.assertEqual(response.status_code, 200)
        primary, missing = response.json["rankings"]
        self.assertEqual(primary["status"], "available")
        self.assertEqual(primary["returns"]["price"]["start"], 10)
        self.assertEqual(missing["status"], "unavailable")
        self.assertIsNone(missing["returns"]["price"]["start"])


if __name__ == "__main__":
    unittest.main()
