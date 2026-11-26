"""A bank cash deposit is income unless the cash ledger's balances account for it (synthetic Intesa rows).

The workbook (see test_cash_ledger_bank_cash) has a salary of 1000 on 5 January, an
ATM withdrawal of 100 on 12 January and a cash deposit ("Versamento Contanti") of 60
on 15 January.
"""

from __future__ import annotations

import io
import tempfile
import unittest
from collections.abc import Callable
from contextlib import ExitStack
from datetime import date
from pathlib import Path
from unittest.mock import patch

import app
from src.portfolio_dashboard.movements.personal import PersonalLedger
from test_cash_ledger_bank_cash import intesa_workbook

OWNER = app.PRIMARY_PORTFOLIO_ID
DEPOSIT = "Versamento Contanti"


def spend(ledger: PersonalLedger, categories: list[str], day: str, amount: str) -> None:
    ledger.save_cash(OWNER, {"date": day, "amount": amount, "flow_kind": "spend", "merchant": "Example kiosk", "category": "Groceries"}, categories)


def balance(ledger: PersonalLedger, day: str, amount: str) -> None:
    ledger.save_account_balance(OWNER, {"account": "Cash", "amount": amount, "date": day}, {"Cash"})


class CashDepositIncomeTest(unittest.TestCase):
    def payload(self, keep: Callable[[PersonalLedger, list[str]], None], override: str | None = None) -> dict:
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            root = Path(temporary)
            database = root / "private" / "movements.sqlite3"
            for name, value in (
                ("ROOT_DIR", root / "sources"),
                ("MOVEMENT_DATABASE", database),
                ("_movement_store", None),
                ("_legacy_imported_portfolios", {OWNER}),
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
            ledger = PersonalLedger(database)
            keep(ledger, ledger.categories(OWNER, app.EXPENSE_CATEGORIES))
            if override:
                deposit = next(row for row in app.read_ledger_expenses(OWNER) if row["merchant"] == DEPOSIT)
                ledger.set_category(OWNER, deposit, "Income", "Lessons")
                ledger.set_direction(OWNER, deposit["movement_id"], override)
            return app.personal_expenses_payload(OWNER)

    @staticmethod
    def deposit(payload: dict) -> dict:
        return next(row for row in payload["rows"] if row["merchant"] == DEPOSIT)

    @staticmethod
    def cash_intervals(payload: dict) -> list[dict]:
        return [item for item in payload["reconciliation"]["intervals"] if item["account"] == "Cash"]

    def assert_income(self, payload: dict) -> None:
        deposit = self.deposit(payload)
        self.assertEqual((deposit["flow_kind"], deposit["internal"]), ("income", False))
        self.assertEqual(payload["summary"]["income_eur"], 1060.0)
        self.assertEqual(payload["summary"]["calculated_income_eur"], 0.0)

    def test_a_cash_ledger_with_only_expenses_leaves_the_deposit_income(self) -> None:
        def keep(ledger: PersonalLedger, categories: list[str]) -> None:
            spend(ledger, categories, "2025-01-10", "30.00")
            spend(ledger, categories, "2025-01-14", "12.50")

        payload = self.payload(keep)
        self.assert_income(payload)
        self.assertEqual(self.cash_intervals(payload), [])

    def test_an_opening_balance_alone_brackets_nothing(self) -> None:
        def keep(ledger: PersonalLedger, categories: list[str]) -> None:
            ledger.set_opening_balance(OWNER, "20.00")
            spend(ledger, categories, "2025-01-10", "30.00")

        self.assert_income(self.payload(keep))

    def test_balances_that_end_before_the_deposit_leave_it_income(self) -> None:
        def keep(ledger: PersonalLedger, categories: list[str]) -> None:
            spend(ledger, categories, "2025-01-03", "30.00")
            balance(ledger, "2025-01-02", "50.00")
            balance(ledger, "2025-01-14", "120.00")  # 50 − 30 + 100 withdrawn

        payload = self.payload(keep)
        self.assert_income(payload)
        cash = self.cash_intervals(payload)
        self.assertEqual([(item["status"], item["gap_eur"]) for item in cash], [("reconciled", 0.0)])

    def test_two_balances_spanning_the_deposit_make_it_a_transfer_from_cash(self) -> None:
        # 20 opening − 30 spent + 100 withdrawn − 60 paid in = 30; the wallet held 80,
        # so 50 of cash came in unrecorded (lessons paid in cash, say).
        def with_opening(ledger: PersonalLedger, categories: list[str]) -> None:
            ledger.set_opening_balance(OWNER, "20.00")
            spend(ledger, categories, "2025-01-10", "30.00")
            balance(ledger, "2025-01-20", "80.00")

        def with_two_balances(ledger: PersonalLedger, categories: list[str]) -> None:
            spend(ledger, categories, "2025-01-10", "30.00")
            balance(ledger, "2025-01-09", "20.00")
            balance(ledger, "2025-01-20", "80.00")

        for keep in (with_opening, with_two_balances):
            with self.subTest(checkpoints=keep.__name__):
                payload = self.payload(keep)
                deposit = self.deposit(payload)
                self.assertEqual((deposit["flow_kind"], deposit["category"], deposit["internal"]), ("top_up", "Top-ups", True))
                [cash] = self.cash_intervals(payload)
                self.assertEqual((cash["status"], cash["recorded_eur"], cash["gap_eur"]), ("calculated", 10.0, 50.0))
                calculated = [row for row in payload["rows"] if row["flow_kind"] == "calculated_income"]
                self.assertEqual([(row["source"], row["amount_eur"]) for row in calculated], [("Cash", 50.0)])
                # The salary and the cash that came in, once each; the deposit is neither.
                self.assertEqual(payload["summary"]["calculated_income_eur"], 50.0)
                self.assertEqual(payload["summary"]["income_eur"], 1050.0)
                self.assertEqual(payload["summary"]["unmatched_topups_eur"], 0.0)

    def test_a_withdrawal_inside_the_balances_and_a_deposit_after_them_count_once(self) -> None:
        # The ATM cash moves Cash (20 − 30 + 100 = 90); the later deposit is income
        # and is not taken out of Cash, so nothing is calculated for it.
        def keep(ledger: PersonalLedger, categories: list[str]) -> None:
            ledger.set_opening_balance(OWNER, "20.00")
            spend(ledger, categories, "2025-01-10", "30.00")
            balance(ledger, "2025-01-13", "90.00")

        payload = self.payload(keep)
        self.assert_income(payload)
        [cash] = self.cash_intervals(payload)
        self.assertEqual((cash["status"], cash["recorded_eur"], cash["gap_eur"]), ("reconciled", 70.0, 0.0))
        self.assertEqual(payload["summary"]["calculated_expenses_eur"], 0.0)

    def test_a_deposit_the_user_calls_income_stays_in_the_bank_side_only(self) -> None:
        # Paid in straight from a lesson, never in the wallet: 20 − 30 + 100 = 90.
        def keep(ledger: PersonalLedger, categories: list[str]) -> None:
            ledger.set_opening_balance(OWNER, "20.00")
            spend(ledger, categories, "2025-01-10", "30.00")
            balance(ledger, "2025-01-20", "90.00")

        payload = self.payload(keep, override="income")
        self.assert_income(payload)
        self.assertEqual(self.deposit(payload)["category"], "Income")
        [cash] = self.cash_intervals(payload)
        self.assertEqual((cash["status"], cash["recorded_eur"], cash["gap_eur"]), ("reconciled", 70.0, 0.0))

    def test_the_span_needs_two_checkpoint_days(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            ledger = PersonalLedger(Path(temporary) / "ledger.sqlite3")
            categories = ledger.categories(OWNER, app.EXPENSE_CATEGORIES)
            self.assertIsNone(app.cash_ledger_span(ledger, OWNER, ledger.cash_events(OWNER)))
            ledger.set_opening_balance(OWNER, "20.00")
            spend(ledger, categories, "2025-01-10", "30.00")
            self.assertIsNone(app.cash_ledger_span(ledger, OWNER, ledger.cash_events(OWNER)))
            balance(ledger, "2025-01-20", "0.00")
            span = app.cash_ledger_span(ledger, OWNER, ledger.cash_events(OWNER))
        self.assertEqual(span, (date(2025, 1, 9), date(2025, 1, 20)))
        self.assertFalse(app.cash_ledger_covers(span, date(2025, 1, 9)))
        self.assertTrue(app.cash_ledger_covers(span, date(2025, 1, 10)))
        self.assertTrue(app.cash_ledger_covers(span, date(2025, 1, 20)))
        self.assertFalse(app.cash_ledger_covers(span, date(2025, 1, 21)))


if __name__ == "__main__":
    unittest.main()
