import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app


class PersonalLedgerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        for patcher in (
            patch.object(app, "MOVEMENT_DATABASE", Path(self.temp.name) / "ledger.sqlite3"),
            patch.object(app, "_movement_store", None),
            patch.object(app, "ensure_legacy_statements_imported"),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = app.app.test_client()
        self.owner = app.PRIMARY_PORTFOLIO_ID
        self.import_rows("first", [self.row("2026-01-01"), self.row("2026-01-02")])

    def row(self, day, merchant="City Market", kind="spend"):
        return {
            "occurred_on": day,
            "event_type": kind,
            "account": "bank",
            "amount": "10",
            "currency": "EUR",
            "description": merchant,
            "metadata": {"merchant": merchant, "category": "Uncategorized", "amount_eur": "10"},
        }

    def import_rows(self, sha, rows, owner=None):
        return app.get_movement_store().record_import(
            sha256=sha,
            source_kind="bank",
            original_name=sha,
            stored_path="",
            parser_version="test",
            movements=rows,
            portfolio_id=owner or self.owner,
        )

    def get(self):
        response = self.client.get("/api/expenses")
        self.assertEqual(response.status_code, 200)
        return response.get_json()

    def post(self, **payload):
        response = self.client.post("/api/expenses", json=payload)
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def test_create_and_use_custom_category(self):
        result = self.post(action="add_category", name="Professional learning")
        self.assertIn("Professional learning", result["categories"])
        row = result["rows"][0]
        result = self.post(action="category", movement_id=row["movement_id"], category="Professional learning")
        self.assertTrue(any(r["category"] == "Professional learning" for r in result["rows"]))
        result = self.post(action="save_cash", date="2026-01-01", amount="5", flow_kind="spend",
                           merchant="Bookshop", category="Professional learning")
        self.assertEqual(result["cash_rows"][0]["category"], "Professional learning")

    def test_rules_apply_past_and_future_without_changing_manual_overrides(self):
        ids = [row["movement_id"] for row in self.get()["rows"]]
        self.post(action="category", movement_id=ids[0], category="Shopping", learn=False)
        self.post(action="category", movement_id=ids[1], category="Groceries", learn=True)
        self.import_rows("next", [self.row("2026-01-03", "  CITY   MARKET ")])
        self.assertEqual([row["category"] for row in self.get()["rows"]], ["Groceries", "Shopping", "Groceries"])
        original = app.get_movement_store().movements(self.owner)
        self.assertTrue(all(row["metadata"]["category"] == "Uncategorized" for row in original))

    def test_future_only_rule_does_not_reclassify_existing_rows(self):
        rows = self.get()["rows"]
        self.post(
            action="category", movement_id=rows[0]["movement_id"], category="Groceries", learn=True, include_past=False
        )
        self.import_rows("next", [self.row("2026-01-03")])
        self.assertEqual([row["category"] for row in self.get()["rows"]], ["Groceries", "Groceries", "Uncategorized"])

    def test_rule_does_not_cross_source_direction_or_portfolio(self):
        self.post(action="category", movement_id=self.get()["rows"][0]["movement_id"], category="Groceries", learn=True)
        self.import_rows("income", [self.row("2026-01-04", kind="income")])
        self.import_rows("other", [self.row("2026-01-05")], owner="other")
        self.assertEqual(self.get()["rows"][0]["category"], "Uncategorized")
        events = [
            {
                "movement_id": 99,
                "source": "other bank",
                "merchant": "city market",
                "flow_kind": "spend",
                "category": "Uncategorized",
            }
        ]
        self.assertEqual(
            app.PersonalLedger(app.MOVEMENT_DATABASE).classify(self.owner, events)[0]["category"], "Uncategorized"
        )

    def test_remove_rule_keeps_individual_override(self):
        result = self.post(
            action="category", movement_id=self.get()["rows"][0]["movement_id"], category="Groceries", learn=True
        )
        rule = result["rules"][0]
        result = self.post(action="delete_rule", **rule)
        self.assertEqual([row["category"] for row in result["rows"]], ["Groceries", "Uncategorized"])

    def test_cash_balance_crud_transfers_and_investment_separation(self):
        self.assertIsNone(self.get()["cash_ledger"]["balance"])
        self.post(action="opening_balance", amount="100")
        base = {"action": "save_cash", "date": "2026-01-01", "merchant": "Cash", "category": "Shopping"}
        self.post(**base, amount="20", flow_kind="income")
        self.post(**base, amount="50", flow_kind="transfer_in")
        result = self.post(**base, amount="15", flow_kind="spend")
        self.assertEqual(result["cash_ledger"]["balance"], 155)
        self.assertEqual(result["summary"]["income_eur"], 20)
        cash_id = next(row["cash_id"] for row in result["cash_rows"] if row["flow_kind"] == "spend")
        result = self.post(**base, id=cash_id, amount="25", flow_kind="spend")
        self.assertEqual(result["cash_ledger"]["balance"], 145)
        result = self.post(action="delete_cash", id=cash_id)
        self.assertEqual(result["cash_ledger"]["balance"], 170)
        self.assertEqual(len(app.get_movement_store().movements(self.owner)), 2)
        self.assertFalse(app.get_movement_store().movements(self.owner, ("trade", "cash_flow")))

    def test_category_does_not_change_transaction_direction(self):
        result = self.post(action="category", movement_id=self.get()["rows"][0]["movement_id"], category="Income")
        self.assertEqual(app.expense_row_kind(result["rows"][0]), "spend")
        self.assertEqual(
            app.expense_row_kind({"flow_kind": "cash_withdrawal", "category": "Cash Withdrawals"}), "transfers"
        )

    def test_rule_and_override_survive_reimport_and_exports_match(self):
        identifier = self.get()["rows"][0]["movement_id"]
        self.post(action="category", movement_id=identifier, category="Dining", learn=True)
        record = app.get_movement_store().import_by_hash("first", self.owner)
        app.get_movement_store().enrich_import(
            record, parser_version="new", movements=[self.row("2026-01-01"), self.row("2026-01-02")]
        )
        rows = self.get()["rows"]
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row["category"] == "Dining" for row in rows))
        exported = app.expense_category_export_rows(
            rows + [{"flow_kind": "personal_transfer", "category": "Personal Transfers", "amount_eur": 500}]
        )
        self.assertEqual(exported, [{"category": "Dining", "amount_eur": 20, "count": 2, "share_pct": 100}])

    def test_explicit_direction_correction_survives_reimport_without_affecting_other_rows(self):
        identifier = self.get()["rows"][0]["movement_id"]
        result = self.post(
            action="category", movement_id=identifier, category="Credits", flow_kind="credit", learn=True
        )
        self.assertEqual(result["rules"], [])
        record = app.get_movement_store().import_by_hash("first", self.owner)
        app.get_movement_store().enrich_import(
            record, parser_version="new", movements=[self.row("2026-01-01"), self.row("2026-01-02")]
        )
        result = self.get()
        self.assertEqual([row["flow_kind"] for row in result["rows"]], ["credit", "spend"])
        self.assertEqual(result["summary"]["credits_eur"], 10)

    def test_invalid_cash_and_cross_site_writes_are_rejected(self):
        for value in ("NaN", "Infinity", "-1", "0", "1.001", "1e100"):
            response = self.client.post(
                "/api/expenses",
                json={
                    "action": "save_cash",
                    "date": "2026-01-01",
                    "amount": value,
                    "merchant": "Cash",
                    "category": "Shopping",
                },
            )
            self.assertEqual(response.status_code, 400, value)
        self.assertEqual(
            self.client.post(
                "/api/expenses",
                json={"action": "opening_balance", "amount": "1"},
                headers={"Origin": "https://evil.invalid"},
            ).status_code,
            403,
        )
        self.assertEqual(self.client.post("/api/expenses", json=[1]).status_code, 400)
        self.assertEqual(
            self.client.post("/api/expenses", json={"action": "delete_cash", "id": "other-owner-entry"}).status_code,
            400,
        )


if __name__ == "__main__":
    unittest.main()
