"""Bulk CSV imports of account balances and cash spending into the personal ledger."""

from __future__ import annotations

import tempfile
import unittest
from contextlib import ExitStack
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import app
from src.portfolio_dashboard.movements.ledger_csv import (
    BALANCE_COLUMNS,
    parse_ledger_amount,
    parse_ledger_date,
    read_ledger_csv,
)
from src.portfolio_dashboard.movements.personal import PersonalLedger
from test_import_reread import export


class LedgerCsvTest(unittest.TestCase):
    def test_headers_delimiters_and_problem_rows(self) -> None:
        text = "﻿Conto ; Data ; Saldo\nIntesa;01/02/2023;1.234,56\nIntesa;02/02/2023;1;2\n\n"
        rows, problems = read_ledger_csv(text, BALANCE_COLUMNS, {"account", "date", "balance"})
        self.assertEqual(rows, [(2, {"account": "Intesa", "date": "01/02/2023", "balance": "1.234,56", "currency": ""})])
        self.assertEqual([item["line"] for item in problems], [3])
        with self.assertRaisesRegex(ValueError, "missing balance"):
            read_ledger_csv("account,date\nIntesa,2023-01-01\n", BALANCE_COLUMNS, {"account", "date", "balance"})

    def test_dates_and_amounts(self) -> None:
        self.assertEqual(
            [parse_ledger_date(value) for value in ("2023-02-01", "1/2/2023", "01.02.2023", "2023-02-01T10:00:00", "31/02/2023", "")],
            [date(2023, 2, 1)] * 4 + [None, None],
        )
        self.assertEqual(
            [parse_ledger_amount(value) for value in ("1.234,56", "-12,30", "€ 7", "1.234", "text", "")],
            [Decimal("1234.56"), Decimal("-12.30"), Decimal(7), None, None, None],
        )


class LedgerImportTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.stack = ExitStack()
        for name, value in (
            ("ROOT_DIR", self.root / "sources"),
            ("MOVEMENT_DATABASE", self.root / "private" / "movements.sqlite3"),
            ("_movement_store", None),
            ("_legacy_imported_portfolios", {app.PRIMARY_PORTFOLIO_ID}),
            ("SELF_TRANSFER_NAMES", ("account owner",)),
            ("read_expense_category_rules", lambda *args: []),
        ):
            self.stack.enter_context(patch.object(app, name, value))
        self.client = self.stack.enter_context(app.app.test_client())
        bank = self.root / "bank.xlsx"
        bank.write_bytes(export([(date(2023, 5, 2), "Example market", "Generi alimentari e supermercato", -50)]))
        app.import_statement_path(bank, original_name="bank.xlsx", requested_source="intesa")
        top_up = app.normalize_cash_flow_movement(
            {"date": date(2023, 5, 3), "cash_change": Decimal(40), "contrib_change": Decimal(40)}, "Trade Republic"
        )
        app.get_movement_store().record_import(
            sha256="d" * 64, source_kind="trade_republic", original_name="tr.csv", stored_path="sources/tr.csv",
            parser_version=app.IMPORT_PARSER_VERSION, movements=[top_up],
        )

    def tearDown(self) -> None:
        self.stack.close()
        self.temporary.cleanup()

    def post(self, **body) -> dict:
        response = self.client.post("/api/expenses", json=body)
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def test_balances_map_account_labels_report_unknown_ones_and_never_repeat(self) -> None:
        text = (
            "account;date;balance;currency\n"
            " INTESA  ;30/04/2023;3.000,00;EUR\n"
            "trade   republic;2023-04-30;150,00;\n"
            "Portafoglio;2023-04-30;80,00;eur\n"
            "Intesa Sanpaolo;2023-05-31;2.950,00;EUR\n"
            "Revolut;2023-04-30;10,00;EUR\n"
            "Intesa;2023-04-29;10,00;USD\n"
            "Intesa;31/02/2023;1;EUR\n"
        )
        first = self.post(action="import_balances", csv=text)["import_result"]
        again = self.post(action="import_balances", csv=text)["import_result"]
        changed = self.post(action="import_balances", csv="account,date,balance\nintesa,2023-04-30,2999.99\n")["import_result"]
        balances = PersonalLedger(app.MOVEMENT_DATABASE).account_balances(app.PRIMARY_PORTFOLIO_ID)

        self.assertEqual((first["added"], first["updated"], first["unchanged"]), (4, 0, 0))
        # Revolut has no imported movements here: the label is reported, not guessed.
        self.assertEqual(
            [(item["line"], item["reason"]) for item in first["skipped"]],
            [(6, "unknown account 'Revolut'"), (7, "only EUR balances are supported, not USD"), (8, "unreadable date")],
        )
        self.assertEqual((again["added"], again["unchanged"]), (0, 4))
        self.assertEqual((changed["added"], changed["updated"]), (0, 1))
        self.assertEqual(
            sorted((entry["account"], entry["date"].isoformat(), entry["balance"]) for entry in balances),
            [
                ("Cash", "2023-04-30", Decimal("80.00")),
                ("Intesa", "2023-04-30", Decimal("2999.99")),
                ("Intesa", "2023-05-31", Decimal("2950.00")),
                ("Trade Republic", "2023-04-30", Decimal("150.00")),
            ],
        )

    def test_cash_spending_is_imported_once_and_reconciles_the_cash_account(self) -> None:
        text = (
            "date,amount,description,category,subcategory\n"
            "2023-05-02,12.50,Example bakery,dining,\n"
            "2023-05-02,12.50,Example bakery,Dining,\n"
            "2023-05-03,-7.20,Example kiosk,Groceries,snacks\n"
            "2023-05-04,5,Example place,Made-up category,\n"
            "2023-05-04,0,Example place,Groceries,\n"
        )
        first = self.post(action="import_cash", csv=text)["import_result"]
        again = self.post(action="import_cash", csv=text)["import_result"]
        self.post(action="opening_balance", amount="100")
        payload = self.post(action="save_balance", account="Cash", amount="60.00", date="2023-05-05")
        cash_rows = payload["cash_rows"]
        cash = next(item for item in payload["reconciliation"]["accounts"] if item["account"] == "Cash")
        calculated = [row for row in payload["rows"] if row["calculated"]]

        # Two equal purchases on one day stay two entries; re-importing adds neither again.
        self.assertEqual((first["added"], first["unchanged"]), (3, 0))
        self.assertEqual((again["added"], again["unchanged"]), (0, 3))
        self.assertEqual(
            [(item["line"], item["reason"]) for item in first["skipped"]],
            [(5, "unknown category 'Made-up category' (create it first)"), (6, "unreadable amount")],
        )
        self.assertEqual(sorted((row["category"], row["native_amount"]) for row in cash_rows), [("Dining", -12.5), ("Dining", -12.5), ("Groceries", -7.2)])
        self.assertEqual(payload["summary"]["spend_eur"], 50 + 32.2 + 7.8)
        # 100 before the first entry, 32.20 recorded, 60 counted on 5 May: 7.80 spent unrecorded.
        self.assertEqual(cash["status"], "reconciled")
        self.assertEqual([(row["source"], row["flow_kind"], row["amount_eur"], row["date"]) for row in calculated], [("Cash", "calculated_expense", 7.8, "2023-05-05")])


if __name__ == "__main__":
    unittest.main()
