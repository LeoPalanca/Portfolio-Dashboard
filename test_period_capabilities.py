from __future__ import annotations

import json
import re
import unittest
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
    def test_fresh_install_omits_since_2024_button(self) -> None:
        with patch.object(app, "SINCE_2024_PORTFOLIO_IDS", set()), app.app.test_client() as client:
            html = client.get("/").get_data(as_text=True)

        self.assertNotIn('data-period="since24"', html)
        self.assertEqual(app_config(html)["since2024PortfolioIds"], [])
        self.assertNotIn("__SINCE_2024_PORTFOLIO_IDS__", html)

    def test_configured_portfolio_receives_since_2024_button(self) -> None:
        with patch.object(app, "SINCE_2024_PORTFOLIO_IDS", {app.PRIMARY_PORTFOLIO_ID}), app.app.test_client() as client:
            html = client.get("/").get_data(as_text=True)

        self.assertIn('data-period="since24"', html)
        self.assertEqual(app_config(html)["since2024PortfolioIds"], [app.PRIMARY_PORTFOLIO_ID])


if __name__ == "__main__":
    unittest.main()
