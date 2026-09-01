from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app


class DashboardPayloadCacheTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
