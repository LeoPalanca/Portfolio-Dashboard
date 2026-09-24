"""Release discovery and update-request safety checks."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app
from src.portfolio_dashboard.updates import github_release_status, newer_release_notes, version_tuple


class UpdateTest(unittest.TestCase):
    def test_changelog_includes_only_newer_releases(self) -> None:
        notes = "# Changelog\n\n## 0.8.0 - Today\n\nNew feature.\n\n## 0.7.1 - Yesterday\n\nFix.\n\n## 0.7.0 - Earlier\n\nOld.\n"
        self.assertEqual(version_tuple("0.8.0"), (0, 8, 0))
        self.assertIn("New feature.", newer_release_notes(notes, "0.7.0"))
        self.assertIn("Fix.", newer_release_notes(notes, "0.7.0"))
        self.assertNotIn("Old.", newer_release_notes(notes, "0.7.0"))

    def test_release_check_reads_fixed_github_metadata(self) -> None:
        def response(request: object, **_kwargs: object) -> io.BytesIO:
            url = request.full_url  # type: ignore[attr-defined]
            if url.endswith("pyproject.toml"):
                return io.BytesIO(b'[project]\nversion = "0.8.0"\n')
            return io.BytesIO(b'## 0.8.0 - Today\n\nUpdate control.\n')
        with patch("src.portfolio_dashboard.updates.urllib.request.urlopen", side_effect=response) as urlopen:
            result = github_release_status("0.7.0")
        self.assertEqual(urlopen.call_count, 2)
        self.assertTrue(result["available"])
        self.assertIn("Update control.", result["changelog"])

    def test_update_request_requires_page_token_and_queues_fixed_request(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            (Path(temporary) / "deployed-head").write_text("test-commit\n")
            with (
                patch.object(app.SETTINGS, "auto_update_enabled", True),
                patch.object(app, "UPDATE_STATE_DIR", Path(temporary)),
                patch.object(app, "update_release_status", return_value={"available": True, "latest_version": "0.8.0"}),
            ):
                client = app.app.test_client()
                self.assertEqual(client.post("/api/update").status_code, 403)
                self.assertEqual(client.post("/api/update", headers={"X-Update-Token": app._UPDATE_TOKEN,
                    "Origin": "https://unrelated.example"}).status_code, 403)
                response = client.post("/api/update", headers={"X-Update-Token": app._UPDATE_TOKEN})
                self.assertEqual(response.status_code, 202)
                self.assertIn("requested_at", json.loads((Path(temporary) / "request.json").read_text()))


if __name__ == "__main__":
    unittest.main()
