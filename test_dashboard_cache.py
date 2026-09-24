from __future__ import annotations

import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import app


class DashboardPayloadCacheTest(unittest.TestCase):
    def setUp(self) -> None:
        app._DASHBOARD_MEMORY_CACHE.clear()
        app._PRICE_REFRESH_JOBS.clear()

    def test_normal_load_reuses_persistent_snapshot_and_refresh_replaces_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cache_dir = Path(temporary)
            builds = [
                {"generated_at": "first", "totals": {"market_value": 1}},
                {"generated_at": "refreshed", "totals": {"market_value": 2}},
            ]
            with (
                patch.object(app, "DASHBOARD_CACHE_DIR", cache_dir),
                patch.object(app, "dashboard_source_signature", return_value="inputs-v1"),
                patch.object(app, "_build_dashboard_payload", side_effect=builds) as build,
            ):
                first = app.dashboard_payload(person=app.PRIMARY_PORTFOLIO_ID)
                cache_file = next(cache_dir.glob("*.json"))
                cache_file.unlink()
                cached = app.dashboard_payload(person=app.PRIMARY_PORTFOLIO_ID)
                refreshed = app.dashboard_payload(refresh=True, person=app.PRIMARY_PORTFOLIO_ID)
                cached_after_refresh = app.dashboard_payload(person=app.PRIMARY_PORTFOLIO_ID)

        self.assertEqual(first, cached)
        self.assertEqual(refreshed, cached_after_refresh)
        self.assertEqual(refreshed["totals"]["market_value"], 2)
        self.assertEqual(build.call_count, 2)

    def test_source_signature_change_invalidates_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cache_dir = Path(temporary)
            signatures = iter(
                ["inputs-v1", "inputs-v1", "inputs-v1", "inputs-v2", "inputs-v2", "inputs-v2"]
            )
            builds = [
                {"generated_at": "first"},
                {"generated_at": "after-import"},
            ]
            with (
                patch.object(app, "DASHBOARD_CACHE_DIR", cache_dir),
                patch.object(app, "dashboard_source_signature", side_effect=signatures),
                patch.object(app, "_build_dashboard_payload", side_effect=builds) as build,
            ):
                first = app.dashboard_payload(person=app.PRIMARY_PORTFOLIO_ID)
                after_import = app.dashboard_payload(person=app.PRIMARY_PORTFOLIO_ID)

        self.assertNotEqual(first, after_import)
        self.assertEqual(build.call_count, 2)

    def test_expired_snapshot_is_rebuilt_without_an_explicit_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cache_dir = Path(temporary)
            expired = (datetime.now() - timedelta(seconds=app.PRICE_TTL_SECONDS + 1)).isoformat()
            builds = [
                {"generated_at": expired, "totals": {"market_value": 1}},
                {"generated_at": datetime.now().isoformat(), "totals": {"market_value": 2}},
            ]
            with (
                patch.object(app, "DASHBOARD_CACHE_DIR", cache_dir),
                patch.object(app, "dashboard_source_signature", return_value="inputs-v1"),
                patch.object(app, "_build_dashboard_payload", side_effect=builds) as build,
            ):
                first = app.dashboard_payload(person=app.PRIMARY_PORTFOLIO_ID)
                rebuilt = app.dashboard_payload(person=app.PRIMARY_PORTFOLIO_ID)

        self.assertEqual(first["totals"]["market_value"], 1)
        self.assertEqual(rebuilt["totals"]["market_value"], 2)
        self.assertEqual(build.call_count, 2)

    def test_running_refresh_keeps_old_snapshot_available(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "snapshot.json"
            expired = {"generated_at": (datetime.now() - timedelta(days=1)).isoformat()}
            with patch.object(app, "dashboard_source_signature", return_value="inputs-v1"):
                app.write_dashboard_cache(path, "inputs-v1", expired)
                self.assertIsNone(app.read_dashboard_cache(path, "inputs-v1"))
                self.assertEqual(app.read_dashboard_cache(path, "inputs-v1", allow_expired=True), expired)
                self.assertIsNone(app.read_dashboard_cache(path, "inputs-v2"))
                self.assertEqual(app.read_dashboard_cache(path, "inputs-v2", allow_expired=True), expired)

    def test_price_refresh_endpoint_returns_before_background_rebuild(self) -> None:
        payload = {"generated_at": datetime.now().isoformat(), "pricing_as_of": "2026-09-16"}
        with patch.object(app, "dashboard_payload", return_value=payload) as build:
            client = app.app.test_client()
            started = client.post("/api/portfolio/refresh-prices")
            self.assertEqual(started.status_code, 202)
            self.assertEqual(started.json["status"], "running")
            for _ in range(100):
                status = client.get("/api/portfolio/refresh-prices")
                if status.json["status"] == "done":
                    break
                time.sleep(0.01)
        self.assertEqual(status.json["status"], "done")
        self.assertEqual(status.json["pricing_as_of"], "2026-09-16")
        self.assertTrue(build.call_args.kwargs["refresh"])


if __name__ == "__main__":
    unittest.main()
