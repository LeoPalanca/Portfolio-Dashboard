"""Bank movements of physical cash move the manual cash ledger (synthetic Intesa rows)."""

from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import ExitStack
from datetime import date
from pathlib import Path
from unittest.mock import patch

from openpyxl import Workbook

import app
from src.portfolio_dashboard.movements.personal import PersonalLedger


def intesa_workbook() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Lista Operazione"
    sheet.append(("Intesa Sanpaolo",))
    sheet.append(("Data", "Operazione", "Dettagli", "Conto o carta", "Contabilizzazione", "Categoria ", "Valuta", "Importo"))
    for day, operation, details, category, amount in [
        (date(2025, 1, 5), "Example employer", "Salary", "Stipendi e pensioni", 1000),
        (date(2025, 1, 12), "Prelievo contanti", "Prelievo ATM Example Branch", "Prelievi", -100),
        (date(2025, 1, 15), "Versamento Contanti", "Versamento contanti presso Example Branch", "Versamenti", 60),
    ]:
        sheet.append((day, operation, details, "Conto", "SI", category, "EUR", amount))
    output = io.BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


class CashLedgerBankCashTest(unittest.TestCase):
    def run_case(self, keep_cash_ledger: bool, entered_transfer: bool = False) -> dict:
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            root = Path(temporary)
            database = root / "private" / "movements.sqlite3"
            for name, value in (
                ("ROOT_DIR", root / "sources"),
                ("MOVEMENT_DATABASE", database),
                ("_movement_store", None),
                ("_legacy_imported_portfolios", {app.PRIMARY_PORTFOLIO_ID}),
            ):
                stack.enter_context(patch.object(app, name, value))
            stack.enter_context(patch.object(app, "read_expense_category_rules", return_value=[]))
            client = stack.enter_context(app.app.test_client())
            response = client.post(
                "/api/imports",
                data={"file": (io.BytesIO(intesa_workbook()), "account_operations.xlsx")},
                content_type="multipart/form-data",
            )
            self.assertEqual(response.get_json()["status"], "imported", response.get_json())
            owner = app.PRIMARY_PORTFOLIO_ID
            if keep_cash_ledger:
                ledger = PersonalLedger(database)
                categories = ledger.categories(owner, app.EXPENSE_CATEGORIES)
                ledger.set_opening_balance(owner, "20.00")
                ledger.save_cash(owner, {"date": "2025-01-10", "amount": "30.00", "flow_kind": "spend", "merchant": "Example kiosk", "category": "Groceries"}, categories)
                if entered_transfer:
                    ledger.save_cash(owner, {"date": "2025-01-13", "amount": "100.00", "flow_kind": "transfer_in", "merchant": "ATM", "category": "Cash Withdrawals"}, categories)
                # 20 opening − 30 spent + 100 withdrawn − 60 paid in at the bank.
                ledger.save_account_balance(owner, {"account": "Cash", "amount": "30.00", "date": "2025-01-20"}, {"Cash"})
            return app.personal_expenses_payload(owner)

    def test_withdrawals_fill_the_cash_ledger_and_deposits_empty_it(self) -> None:
        payload = self.run_case(keep_cash_ledger=True)
        cash = next(item for item in payload["reconciliation"]["intervals"] if item["account"] == "Cash")
        self.assertEqual((cash["status"], cash["gap_eur"], cash["recorded_eur"]), ("reconciled", 0.0, 10.0))
        self.assertEqual(payload["summary"]["calculated_income_eur"], 0.0)
        deposit = next(row for row in payload["rows"] if row["merchant"] == "Versamento Contanti")
        # A transfer from Cash, matched by the ledger: neither income nor an unmatched top-up.
        self.assertEqual((deposit["flow_kind"], deposit["internal"]), ("top_up", True))
        self.assertEqual(payload["summary"]["income_eur"], 1000.0)
        self.assertEqual(payload["summary"]["unmatched_topups_eur"], 0.0)

    def test_a_cash_transfer_entered_for_the_same_withdrawal_is_not_counted_twice(self) -> None:
        payload = self.run_case(keep_cash_ledger=True, entered_transfer=True)
        cash = next(item for item in payload["reconciliation"]["intervals"] if item["account"] == "Cash")
        self.assertEqual((cash["status"], cash["gap_eur"]), ("reconciled", 0.0))

    def test_without_a_cash_ledger_a_cash_deposit_keeps_its_classification(self) -> None:
        payload = self.run_case(keep_cash_ledger=False)
        deposit = next(row for row in payload["rows"] if row["merchant"] == "Versamento Contanti")
        self.assertEqual(deposit["flow_kind"], "income")
        self.assertEqual(payload["summary"]["income_eur"], 1060.0)
        self.assertNotIn("Cash", [item["account"] for item in payload["reconciliation"]["intervals"]])

    def test_cash_deposit_wording(self) -> None:
        def event(text: str, amount: str = "50") -> dict:
            return {"merchant": text, "description": "", "source": "intesa", "native_amount": amount}

        self.assertTrue(app.is_cash_deposit(event("VERSAMENTO CONTANTI SU ATM")))
        self.assertTrue(app.is_cash_deposit(event("Versamento di contanti")))
        self.assertFalse(app.is_cash_deposit(event("Versamento assegno")))
        self.assertFalse(app.is_cash_deposit(event("Versamento contanti", "-50")))


if __name__ == "__main__":
    unittest.main()
