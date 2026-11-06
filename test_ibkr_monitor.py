"""Synthetic affordability and request-boundary tests. No live account access."""

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from flask import Flask

from src.portfolio_dashboard.ibkr_monitor import WATCHLIST, affordability, create_ibkr_blueprint
from scripts.ibkr_cash_bridge import broker_cash, saved_connection


class AffordabilityTests(unittest.TestCase):
    def test_saved_connection_is_private_and_requires_an_explicit_account(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "account_config.json"
            path.write_text(json.dumps({"account": "U0001111", "endpoint": "gateway-live"}))
            self.assertEqual(saved_connection(path), (4001, "1111", "U0001111"))
            path.write_text(json.dumps({"endpoint": "gateway-live"}))
            with self.assertRaises(ValueError):
                saved_connection(path)
            path.unlink()
            with self.assertRaises(OSError):
                saved_connection(path)

    def test_refresh_uses_saved_connection_without_account_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            app = Flask(__name__, template_folder="templates")
            app.register_blueprint(create_ibkr_blueprint(Path(folder)))
            client = app.test_client()
            page = client.get("/ibkr").text
            import re

            token = re.search(r'name="ibkr-token" content="([^"]+)"', page).group(1)
            self.assertNotIn('id="ibkr-account"', page)
            self.assertNotIn('id="ibkr-port"', page)
            with patch("src.portfolio_dashboard.ibkr_monitor.threading.Thread") as thread:
                response = client.post("/api/ibkr/refresh", json={}, headers={"X-IBKR-Token": token})
                self.assertEqual(response.status_code, 202)
                self.assertEqual(thread.call_args.kwargs["args"], (None, None))

    def test_full_cash_without_position_cap_and_fees_reserved(self):
        rows = affordability(100, 1.1, [{"symbol": "TEST", "price_usd": 55, "price_time": 100}], 101)
        self.assertEqual(rows[0]["whole_shares_with_cash"], 1)
        self.assertEqual(rows[0]["estimated_one_share_cost_usd"], 56)
        self.assertNotIn("within_proposed_10pct_cap", rows[0])

    def test_unknown_stale_and_future_prices_cannot_be_affordable(self):
        for stamp in (None, 1, 900000):
            row = affordability(100, 1, [{"price_usd": 10, "price_time": stamp}], 800000)[0]
            self.assertIsNone(row["whole_shares_with_cash"])
        self.assertIsNone(
            affordability(100, None, [{"price_usd": 10, "price_time": 100}], 101)[0]["whole_shares_with_cash"]
        )

    def test_no_borrowing_for_negative_cash(self):
        self.assertEqual(
            affordability(-20, 1, [{"price_usd": 10, "price_time": 100}], 101)[0]["whole_shares_with_cash"], 0
        )

    def test_exactly_100_distinct_securities(self):
        self.assertEqual(len(WATCHLIST), 100)
        self.assertEqual(len(set(WATCHLIST)), 100)

    def test_broker_scope_excludes_margin_and_other_accounts(self):
        ib = MagicMock()
        ib.connectAsync = AsyncMock(side_effect=ConnectionError("positions request timed out"))
        ib.client.connectAsync = AsyncMock()
        ib.client.getAccounts.return_value = ["U0001111", "U0002222"]
        ib.accountSummaryAsync = AsyncMock(
            return_value=[
                SimpleNamespace(account="U0001111", tag=tag, value=value, currency="EUR")
                for tag, value in [("NetLiquidation", "1000"), ("TotalCashValue", "100"), ("AvailableFunds", "500")]
            ]
            + [SimpleNamespace(account="U0002222", tag="TotalCashValue", value="99999", currency="EUR")]
        )
        with patch("ib_async.IB", return_value=ib):
            result = asyncio.run(broker_cash(4001, "1111"))
        self.assertEqual(result["cash_budget_base"], 100)
        self.assertEqual(result["account_masked"], "•••1111")
        ib.connectAsync.assert_not_called()
        ib.reqPositionsAsync.assert_not_called()
        ib.reqOpenOrdersAsync.assert_not_called()
        ib.placeOrder.assert_not_called()
        ib.client.connectAsync.assert_awaited_once_with("127.0.0.1", 4001, clientId=71, timeout=12)
        ib.disconnect.assert_called_once()

    def test_ambiguous_account_selection_fails_and_disconnects(self):
        ib = MagicMock()
        ib.client.connectAsync = AsyncMock()
        ib.client.getAccounts.return_value = ["U0001111", "D0001111"]
        with patch("ib_async.IB", return_value=ib), self.assertRaises(ValueError):
            asyncio.run(broker_cash(4001, "1111"))
        ib.accountSummaryAsync.assert_not_called()
        ib.disconnect.assert_called_once()

    def test_api_rejects_cross_origin_missing_token_and_invalid_port(self):
        with tempfile.TemporaryDirectory() as folder:
            app = Flask(__name__, template_folder="templates")
            app.register_blueprint(create_ibkr_blueprint(Path(folder)))
            client = app.test_client()
            page = client.get("/ibkr").text
            import re

            token = re.search(r'name="ibkr-token" content="([^"]+)"', page).group(1)
            body = {"account_suffix": "1111", "port": 4001}
            self.assertEqual(client.post("/api/ibkr/refresh", json=body).status_code, 403)
            headers = {"X-IBKR-Token": token, "Origin": "https://other.example"}
            self.assertEqual(client.post("/api/ibkr/refresh", json=body, headers=headers).status_code, 403)
            self.assertEqual(
                client.post(
                    "/api/ibkr/refresh", json={**body, "port": 22}, headers={"X-IBKR-Token": token}
                ).status_code,
                400,
            )
            with patch("src.portfolio_dashboard.ibkr_monitor.threading.Thread") as thread:
                self.assertEqual(
                    client.post("/api/ibkr/refresh", json=body, headers={"X-IBKR-Token": token}).status_code, 202
                )
                thread.return_value.start.assert_called_once()
                self.assertEqual(
                    client.post("/api/ibkr/refresh", json=body, headers={"X-IBKR-Token": token}).status_code, 409
                )
            self.assertFalse(client.get("/api/ibkr").json["execution_enabled"])

    def test_cached_snapshot_is_explicitly_stale(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "ibkr_monitor.json").write_text(json.dumps({"captured_at": "2020-01-01T00:00:00+00:00"}))
            app = Flask(__name__)
            app.register_blueprint(create_ibkr_blueprint(Path(folder)))
            response = app.test_client().get("/api/ibkr")
            self.assertTrue(response.json["snapshot_stale"])


if __name__ == "__main__":
    unittest.main()
