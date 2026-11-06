"""Evidence integrity, partial availability and financial history semantics."""

import json
import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from src.portfolio_dashboard.research_evidence import analyst_views, dashboard_news, history_metrics, shortlist


def chart(values, raw=None):
    return {
        "chart": {
            "result": [
                {
                    "timestamp": [1700000000 + i * 86400 for i in range(len(values))],
                    "indicators": {"adjclose": [{"adjclose": values}], "quote": [{"close": raw or values}]},
                }
            ]
        }
    }


class EvidenceTests(unittest.TestCase):
    def test_drawdown_respects_peak_before_trough(self):
        result = history_metrics(chart([100] * 16 + [100, 50, 200, 160]))
        window = result["windows"]["20"]
        self.assertAlmostEqual(window["drawdown_from_window_high_pct"], -20)
        self.assertAlmostEqual(window["max_drawdown_in_window_pct"], -50)
        self.assertIsNone(result["windows"]["60"])
        self.assertIsNone(result["return_20_sessions_pct"])

    def test_adjusted_series_does_not_create_a_split_crash(self):
        result = history_metrics(chart([100] * 260, [1000] * 200 + [100] * 60))
        self.assertEqual(result["windows"]["252"]["max_drawdown_in_window_pct"], 0)
        self.assertEqual(result["windows"]["252"]["drawdown_from_window_high_pct"], 0)
        self.assertEqual(result["return_20_sessions_pct"], 0)

    def test_missing_prices_cannot_become_valid_history(self):
        with self.assertRaises(ValueError):
            history_metrics(chart([None, float("nan"), -5]))

    def test_news_uses_explicit_symbols_and_filters_non_news_links(self):
        payload = {
            "generated_at": "2026-01-01T00:00:00Z",
            "items": [
                {
                    "symbol": "DEMO",
                    "title": "Public headline",
                    "link": "https://example.org/news",
                    "published": "2026-01-01",
                },
                {"symbol": "PRIVATE", "title": "Other portfolio", "link": "https://example.org/other"},
                {"symbol": "DEMO", "title": "Bad link", "link": "javascript:alert(1)"},
            ],
        }
        with patch("src.portfolio_dashboard.research_evidence.read_json", return_value=payload) as fetch:
            result = dashboard_news("http://127.0.0.1:8050", ["DEMO"])
        self.assertIn("/api/news?symbols=DEMO", fetch.call_args.args[0])
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["coverage"], "headline only; full article not fetched")
        self.assertEqual(result["dashboard_generated_at"], payload["generated_at"])

    def test_no_symbols_never_falls_back_to_private_holdings(self):
        with patch("src.portfolio_dashboard.research_evidence.read_json") as fetch:
            dashboard_news("http://127.0.0.1:8050", [])
        fetch.assert_not_called()

    def test_partial_analyst_data_preserves_counts_and_unknown_issue_date(self):
        ticker = MagicMock()
        ticker.get_info.side_effect = RuntimeError("provider unavailable")
        ticker.get_recommendations_summary.return_value = pd.DataFrame(
            [{"period": "0m", "strongBuy": 2, "buy": 3, "hold": 4, "sell": 1, "strongSell": 0}]
        )
        ticker.get_upgrades_downgrades.side_effect = RuntimeError("missing")
        with patch("yfinance.Ticker", return_value=ticker):
            result = analyst_views("DEMO")
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["rating_counts"]["buy"], 3)
        self.assertIsNone(result["rating_as_of"])
        self.assertIsNone(result["target_as_of"])
        self.assertIsNone(result["targets"])
        json.dumps(result, allow_nan=False)

    def test_shortlist_cannot_include_unaffordable_or_unknown_prices(self):
        rows = [
            {"symbol": "COSTLY", "change_pct": -50, "reference_usable": True, "whole_shares_with_cash": 0},
            {"symbol": "STALE", "change_pct": -40, "reference_usable": False, "whole_shares_with_cash": 10},
            {"symbol": "SECOND", "change_pct": -5, "reference_usable": True, "whole_shares_with_cash": 1},
            {"symbol": "FIRST", "change_pct": -10, "reference_usable": True, "whole_shares_with_cash": 2},
        ]
        self.assertEqual(shortlist({"rows": rows}), ["FIRST", "SECOND"])
