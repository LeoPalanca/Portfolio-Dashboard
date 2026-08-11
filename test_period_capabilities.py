from __future__ import annotations

import unittest
from unittest.mock import patch

import app


class PeriodCapabilityTest(unittest.TestCase):
    def test_fresh_install_omits_since_2024_button(self) -> None:
        with patch.object(app, "SINCE_2024_PORTFOLIO_IDS", set()), app.app.test_client() as client:
            html = client.get("/").get_data(as_text=True)

        self.assertNotIn('data-period="since24"', html)
        self.assertIn("const SINCE_2024_PORTFOLIO_IDS = new Set([])", html)
        self.assertNotIn("__SINCE_2024_PORTFOLIO_IDS__", html)

    def test_configured_portfolio_receives_since_2024_button(self) -> None:
        with patch.object(app, "SINCE_2024_PORTFOLIO_IDS", {app.PRIMARY_PORTFOLIO_ID}), app.app.test_client() as client:
            html = client.get("/").get_data(as_text=True)

        self.assertIn('data-period="since24"', html)
        self.assertIn(f'new Set(["{app.PRIMARY_PORTFOLIO_ID}"])', html)


if __name__ == "__main__":
    unittest.main()
