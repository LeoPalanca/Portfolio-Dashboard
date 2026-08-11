from __future__ import annotations

import unittest
from unittest.mock import patch

import app


class NewsPayloadTest(unittest.TestCase):
    def test_supplied_symbols_skip_dashboard_recompute(self) -> None:
        with (
            patch.object(app, "dashboard_payload") as dashboard_payload,
            patch.object(app, "fetch_symbol_news", return_value=[]),
            patch.object(app, "get_news_cache", return_value={}),
            patch.object(app, "save_json"),
        ):
            result = app.portfolio_news_payload(symbols=["aapl", "USD", "bad symbol", "MSFT"])

        dashboard_payload.assert_not_called()
        self.assertEqual(result["symbols"], ["AAPL", "MSFT"])

    def test_news_payload_falls_back_to_dashboard_when_symbols_missing(self) -> None:
        dashboard = {
            "positions": [
                {
                    "asset": "NVIDIA",
                    "symbol": "NVDA",
                    "isin": "US67066G1040",
                    "is_open": True,
                    "market_value_eur": 1000,
                }
            ],
            "distribution": {"rows": []},
        }

        with (
            patch.object(app, "dashboard_payload", return_value=dashboard) as dashboard_payload,
            patch.object(app, "fetch_symbol_news", return_value=[]),
            patch.object(app, "get_news_cache", return_value={}),
            patch.object(app, "save_json"),
        ):
            result = app.portfolio_news_payload()

        dashboard_payload.assert_called_once()
        self.assertEqual(result["symbols"], ["NVDA"])


if __name__ == "__main__":
    unittest.main()
