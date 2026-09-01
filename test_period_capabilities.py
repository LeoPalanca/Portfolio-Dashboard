from __future__ import annotations

import json
import re
import unittest
from datetime import date
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import app

APP_CONFIG_RE = re.compile(
    r'<script id="app-config" type="application/json">(.*?)</script>', re.DOTALL
)


def app_config(html: str) -> dict[str, Any]:
    """Read the JSON config island the page hands to static/app.js."""
    match = APP_CONFIG_RE.search(html)
    assert match is not None, "app-config island missing from rendered page"
    payload: dict[str, Any] = json.loads(match.group(1).replace("\\u003c", "<"))
    return payload


class PeriodCapabilityTest(unittest.TestCase):
    def test_fresh_install_hides_multi_portfolio_rankings(self) -> None:
        with patch.object(app, "SETTINGS", SimpleNamespace(portfolios={})), app.app.test_client() as client:
            html = client.get("/").get_data(as_text=True)

        self.assertNotIn("Family Rankings", html)

    def test_fresh_install_offers_custom_window_without_a_private_default(self) -> None:
        with patch.object(app, "DEFAULT_CUSTOM_PERIOD_START", None), app.app.test_client() as client:
            html = client.get("/").get_data(as_text=True)

        self.assertIn('data-period="custom"', html)
        self.assertIsNone(app_config(html)["defaultCustomPeriodStart"])

    def test_private_default_custom_start_is_sent_to_the_browser(self) -> None:
        with patch.object(app, "DEFAULT_CUSTOM_PERIOD_START", date(2024, 1, 1)), app.app.test_client() as client:
            html = client.get("/").get_data(as_text=True)

        self.assertIn('data-period="custom"', html)
        self.assertEqual(app_config(html)["defaultCustomPeriodStart"], "2024-01-01")


if __name__ == "__main__":
    unittest.main()
