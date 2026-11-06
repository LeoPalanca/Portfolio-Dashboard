"""Evidence integrity, partial availability and financial history semantics."""

import json
import math
import statistics
import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from src.portfolio_dashboard.research_evidence import (
    analyst_views,
    build_evidence,
    dashboard_news,
    history_metrics,
    shortlist,
)


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
    def test_volatility_scans_all_100_even_when_only_six_are_affordable(self):
        rows = [
            {"symbol": f"D{i}", "reference_usable": True, "change_pct": -i, "whole_shares_with_cash": 1 if i < 6 else 0}
            for i in range(100)
        ]

        def history(_symbol):
            return {
                "status": "available",
                "last_bar_date": "2026-11-05",
                "volatility": {"annualized_20_pct": 30.0, "as_of": "2026-11-05"},
            }

        with (
            patch("src.portfolio_dashboard.research_evidence.price_history", side_effect=history) as fetch,
            patch("src.portfolio_dashboard.research_evidence.dashboard_news", return_value={"items": []}),
            patch("src.portfolio_dashboard.research_evidence.analyst_views", return_value={"status": "unavailable"}),
        ):
            evidence = build_evidence({"rows": rows}, "http://localhost")
        self.assertEqual(fetch.call_count, 101)  # all stocks plus SPY
        self.assertEqual(evidence["volatility_scan"]["available"], 100)
        self.assertEqual(len(evidence["volatility_scan"]["rows"]), 100)
        self.assertEqual(len(evidence["symbols"]), 6)

    def test_volatility_uses_sample_log_returns_and_prior_only_shock(self):
        returns = [0.01, -0.01] * 10 + [0.05]
        values = [100.0]
        for value in returns:
            values.append(values[-1] * math.exp(value))
        vol = history_metrics(chart(values))["volatility"]
        expected = statistics.stdev(returns[-20:]) * math.sqrt(252) * 100
        self.assertAlmostEqual(vol["annualized_20_pct"], expected)
        self.assertAlmostEqual(vol["last_close_sigma"], 0.05 / statistics.stdev(returns[:-1]))
        self.assertIsNone(vol["annualized_60_pct"])

    def test_partial_regular_session_bar_is_excluded_from_volatility(self):
        payload = chart([100, 101] * 12 + [50])
        result = payload["chart"]["result"][0]
        start = result["timestamp"][-1]
        result["meta"] = {"currentTradingPeriod": {"regular": {"start": start, "end": start + 20000}}}
        actual = history_metrics(payload, now_ts=start + 3600)["volatility"]
        expected = history_metrics(chart([100, 101] * 12))["volatility"]
        self.assertAlmostEqual(actual["annualized_20_pct"], expected["annualized_20_pct"])
        self.assertEqual(actual["as_of"], expected["as_of"])

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
