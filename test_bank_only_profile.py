"""A profile with bank data only: no trades and no holdings snapshot (a household joint account)."""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import app
from test_revolut_sub_accounts import HOUSEHOLD, household_profiles, isolated_app, statement_text, upload


def no_prices(*_args, **_kwargs):
    return {"prices": {}, "history": {}}


class BankOnlyProfileTest(unittest.TestCase):
    def setUp(self) -> None:
        app._DASHBOARD_MEMORY_CACHE.clear()

    def test_the_dashboard_loads_with_empty_investment_sections(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            root = Path(temporary)
            isolated_app(stack, root)
            stack.enter_context(patch.object(app, "fetch_history", no_prices))
            stack.enter_context(patch.object(app, "refresh_price_cache", lambda *args, **kwargs: None))
            stack.enter_context(patch.object(app, "DASHBOARD_CACHE_DIR", root / "cache"))
            client = stack.enter_context(app.app.test_client())
            self.assertEqual(upload(client, HOUSEHOLD, statement_text()).get_json()["status"], "imported")
            payload = app._build_dashboard_payload(person=HOUSEHOLD)
            expenses = client.get(f"/api/expenses?person={HOUSEHOLD}").get_json()

        self.assertEqual((payload["person"], payload["person_name"]), (HOUSEHOLD, "Household"))
        self.assertEqual((payload["positions"], payload["trade_count"], payload["valuation_series"]), ([], 0, []))
        self.assertEqual(payload["totals"]["market_value"], 0)
        self.assertEqual(payload["dividends"]["rows"], [])
        json.dumps(payload, default=str)  # the payload is served as JSON
        self.assertEqual(expenses["summary"]["spend_eur"], 45.0)
        self.assertEqual([item["status"] for item in expenses["reconciliation"]["accounts"]], ["reconciled"])

    def test_the_person_selector_lists_it_and_the_rankings_skip_it(self) -> None:
        profiles = household_profiles()
        family = app.SETTINGS.model_copy(update={"portfolios": profiles}).family_portfolios
        with ExitStack() as stack:
            stack.enter_context(patch.dict(app.SETTINGS.portfolios, profiles))
            stack.enter_context(patch.object(app, "FAMILY_PORTFOLIOS", family))
            stack.enter_context(patch.object(app, "read_dashboard_cache", return_value=None))
            stack.enter_context(patch.object(app, "queue_dashboard_refresh", return_value={"status": "running"}))
            client = stack.enter_context(app.app.test_client())
            page = client.get("/").get_data(as_text=True)
            rankings = client.get("/api/rankings").get_json()

        self.assertEqual(family, {})
        self.assertIn(f'data-person="{HOUSEHOLD}"', page)
        config = json.loads(re.search(r'<script[^>]*id="app-config"[^>]*>(.*?)</script>', page, re.DOTALL).group(1))
        self.assertEqual(config["portfolioFeatures"][HOUSEHOLD], [app.REVOLUT_JOINT_ACCOUNT_FEATURE])
        self.assertNotIn(HOUSEHOLD, [row["person"] for row in rankings["rankings"]])


if __name__ == "__main__":
    unittest.main()
