"""Server-side return math: valuation dates, variation cards and Trade Republic dividends."""

from __future__ import annotations

import io
import json
import shutil
import subprocess
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import app

TR_HEADER = (
    "datetime,date,account_type,category,type,asset_class,name,symbol,shares,price,amount,fee,tax,currency,"
    "original_amount,original_currency,fx_rate,description,transaction_id,counterparty_name,counterparty_iban,"
    "payment_reference,mcc_code\n"
)


def point(day: str, value: float, contributions: float, msci: float = 0.0, **extra: float) -> dict:
    return {
        "date": day,
        "market_value": value,
        "net_contributions": contributions,
        "profit": value - contributions,
        "msci_return_pct": msci,
        "msci_price_date": day,
        "priced_positions": 1,
        "unpriced_positions": 0,
        **extra,
    }


class ValuationDateGridTest(unittest.TestCase):
    def test_prices_the_day_before_each_flow_and_the_one_year_anchor(self) -> None:
        start, end = date(2024, 1, 10), date(2026, 11, 24)
        grid = app.valuation_date_grid(start, end, {date(2024, 1, 10), date(2025, 6, 18)})
        self.assertIn(date(2025, 6, 18), grid)
        self.assertIn(date(2025, 6, 17), grid)
        self.assertIn(date(2025, 11, 24), grid)  # 1Y window start
        self.assertIn(date(2025, 6, 30), grid)  # month end
        self.assertIn(date(2026, 10, 21), grid)  # last 35 days
        self.assertNotIn(date(2024, 1, 9), grid)  # before the first trade
        self.assertNotIn(date(2026, 10, 19), grid)
        self.assertEqual(min(grid), start)
        self.assertEqual(max(grid), end)

    def test_one_year_anchor_on_29_february(self) -> None:
        self.assertEqual(app.one_year_before(date(2028, 2, 29)), date(2027, 2, 28))

    def test_mid_month_buy_needs_the_day_before(self) -> None:
        # Old holdings gain 10% during the month; 4,000 is bought on the 18th.
        with_day_before = [
            point("2025-05-31", 1000, 1000),
            point("2025-06-17", 1100, 1000),
            point("2025-06-18", 5100, 5000),
        ]
        month_only = [with_day_before[0], with_day_before[2]]
        self.assertAlmostEqual(app.time_weighted_return_pct(with_day_before, "market_value", "net_contributions"), 10.0)
        self.assertNotAlmostEqual(
            app.time_weighted_return_pct(month_only, "market_value", "net_contributions"), 10.0, places=0
        )


class VariationCardTest(unittest.TestCase):
    def test_purchase_in_the_window_is_not_performance(self) -> None:
        # 1,000 portfolio, 9,000 bought on the 20th, everything (MSCI too) +1% over the week.
        series = [
            point(
                "2026-11-17",
                1000.0,
                1000.0,
                total_market_value=1000.0,
                total_net_contributions=1000.0,
                total_profit=0.0,
            ),
            point(
                "2026-11-20",
                10000.0,
                10000.0,
                total_market_value=10000.0,
                total_net_contributions=10000.0,
                total_profit=0.0,
            ),
            point(
                "2026-11-24",
                10100.0,
                10000.0,
                msci=1.0,
                total_market_value=10100.0,
                total_net_contributions=10000.0,
                total_profit=100.0,
            ),
        ]
        week = app.calculate_variations(series)["1w"]
        self.assertEqual(week["pct"], 1.0)
        self.assertEqual(week["amount"], 100.0)
        self.assertEqual(week["vs_msci_pct"], 0.0)
        self.assertEqual(week["total_pct"], 1.0)
        self.assertEqual(week["total_amount"], 100.0)
        self.assertEqual(week["total_vs_msci_pct"], 0.0)

    def test_series_without_total_fields_keeps_price_cards(self) -> None:
        series = [point("2026-11-17", 1000.0, 1000.0), point("2026-11-24", 1010.0, 1000.0)]
        week = app.calculate_variations(series)["1w"]
        self.assertEqual(week["pct"], 1.0)
        self.assertIsNone(week["total_pct"])
        self.assertIsNone(week["total_amount"])

    def test_python_and_browser_growth_formulas_agree(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not installed")
        source = (Path(__file__).resolve().parent / "static" / "app.js").read_text(encoding="utf-8")
        start = source.index("    function flowAdjustedGrowth(")
        end = source.index("    function normalizeReturnSeries(", start)
        cases = [
            (1000, 1100, 0),
            (1000, 5100, 4000),
            (1000, 7100, 6000),
            (1000, 200, -900),
            (5, 10105, 10000),
            (100, 0, -150),
        ]
        script = (
            source[start:end]
            + f"\nconsole.log(JSON.stringify({json.dumps(cases)}.map(c => flowAdjustedGrowth(...c))));"
        )
        browser = json.loads(subprocess.run([node, "-e", script], capture_output=True, text=True, check=True).stdout)
        for case, expected in zip(cases, browser):
            with self.subTest(case=case):
                self.assertAlmostEqual(app.flow_adjusted_growth(*case), expected)


class TradeRepublicDividendTest(unittest.TestCase):
    def test_net_from_reported_gross_and_reversal(self) -> None:
        self.assertEqual(
            app.trade_republic_dividend_net(Decimal("1.00"), Decimal("0.26")), (Decimal("0.74"), Decimal("0.26"))
        )
        self.assertEqual(
            app.trade_republic_dividend_net(Decimal("-1.00"), Decimal("0.26")), (Decimal("-0.74"), Decimal("-0.26"))
        )

    def test_ledger_reads_net_dividends_for_trade_republic(self) -> None:
        export = TR_HEADER + (
            ",2025-05-13,,,DIVIDEND,,Example AG,XX0000000002,2,,1.00,,-0.26,EUR,,,,Cash Dividend,tx-1,,,,\n"
            ",2025-06-03,,,DIVIDEND,,Example AG,XX0000000002,2,,-1.00,,0.26,EUR,,,,Cash Dividend,tx-2,,,,\n"
            ",2025-06-03,,,DIVIDEND,,Example AG,XX0000000002,2,,1.00,,-0.26,EUR,,,,Cash Dividend,tx-3,,,,\n"
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with (
                patch.object(app, "ROOT_DIR", root / "sources"),
                patch.object(app, "MOVEMENT_DATABASE", root / "private" / "movements.sqlite3"),
                patch.object(app, "_movement_store", None),
                app.app.test_client() as client,
            ):
                response = client.post(
                    "/api/imports",
                    data={"source": "trade_republic", "file": (io.BytesIO(export.encode()), "tr.csv")},
                    content_type="multipart/form-data",
                )
                self.assertEqual(response.status_code, 200, response.get_json())
                dividends = app.read_ledger_dividends()
                summary = app.summarize_dividends(dividends)

        self.assertEqual(sorted(d.amount_eur for d in dividends), [Decimal("-0.74"), Decimal("0.74"), Decimal("0.74")])
        self.assertEqual(summary["total_eur"], 0.74)
        self.assertEqual(summary["tax_eur"], 0.26)
        self.assertEqual(summary["gross_eur"], 1.0)


if __name__ == "__main__":
    unittest.main()
