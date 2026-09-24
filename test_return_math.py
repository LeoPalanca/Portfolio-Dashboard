"""Regression checks for the browser's cash-flow-adjusted return series."""

from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parent / "static" / "app.js"


@unittest.skipUnless(shutil.which("node"), "Node.js is needed to run the browser return formula")
class ReturnMathTest(unittest.TestCase):
    def calculate(self, rows: list[dict[str, object]]) -> list[dict[str, object]]:
        source = SCRIPT.read_text(encoding="utf-8")
        start = source.index("function portfolioTimeWeightedReturns(series) {")
        end = source.index("function normalizeReturnSeries(series) {", start)
        function = source[start:end]
        script = (
            'const selectedReturnMode = "price";\n'
            + function
            + "\nprocess.stdout.write(JSON.stringify(portfolioTimeWeightedReturns("
            + json.dumps(rows)
            + ")));"
        )
        result = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
        return json.loads(result.stdout)

    def test_a_buy_keeps_the_cash_flow_adjusted_return_interval(self) -> None:
        rows = [
            {"market_value": 100, "net_contributions": 100, "priced_positions": 1, "unpriced_positions": 0},
            {"market_value": 220, "net_contributions": 200, "priced_positions": 2, "unpriced_positions": 0},
            {"market_value": 250, "net_contributions": 200, "priced_positions": 2, "unpriced_positions": 0},
        ]
        result = self.calculate(rows)
        self.assertAlmostEqual(result[1]["return_pct"], 20)
        self.assertAlmostEqual(result[2]["return_pct"], 36.363636, places=5)

    def test_a_quote_coverage_change_is_excluded(self) -> None:
        rows = [
            {"market_value": 100, "net_contributions": 100, "priced_positions": 1, "unpriced_positions": 1},
            {"market_value": 180, "net_contributions": 100, "priced_positions": 2, "unpriced_positions": 0},
            {"market_value": 198, "net_contributions": 100, "priced_positions": 2, "unpriced_positions": 0},
        ]
        result = self.calculate(rows)
        self.assertAlmostEqual(result[1]["return_pct"], 0)
        self.assertAlmostEqual(result[2]["return_pct"], 10)

    def calculate_equity(self, rows: list[dict[str, object]]) -> list[float | None]:
        source = SCRIPT.read_text(encoding="utf-8")
        start = source.index("function equityTimeWeightedReturns(series) {")
        end = source.index("function normalizeReturnSeries(series) {", start)
        script = source[start:end] + "\nprocess.stdout.write(JSON.stringify(equityTimeWeightedReturns(" + json.dumps(rows) + ")));"
        result = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
        return json.loads(result.stdout)

    def test_equity_return_includes_dividends_and_adjusts_for_trades(self) -> None:
        rows = [
            {"equity_market_value": 100, "equity_net_contributions": 100, "equity_dividends": 0, "equity_unpriced_positions": 0},
            {"equity_market_value": 110, "equity_net_contributions": 100, "equity_dividends": 5, "equity_unpriced_positions": 0},
            {"equity_market_value": 220, "equity_net_contributions": 200, "equity_dividends": 5, "equity_unpriced_positions": 0},
        ]
        result = self.calculate_equity(rows)
        self.assertAlmostEqual(result[1], 15)
        self.assertAlmostEqual(result[2], 25.454545, places=5)

    def test_equity_comparison_requires_complete_quote_coverage(self) -> None:
        rows = [
            {"equity_market_value": 100, "equity_net_contributions": 100, "equity_dividends": 0, "equity_unpriced_positions": 0},
            {"equity_market_value": 110, "equity_net_contributions": 100, "equity_dividends": 0, "equity_unpriced_positions": 1},
        ]
        self.assertEqual(self.calculate_equity(rows), [None, None])


if __name__ == "__main__":
    unittest.main()
