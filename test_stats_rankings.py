"""Family rankings, risk statistics and allocation labels (synthetic numbers only)."""

from __future__ import annotations

import math
import statistics
import unittest
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

import app


def point(day: str, value: float, contributions: float) -> dict[str, float | str]:
    return {
        "date": day,
        "market_value": value,
        "net_contributions": contributions,
        "profit": value - contributions,
        "total_market_value": value,
        "total_net_contributions": contributions,
        "total_profit": value - contributions,
        "priced_positions": 1,
        "unpriced_positions": 0,
    }


def trade(asset: str, day: date, quantity: str, amount: str, broker: str = "Example") -> app.Trade:
    return app.Trade(
        asset=asset, isin="", broker=broker, action="Acquisto", currency_hint="EUR", cash_currency="EUR",
        date=day, price=Decimal(amount) / Decimal(quantity), quantity=Decimal(quantity), quantity_diff=Decimal(quantity),
        total_spend=-Decimal(amount), fees=Decimal(0), tax=Decimal(0), grand_total=-Decimal(amount),
        grand_total_present=True, source="test",
    )


def business_days(start: date, count: int) -> list[date]:
    days: list[date] = []
    day = start
    while len(days) < count:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days


class RankingReturnTest(unittest.TestCase):
    """The same fund (+8.9% to November, +1% in December) held three ways."""

    def test_flows_do_not_change_the_rank_of_the_same_fund(self) -> None:
        no_flows = [point("2025-12-31", 10000, 10000), point("2026-11-30", 10890, 10000),
                    point("2026-12-01", 10890, 10000), point("2026-12-31", 10998.9, 10000)]
        late_inflow = [point("2025-12-31", 10000, 10000), point("2026-11-30", 10890, 10000),
                       point("2026-12-01", 100890, 100000), point("2026-12-31", 101898.9, 100000)]
        early_outflow = [point("2025-12-31", 100000, 100000), point("2026-01-02", 10000, 10000),
                         point("2026-11-30", 10890, 10000), point("2026-12-31", 10998.9, 10000)]
        results = [
            app.portfolio_ranking_returns(series, "2025-12-31", "2025-12-31") for series in (no_flows, late_inflow, early_outflow)
        ]
        for result in results:
            for window in ("start", "common", "ytd"):
                self.assertAlmostEqual(result["price"][window], 9.99, places=2, msg=(window, result))
                self.assertAlmostEqual(result["total"][window], 9.99, places=2)

    def test_windows_start_from_the_last_point_on_or_before_their_date(self) -> None:
        # Month-end points: the first point in the new year is 31 January.
        series = [point("2025-11-30", 1000, 1000), point("2025-12-31", 1000, 1000),
                  point("2026-01-31", 1100, 1000), point("2026-02-28", 1100, 1000)]
        self.assertEqual(app.ranking_anchor_index(series, "2025-12-31"), 1)
        self.assertEqual(app.ranking_anchor_index(series, "2026-02-15"), 2)
        # History starting after the date is measured from its own first point.
        self.assertEqual(app.ranking_anchor_index(series, "2020-01-01"), 0)
        returns = app.portfolio_ranking_returns(series, "2026-02-15", "2025-12-31")
        self.assertEqual(returns["price"]["ytd"], 10.0)  # January is not skipped
        self.assertEqual(returns["price"]["common"], 0.0)

    def test_ranking_matches_the_dashboard_time_weighted_return(self) -> None:
        series = [point("2026-01-01", 1000, 1000), point("2026-03-31", 1200, 1100),
                  point("2026-06-30", 900, 1100), point("2026-09-30", 1500, 1400)]
        expected = app.time_weighted_return_pct(series, "market_value", "net_contributions", "profit")
        self.assertEqual(app.portfolio_ranking_returns(series, None, "2025-12-31")["price"]["start"], round(expected, 2))

    def test_reconstructed_family_history_is_flagged(self) -> None:
        primary_path = app.dashboard_cache_path(app.PRIMARY_PORTFOLIO_ID, "stock", app.DEFAULT_PROXY_MODE, "all", "off")
        series = [point("2026-01-01", 100, 100), point("2026-02-01", 110, 100)]

        def cached(path, *args, **kwargs):
            if path == primary_path:
                return {"valuation_series": series, "trade_source": "ledger"}
            if "family" in str(path):
                return {"valuation_series": series, "history_reconstructed": True}
            return {"valuation_series": series, "trade_source": "Other CSV snapshot"}

        with (
            patch.object(app, "FAMILY_PORTFOLIOS", {"family": {"name": "Family"}, "older": {"name": "Older"}}),
            patch.object(app, "read_dashboard_cache", side_effect=cached),
        ):
            response = app.app.test_client().get("/api/rankings")
        self.assertEqual(response.status_code, 200)
        rows = {row["person"]: row for row in response.get_json()["rankings"]}
        self.assertFalse(rows[app.PRIMARY_PORTFOLIO_ID]["reconstructed"])
        self.assertTrue(rows["family"]["reconstructed"])
        self.assertIn("hindsight", rows["family"]["reconstructed_note"])
        # Snapshots saved before the flag existed are recognised by their source.
        self.assertTrue(rows["older"]["reconstructed"])
        self.assertEqual(response.get_json()["method"], "time_weighted")


class ReturnStatisticsTest(unittest.TestCase):
    def test_standard_deviation_is_the_sample_estimate(self) -> None:
        values = [0.01, -0.01, 0.02, 0.0] * 20
        summary = app.daily_return_summary(values)
        self.assertAlmostEqual(summary["daily_variance_pct"], statistics.variance(values) * 10000)
        self.assertAlmostEqual(summary["daily_volatility_pct"], statistics.stdev(values) * 100)
        self.assertAlmostEqual(summary["annualized_volatility_pct"], statistics.stdev(values) * math.sqrt(252) * 100)

    def test_small_samples_have_no_annualised_figures(self) -> None:
        week = [0.003, 0.001, 0.002, 0.0025, 0.0015]
        summary = app.daily_return_summary(week, [value - 0.0001 for value in week])
        self.assertTrue(summary["sample_too_small"])
        self.assertIsNone(summary["annualized_volatility_pct"])
        self.assertIsNone(summary["sharpe_ratio"])
        # Non-annualised figures stay.
        self.assertAlmostEqual(summary["mean_daily_return_pct"], 0.2)
        self.assertAlmostEqual(summary["best_daily_return_pct"], 0.3)
        self.assertAlmostEqual(summary["worst_daily_return_pct"], 0.1)
        self.assertIsNotNone(summary["daily_volatility_pct"])

        enough = app.daily_return_summary(week * 12, [value - 0.0001 for value in week * 12])
        self.assertFalse(enough["sample_too_small"])
        self.assertIsNotNone(enough["annualized_volatility_pct"])
        self.assertIsNotNone(enough["sharpe_ratio"])

    def test_sharpe_uses_xeon_excess_returns_on_the_same_days(self) -> None:
        xeon = [0.0001 + 0.00002 * ((index % 5) - 2) for index in range(80)]
        portfolio = [0.001 * (1 if index % 2 else -0.5) for index in range(80)]
        rows = [{"price_return": r, "msci_return": r, "xeon_return": x} for r, x in zip(portfolio, xeon, strict=True)]
        result = app.return_series_statistics(rows, "price_return", 0.03)

        excess = [r - x for r, x in zip(portfolio, xeon, strict=True)]
        expected = statistics.fmean(excess) / statistics.stdev(excess) * math.sqrt(252)
        self.assertEqual(result["risk_free"], {"source": "xeon", "annual_rate": None})
        self.assertAlmostEqual(result["portfolio"]["sharpe_ratio"], expected)
        self.assertAlmostEqual(result["msci"]["sharpe_ratio"], expected)
        fixed = [r - 0.03 / 252 for r in portfolio]
        self.assertNotAlmostEqual(result["portfolio"]["sharpe_ratio"], statistics.fmean(fixed) / statistics.stdev(fixed) * math.sqrt(252))
        # The cash proxy has no Sharpe ratio of its own.
        self.assertIsNone(result["xeon"]["sharpe_ratio"])
        self.assertIsNotNone(result["xeon"]["annualized_volatility_pct"])

    def test_a_day_without_a_new_xeon_quote_earns_no_risk_free_return(self) -> None:
        rows = [{"price_return": 0.001 * (index % 3), "xeon_return": 0.0001} for index in range(80)]
        rows[10]["xeon_return"] = None  # holiday on the XEON exchange
        result = app.return_series_statistics(rows, "price_return", 0.03)
        excess = [row["price_return"] - (row["xeon_return"] or 0.0) for row in rows]
        self.assertEqual(result["risk_free"]["source"], "xeon")
        self.assertAlmostEqual(result["portfolio"]["sharpe_ratio"], statistics.fmean(excess) / statistics.stdev(excess) * math.sqrt(252))

    def test_fixed_rate_only_without_xeon_data(self) -> None:
        portfolio = [0.002 * (1 if index % 3 else -1) for index in range(70)]
        rows = [{"price_return": value, "msci_return": None, "xeon_return": None} for value in portfolio]
        result = app.return_series_statistics(rows, "price_return", 0.0252)
        excess = [value - 0.0001 for value in portfolio]
        self.assertEqual(result["risk_free"], {"source": "fixed", "annual_rate": 0.0252})
        self.assertAlmostEqual(result["portfolio"]["sharpe_ratio"], statistics.fmean(excess) / statistics.stdev(excess) * math.sqrt(252))
        self.assertIsNone(result["msci"]["mean_daily_return_pct"])
        self.assertIsNone(result["msci"]["sharpe_ratio"])


class StatisticsBrokerFilterTest(unittest.TestCase):
    def statistics(self, broker: str) -> dict:
        days = business_days(date.today() - timedelta(days=130), 80)  # noqa: DTZ011 - statistics run up to today
        flat = {day.isoformat(): 100.0 for day in days}
        xeon = {day.isoformat(): 100.0 + index * 0.01 for index, day in enumerate(days)}
        context = {
            "histories": {"AAA": {"status": "priced", "currency": "EUR", "prices": flat}},
            "msci_prices": flat, "msci_symbol": "MSCI", "xeon_prices": xeon,
        }
        trades = [trade("AAA", days[0], "10", "1000", broker="Broker A")]
        other_dividend = app.Dividend(
            broker="Broker B", asset="ZZZ", isin="", date=days[20], amount_eur=Decimal("100"), tax_eur=Decimal(0)
        )
        with (
            patch.object(app, "load_cash_histories", return_value=([], [], [])),
            patch.object(app, "read_portfolio_dividends", return_value=[other_dividend]),
            patch.object(app, "read_cash_interests", return_value=[{"broker": "Broker B", "date": days[30], "net_eur": 50}]),
            patch.object(app, "build_instrument_refs", return_value={"AAA": {"symbol": "AAA"}}),
            patch.object(app, "fetch_history", return_value={"status": "history_error", "prices": {}}),
        ):
            stats = app.calculate_portfolio_statistics(trades, {}, broker=broker, history_context=context)
        self.assertIsNotNone(stats)
        return stats

    def test_one_broker_ignores_another_brokers_dividends_and_interest(self) -> None:
        stats = self.statistics("broker a")
        returns = [row["total_return"] for row in stats["daily_returns"] if row["total_return"] is not None]
        self.assertGreaterEqual(len(returns), app.MIN_ANNUALISED_RETURNS)
        self.assertTrue(all(value == 0 for value in returns), [value for value in returns if value])
        self.assertEqual(stats["total_return"]["portfolio"]["annualized_volatility_pct"], 0.0)
        self.assertEqual(stats["total_return"]["risk_free"]["source"], "xeon")
        self.assertIsNone(stats["total_return"]["xeon"]["sharpe_ratio"])

    def test_all_brokers_still_count_every_dividend(self) -> None:
        stats = self.statistics("all")
        returns = [row["total_return"] for row in stats["daily_returns"] if row["total_return"]]
        self.assertEqual(len(returns), 2)  # the dividend day and the interest day


class AllocationLabelTest(unittest.TestCase):
    def test_source_labels_map_to_a_small_set(self) -> None:
        expected = {
            "Equities": "Equity", "Equity": "Equity", "Single share": "Equity", "ETF underlying": "Equity",
            "Proxy ETF underlying": "Equity", "Berkshire 13F public equity holding": "Equity",
            "Cash": "Cash", "Cash equivalent": "Cash", "Cash Collateral and Margins": "Cash", "Money Market": "Cash",
            "FX": "Cash", "Fixed Income": "Bond", "Crypto": "Crypto", "Gold": "Commodity", "Commodities": "Commodity",
            "Real Estate": "Real estate", "Futures": "Other", "Unclassified": "Other", "": "Other",
        }
        for label, group in expected.items():
            self.assertEqual(app.asset_class_group(label), group, label)

    def test_asset_class_view_uses_groups_and_lists_unpriced_holdings(self) -> None:
        exposures = {
            "isin:FUND00000001": [
                {"holding_name": "Company A", "holding_ticker": "", "weight_pct": Decimal("50"), "sector": "Tech",
                 "geo": "World", "asset_class": "Equities"},
                {"holding_name": "Company B", "holding_ticker": "", "weight_pct": Decimal("30"), "sector": "Tech",
                 "geo": "World", "asset_class": "Proxy ETF underlying"},
                {"holding_name": "Cash line", "holding_ticker": "", "weight_pct": Decimal("10"), "sector": "Cash",
                 "geo": "World", "asset_class": "Cash Collateral and Margins"},
            ],
        }
        positions = [
            {"asset": "Fund", "isin": "FUND00000001", "is_open": True, "market_value_eur": 1000.0},
            {"asset": "New listing", "isin": "NEW000000001", "is_open": True, "market_value_eur": None},
        ]
        with patch.object(app, "read_etf_documents", return_value={}):
            result = app.calculate_distribution(positions, exposures)
        classes = {row["asset_class"]: row["weight_pct"] for row in result["asset_classes"]}
        # The unlisted 10% of the fund follows what the fund mostly holds.
        self.assertEqual(classes, {"Equity": 90.0, "Cash": 10.0})
        # Holding rows keep the issuer's own label.
        self.assertIn("Proxy ETF underlying", {row["asset_class"] for row in result["rows"]})
        self.assertEqual(result["open_assets"], 2)
        self.assertEqual(result["covered_assets"], 1)
        self.assertEqual([(row["asset"], row["status"], row["market_value_eur"]) for row in result["missing"]],
                         [("New listing", "unpriced", None)])

    def test_berkshire_message_states_the_model_split(self) -> None:
        metadata = app.read_berkshire_metadata()
        self.assertEqual(metadata["split_pct"], {"13f": 40.0, "cash": 30.0, "operating": 30.0})
        for text in ("40% SEC 13F-HR", "30% cash", "30% operating businesses"):
            self.assertIn(text, metadata["message"])


if __name__ == "__main__":
    unittest.main()
