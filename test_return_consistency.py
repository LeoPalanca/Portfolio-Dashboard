"""Return figures stay consistent: flows priced on their own day, wallet flows at money
value, one calendar-month rule and exported figures that match their window.

All amounts are synthetic.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import patch

import app

TODAY = date.today()  # noqa: DTZ011 - wallet and value histories run up to today
NO_HISTORY = {"status": "history_error", "prices": {}}


def month_end(day: date) -> date:
    following = date(day.year + (day.month == 12), day.month % 12 + 1, 1)
    return following - timedelta(days=1)


def etf_buy(day: date, quantity: str, amount: str) -> app.Trade:
    return app.Trade(
        asset="Example Equity ETF",
        isin="XX0000000001",
        broker="Example Broker",
        action="BUY",
        currency_hint="EUR",
        cash_currency="EUR",
        date=day,
        price=Decimal(amount) / Decimal(quantity),
        quantity=Decimal(quantity),
        quantity_diff=Decimal(quantity),
        total_spend=Decimal(amount),
        fees=Decimal(0),
        tax=Decimal(0),
        grand_total=Decimal(amount),
        grand_total_present=True,
        source="synthetic_test",
    )


def window(series: list[dict[str, Any]], first: date, last: date) -> list[dict[str, Any]]:
    return [point for point in series if first.isoformat() <= point["date"] <= last.isoformat()]


class TotalModeFlowDatesTest(unittest.TestCase):
    def test_only_money_moved_in_or_out_adds_a_date(self) -> None:
        deposit, interest, revolut_top_up, revolut_exchange = (date(2026, 3, d) for d in (3, 4, 5, 6))
        dates = app.cash_flow_dates(
            [(deposit, Decimal("500"), Decimal("500")), (interest, Decimal("2"), Decimal("0"))],
            [],
            [
                {"date": revolut_top_up, "contrib_change": Decimal("100")},
                {"date": revolut_exchange, "contrib_change": Decimal("0")},
            ],
        )
        self.assertEqual(dates, {deposit, revolut_top_up})

    def run_series(self, cash: list[tuple[date, Decimal, Decimal]], buy_day: date, prices: dict[str, float], **kwargs: Any):
        def history(symbol: str, *_args: object, **_kwargs: object) -> dict[str, object]:
            if symbol == "TEST.MI":
                return {"status": "priced", "currency": "EUR", "prices": prices}
            return NO_HISTORY

        with (
            patch.object(app, "resolve_isin", return_value={"symbol": "TEST.MI", "status": "priced"}),
            patch.object(app, "fetch_history", side_effect=history),
            patch.object(app, "current_price_overrides", return_value={}),
            patch.object(app, "fetch_eurostat_cpi", return_value={}),
            patch.object(app, "read_portfolio_dividends", return_value=[]),
            patch.object(app, "read_cash_interests", return_value=[]),
            patch.object(app, "load_cash_histories", return_value=(cash, [], [])),
            patch.object(app, "read_exposures", return_value={}),
        ):
            return app.calculate_valuation_series(
                [etf_buy(buy_day, "100", "10000")], {}, person=app.PRIMARY_PORTFOLIO_ID, broker="all", **kwargs
            )["series"]

    def test_deposit_on_the_25th_is_priced_on_its_own_day(self) -> None:
        # 10,000 of an ETF gains 3% by the 24th; 30,000 lands on the cash account on
        # the 25th. Over the month the money invested earned exactly 3%.
        month = (TODAY - timedelta(days=150)).replace(day=1)
        start = month - timedelta(days=1)
        day_24, day_25, end = month.replace(day=24), month.replace(day=25), month_end(month)
        series = self.run_series(
            [(day_25, Decimal("30000"), Decimal("30000"))],
            start,
            {start.isoformat(): 100.0, day_24.isoformat(): 103.0},
        )
        dates = [point["date"] for point in series]
        self.assertIn(day_24.isoformat(), dates)
        self.assertIn(day_25.isoformat(), dates)
        points = window(series, start, end)
        twr = app.time_weighted_return_pct(points, "total_market_value", "total_net_contributions")
        self.assertAlmostEqual(twr, 3.0, places=6)
        # Left inside the month-long interval, the deposit would count for half of it.
        month_only = [points[0], points[-1]]
        self.assertAlmostEqual(
            app.time_weighted_return_pct(month_only, "total_market_value", "total_net_contributions"), 1.2, places=6
        )

    def test_wallet_transaction_dates_are_priced_in_the_all_broker_history(self) -> None:
        start = (TODAY - timedelta(days=200)).replace(day=1)
        wallet_day = start + timedelta(days=40)
        series = self.run_series([], start, {start.isoformat(): 100.0}, extra_flow_dates={wallet_day})
        dates = {point["date"] for point in series}
        self.assertIn(wallet_day.isoformat(), dates)
        self.assertIn((wallet_day - timedelta(days=1)).isoformat(), dates)


class CryptoWalletFlowTest(unittest.TestCase):
    def wallet(self, events: list[dict[str, Any]], positions: list[dict[str, Any]], prices: dict[date, float], **kwargs):
        history = {"status": "priced", "prices": {day.isoformat(): value for day, value in prices.items()}}
        with (
            patch.object(app, "read_crypto_events", return_value=events),
            patch.object(app, "fetch_crypto_eur_history", return_value=history),
            patch.object(app, "fetch_history", return_value=NO_HISTORY),
            patch.object(app, "fetch_eurostat_cpi", return_value={}),
        ):
            return app.crypto_wallet_valuation(positions, **kwargs)

    @staticmethod
    def event(day: date, quantity: str, cash: str, kind: str = "") -> dict[str, Any]:
        return {"date": day, "asset": "BTC", "quantity": Decimal(quantity), "cash_eur": Decimal(cash), "type": kind}

    @staticmethod
    def position(quantity: str, value: str) -> dict[str, Any]:
        return {"asset": "BTC", "symbol": "BTC", "quantity": float(quantity), "market_value_eur": float(value), "cost_basis_eur": 0.0}

    def test_a_sale_at_a_flat_price_is_not_a_loss(self) -> None:
        # 1 coin bought for 10,000 is worth 50,000; half is sold at that price.
        bought, risen, sold = TODAY - timedelta(days=120), TODAY - timedelta(days=80), TODAY - timedelta(days=60)
        result = self.wallet(
            [self.event(bought, "1", "10000", "buy"), self.event(sold, "-0.5", "-25000", "sell")],
            [self.position("0.5", "25000")],
            {bought: 10000.0, risen: 50000.0},
        )
        series = result["series"]
        sale_day = window(series, sold - timedelta(days=1), sold)
        self.assertEqual([point["date"] for point in sale_day], [(sold - timedelta(days=1)).isoformat(), sold.isoformat()])
        self.assertAlmostEqual(app.time_weighted_return_pct(sale_day, "market_value", "net_contributions"), 0.0, places=6)
        # Money in minus money out: the realised and the open gain are both profit.
        self.assertEqual(sale_day[-1]["net_contributions"], -15000.0)
        self.assertEqual(series[-1]["profit"], 40000.0)

    def test_the_snapshot_gap_is_booked_once_not_every_day(self) -> None:
        # The transactions explain 1 coin; the snapshot holds 1.1 across two wallets
        # (0.1 from rewards paid elsewhere). Prices are flat for the last 50 days.
        bought, risen = TODAY - timedelta(days=100), TODAY - timedelta(days=50)
        result = self.wallet(
            [self.event(bought, "1", "10000", "buy")],
            [self.position("1", "20000"), self.position("0.1", "2000")],
            {bought: 10000.0, risen: 20000.0},
        )
        series = result["series"]
        self.assertEqual(series[-1]["market_value"], 22000.0)  # the headline value
        # The 0.1 is booked once, on the last transaction date, at that day's price.
        later = [point["net_contributions"] for point in series if point["date"] >= bought.isoformat()]
        self.assertEqual(set(later), {11000.0})
        for period in ("1d", "1w", "1m"):
            with self.subTest(period=period):
                self.assertEqual(result["variations"][period]["pct"], 0.0)

    def test_todays_live_price_is_a_real_move(self) -> None:
        bought = TODAY - timedelta(days=100)
        result = self.wallet(
            [self.event(bought, "1", "20000", "buy")],
            [self.position("1.1", "22220")],  # 20,200 a coin today, 20,000 at yesterday's close
            {bought: 20000.0},
        )
        self.assertEqual(result["variations"]["1d"]["pct"], 1.0)

    def test_rewards_are_income_and_transfers_count_at_market_value(self) -> None:
        reward = self.event(TODAY, "0.01", "500", "staking_reward")
        self.assertEqual(app.crypto_event_flow(reward, Decimal("50000")), Decimal(0))
        received = self.event(TODAY, "0.02", "0", "send")
        self.assertEqual(app.crypto_event_flow(received, Decimal("50000")), Decimal("1000"))
        sold = self.event(TODAY, "-0.5", "-25000", "sell")
        self.assertEqual(app.crypto_event_flow(sold, Decimal("50000")), Decimal("-25000"))

    def test_extra_dates_are_priced(self) -> None:
        bought = TODAY - timedelta(days=200)
        extra = bought + timedelta(days=17)
        result = self.wallet([self.event(bought, "1", "100", "buy")], [self.position("1", "100")], {bought: 100.0}, extra_dates={extra})
        self.assertIn(extra.isoformat(), {point["date"] for point in result["series"]})


class CalendarMonthTest(unittest.TestCase):
    def test_one_month_before_month_end_is_the_previous_month_end(self) -> None:
        self.assertEqual(app.months_before(date(2026, 3, 31), 1), date(2026, 2, 28))
        self.assertEqual(app.months_before(date(2028, 3, 31), 1), date(2028, 2, 29))
        self.assertEqual(app.months_before(date(2026, 1, 15), 1), date(2025, 12, 15))
        self.assertEqual(app.months_before(date(2028, 2, 29), 12), date(2027, 2, 28))

    def test_python_and_browser_month_rules_agree(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not installed")
        source = (Path(__file__).resolve().parent / "static" / "app.js").read_text(encoding="utf-8")
        start = source.index("    function monthsBefore(")
        end = source.index("    function filterByPeriod(", start)
        cases = [("2026-03-31", 1), ("2028-03-31", 1), ("2026-01-31", 1), ("2026-05-31", 12), ("2028-02-29", 12), ("2026-11-24", 1)]
        script = source[start:end] + (
            f"\nconsole.log(JSON.stringify({json.dumps(cases)}.map(([d, m]) => {{"
            "const r = monthsBefore(new Date(`${d}T00:00:00`), m);"
            "return `${r.getFullYear()}-${String(r.getMonth() + 1).padStart(2, '0')}-${String(r.getDate()).padStart(2, '0')}`;"
            "})));"
        )
        browser = json.loads(subprocess.run([node, "-e", script], capture_output=True, text=True, check=True).stdout)
        for (day, months), expected in zip(cases, browser):
            with self.subTest(day=day, months=months):
                self.assertEqual(app.months_before(date.fromisoformat(day), months).isoformat(), expected)

    def test_month_card_starts_a_calendar_month_back(self) -> None:
        series = [
            {"date": day, "market_value": 1000.0, "net_contributions": 1000.0, "profit": 0.0, "priced_positions": 1, "unpriced_positions": 0}
            for day in ("2026-02-27", "2026-02-28", "2026-03-01", "2026-03-31")
        ]
        self.assertEqual(app.calculate_variations(series)["1m"]["past_date"], "2026-02-28")


class ExportWindowTest(unittest.TestCase):
    PAYLOAD = {
        "totals": {"return_pct": 50.0, "realized_pl": 900.0, "net_contributions": 3000.0, "unrealized_pl": 1500.0},
        "valuation_series": [
            {"date": "2026-01-05", "market_value": 2000.0, "net_contributions": 2000.0, "profit": 0.0},
            {"date": "2026-10-31", "market_value": 2000.0, "net_contributions": 2000.0, "profit": 0.0},
            {"date": "2026-11-17", "market_value": 3000.0, "net_contributions": 3000.0, "profit": 0.0},
            {"date": "2026-11-24", "market_value": 3030.0, "net_contributions": 3000.0, "profit": 30.0},
        ],
        "series": [
            {"date": "2026-01-05", "net_contributions": 2000.0, "realized_pl": 900.0},
            {"date": "2026-11-17", "net_contributions": 3000.0, "realized_pl": 900.0},
        ],
    }

    def overview(self, period: str) -> dict[str, Any]:
        rows = app.dashboard_export_context(self.PAYLOAD, "primary", "stock", "off", "all", "off", period)
        return {row[0]: row[1] for row in rows}

    def test_window_figures_match_the_window(self) -> None:
        # 1W runs from the 17 November close, which already holds that day's purchase.
        week = self.overview("1w")
        self.assertEqual(week["Return %"], 1.0)
        self.assertEqual(week["Return basis"], "Time-weighted, 2026-11-17 to 2026-11-24")
        self.assertEqual(week["Net contributions EUR"], 0.0)
        self.assertEqual(week["Realized P/L EUR"], 0.0)
        month = self.overview("1m")  # 24 October: the 31 October point is the nearer one
        self.assertEqual(month["Net contributions EUR"], 1000.0)
        self.assertEqual(month["Return %"], 1.0)

    def test_benchmark_sheet_reports_the_same_window_return(self) -> None:
        rows = app.benchmark_export_rows(self.PAYLOAD, "1w")
        self.assertEqual(rows[0], {"metric": "Portfolio return", "value_pct": 1.0, "comparison": ""})

    def test_single_point_window_says_it_is_the_return_since_start(self) -> None:
        payload = {**self.PAYLOAD, "valuation_series": self.PAYLOAD["valuation_series"][:1]}
        week = self.overview("1w")
        sparse = {row[0]: row[1] for row in app.dashboard_export_context(payload, "primary", "stock", "off", "all", "off", "1w")}
        self.assertNotEqual(week["Return basis"], sparse["Return basis"])
        self.assertEqual(sparse["Return %"], 50.0)
        self.assertIn("since the first trade", sparse["Return basis"])


if __name__ == "__main__":
    unittest.main()
