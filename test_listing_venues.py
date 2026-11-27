"""Funds are priced on the listing their broker would sell them on."""

from __future__ import annotations

import os
import unittest
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from unittest.mock import patch

import app
from src.portfolio_dashboard import venues

NOW = 1_800_000_000
FUND = "XX0000000001"
SHARE = "XX0000000002"
LISTINGS = {
    FUND: [("LN", "EXFU", "ETP"), ("GR", "EXFD", "ETP"), ("IM", "EXFM", "ETP")],
    SHARE: [("US", "EXSH", "Common Stock"), ("GR", "EXS", "Common Stock")],
}


@dataclass(frozen=True)
class T:
    asset: str
    isin: str
    broker: str
    date: date
    quantity_diff: Decimal


def buy(broker: str, isin: str = FUND, quantity: str = "1", day: date = date(2026, 1, 5), asset: str = "Example Fund") -> T:
    return T(asset, isin, broker, day, Decimal(quantity))


class Recorder:
    def __init__(self, listings: dict | None = None) -> None:
        self.listings = LISTINGS if listings is None else listings
        self.calls: list[list[str]] = []

    def __call__(self, isins: list[str]) -> dict:
        self.calls.append(isins)
        return {isin: self.listings.get(isin, []) for isin in isins}


def resolve(trades, manual=None, cache=None, priced=lambda symbol: True, fetch=None):
    cache = {} if cache is None else cache
    fetch = fetch or Recorder()
    with patch.dict(os.environ, {"PORTFOLIO_VENUE_LOOKUP": "on"}):
        found = venues.venue_mappings(trades, manual or {}, cache, priced, NOW, fetch=fetch)
    return found, cache, fetch


class VenueRuleTest(unittest.TestCase):
    def test_trade_republic_funds_use_their_xetra_line(self) -> None:
        found, _cache, _fetch = resolve([buy("Trade Republic")])
        self.assertEqual(found["Example Fund"]["ticker"], "EXFD.DE")

    def test_fineco_funds_use_milan_then_xetra(self) -> None:
        self.assertEqual(resolve([buy("Fineco")])[0]["Example Fund"]["ticker"], "EXFM.MI")
        without_milan = Recorder({FUND: [("LN", "EXFU", "ETP"), ("GR", "EXFD", "ETP")]})
        self.assertEqual(resolve([buy("Fineco")], fetch=without_milan)[0]["Example Fund"]["ticker"], "EXFD.DE")
        # A listing Yahoo has no prices for is skipped for the next venue.
        unpriced = resolve([buy("Fineco")], priced=lambda symbol: not symbol.endswith(".MI"))[0]
        self.assertEqual(unpriced["Example Fund"]["ticker"], "EXFD.DE")

    def test_shares_and_brokers_without_a_rule_keep_the_isin_search(self) -> None:
        found, _cache, fetch = resolve([buy("Trade Republic", SHARE, asset="Example Share"), buy("eToro")])
        self.assertEqual(found, {})
        self.assertEqual(fetch.calls, [[SHARE]])  # eToro funds are not looked up at all

    def test_a_manual_ticker_wins_and_a_manual_row_without_one_is_filled(self) -> None:
        pinned = {"Example Fund": {"isin": FUND, "ticker": "EXFU.L", "exchange": ""}}
        found, _cache, fetch = resolve([buy("Trade Republic")], manual=pinned)
        self.assertEqual((found, fetch.calls), ({}, []))
        open_row = {"Example Fund": {"isin": FUND, "ticker": "", "exchange": "", "benchmark_class": "equity"}}
        found = resolve([buy("Trade Republic")], manual=open_row)[0]
        merged = venues.with_venue_mappings(open_row, found)
        self.assertEqual((merged["Example Fund"]["ticker"], merged["Example Fund"]["benchmark_class"]), ("EXFD.DE", "equity"))

    def test_the_broker_holding_the_fund_now_decides(self) -> None:
        trades = [buy("Fineco", quantity="2"), buy("Fineco", quantity="-2", day=date(2026, 3, 1)), buy("Trade Republic", day=date(2026, 2, 1))]
        self.assertEqual(resolve(trades)[0]["Example Fund"]["ticker"], "EXFD.DE")
        closed = [buy("Trade Republic"), buy("Trade Republic", quantity="-1", day=date(2026, 2, 1)),
                  buy("Fineco", day=date(2026, 3, 1)), buy("Fineco", quantity="-1", day=date(2026, 4, 1))]
        self.assertEqual(resolve(closed)[0]["Example Fund"]["ticker"], "EXFM.MI")  # the last broker that held it

    def test_answers_are_cached_and_a_failed_lookup_is_retried_a_day_later(self) -> None:
        _found, cache, _fetch = resolve([buy("Trade Republic")])
        checks: list[str] = []
        again, _cache, second = resolve([buy("Trade Republic")], cache=cache, priced=lambda symbol: checks.append(symbol) or True)
        self.assertEqual((second.calls, checks, again["Example Fund"]["ticker"]), ([], [], "EXFD.DE"))

        failed = {FUND: {"listings": None, "fetched_at": NOW - 3600, "checked": {}}}
        self.assertEqual(resolve([buy("Trade Republic")], cache=failed)[2].calls, [])
        failed[FUND]["fetched_at"] = NOW - venues.RETRY_AFTER
        self.assertEqual(resolve([buy("Trade Republic")], cache=failed)[2].calls, [[FUND]])

    def test_lookups_can_be_turned_off(self) -> None:
        fetch = Recorder()
        with patch.dict(os.environ, {"PORTFOLIO_VENUE_LOOKUP": "off"}):
            self.assertEqual(venues.venue_mappings([buy("Trade Republic")], {}, {}, lambda symbol: True, NOW, fetch=fetch), {})
        self.assertEqual(fetch.calls, [])


class DashboardMappingTest(unittest.TestCase):
    def test_the_dashboard_merges_venues_and_keeps_the_cache(self) -> None:
        trade = app.Trade(
            asset="Example Fund", isin=FUND, broker="Trade Republic", action="Acquisto", currency_hint="EUR", cash_currency="EUR",
            date=date(2026, 1, 5), price=Decimal(10), quantity=Decimal(1), quantity_diff=Decimal(1), total_spend=Decimal(-10),
            fees=Decimal(0), tax=Decimal(0), grand_total=Decimal(-10), grand_total_present=True, source="trade_republic",
        )
        saved: dict = {}
        with (
            patch.dict(os.environ, {"PORTFOLIO_VENUE_LOOKUP": "on"}),
            patch.object(venues, "openfigi_listings", Recorder()),
            patch.object(app, "fetch_history", return_value={"prices": {"2026-01-05": 10.0}}),
            patch.object(app, "load_json", return_value={}),
            patch.object(app, "save_json", side_effect=lambda path, payload: saved.update(payload)),
        ):
            mappings = app.broker_listing_mappings([trade], {})
        self.assertEqual(app.mapping_for("Example Fund", FUND, mappings)["ticker"], "EXFD.DE")
        self.assertIn(FUND, saved)


if __name__ == "__main__":
    unittest.main()
