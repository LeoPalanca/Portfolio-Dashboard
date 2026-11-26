"""Balance checkpoints reconcile each account; unexplained gaps become calculated rows."""

from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import ExitStack
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from openpyxl import Workbook

import app
from src.portfolio_dashboard.imports import intesa_pdf
from src.portfolio_dashboard.movements.personal import PersonalLedger
from src.portfolio_dashboard.movements.reconcile import AccountMovement, BalanceCheckpoint, reconcile_balances, uncovered_days
from test_intesa_pdf import statement_text


def point(day: date, balance: str, account: str = "Bank", origin: str = "statement") -> BalanceCheckpoint:
    return BalanceCheckpoint(account, day, Decimal(balance), origin)


def moved(day: date, amount: str, account: str = "Bank") -> AccountMovement:
    return AccountMovement(account, day, Decimal(amount))


class ReconcileBalancesTest(unittest.TestCase):
    def test_a_gap_between_two_balances_becomes_one_calculated_row(self) -> None:
        result = reconcile_balances(
            [moved(date(2023, 1, 31), "-1"), moved(date(2023, 2, 10), "-30"), moved(date(2023, 2, 20), "5")],
            [point(date(2023, 1, 31), "100"), point(date(2023, 2, 28), "50")],
        )
        (interval,) = result["intervals"]
        (row,) = result["rows"]

        # The movement on the opening day is already inside the opening balance.
        self.assertEqual((interval["recorded"], interval["movements"], interval["gap"]), (Decimal(-25), 2, Decimal(-25)))
        self.assertEqual(
            (row["date"], row["source"], row["flow_kind"], row["category"], row["amount_eur"], row["calculated"]),
            (date(2023, 2, 28), "Bank", "calculated_expense", "Calculated expenses", Decimal(25), True),
        )
        self.assertEqual(result["accounts"][0]["status"], "reconciled")
        self.assertEqual(result["accounts"][0]["message"], "Reconciled to 2023-02-28")

    def test_income_gaps_tolerance_and_repeated_statement_balances(self) -> None:
        result = reconcile_balances(
            [moved(date(2023, 2, 5), "10"), moved(date(2023, 3, 5), "10")],
            [
                point(date(2023, 1, 31), "0"),
                point(date(2023, 2, 28), "10.60"),
                # The next statement opens with the previous one's closing balance.
                point(date(2023, 2, 28), "10.60"),
                point(date(2023, 3, 31), "120"),
            ],
        )
        self.assertEqual([item["calculated"] for item in result["intervals"]], [None, "income"])
        self.assertEqual(result["rows"][0]["flow_kind"], "calculated_income")
        self.assertEqual(result["rows"][0]["amount_eur"], Decimal("99.40"))
        self.assertEqual(result["accounts"][0]["calculated_income"], Decimal("99.40"))

    def test_disagreeing_same_day_balances_show_up_as_a_gap(self) -> None:
        result = reconcile_balances([], [point(date(2023, 3, 31), "80"), point(date(2023, 3, 31), "75", origin="manual")])
        self.assertEqual([(item["gap"], item["origin"]) for item in result["intervals"]], [(Decimal(-5), "statement→manual")])

    def test_accounts_without_two_balances_are_not_reconciled_and_get_no_rows(self) -> None:
        result = reconcile_balances(
            [moved(date(2023, 1, 5), "-20", "Trade Republic"), moved(date(2023, 1, 5), "-20", "Card")],
            [point(date(2023, 2, 1), "300", "trade republic")],
        )
        statuses = {item["account"]: (item["status"], item["message"]) for item in result["accounts"]}
        self.assertEqual(statuses["Card"], ("no_balance", "No balance yet — enter the current balance to reconcile"))
        self.assertEqual(statuses["Trade Republic"][0], "single_balance")
        self.assertEqual((result["rows"], result["intervals"]), ([], []))


class CoverageTest(unittest.TestCase):
    """A gap is unrecorded money only where imported statements cover every day of it."""

    checkpoints = [point(date(2023, 1, 31), "100"), point(date(2023, 3, 31), "40")]
    movements = [moved(date(2023, 2, 10), "-30")]

    def reconcile(self, *ranges: tuple[date, date]) -> dict:
        return reconcile_balances(self.movements, self.checkpoints, coverage={"bank": list(ranges)})

    def test_an_uncovered_interval_gives_no_row(self) -> None:
        result = self.reconcile()
        (interval,) = result["intervals"]
        self.assertEqual(result["rows"], [])
        self.assertEqual((interval["status"], interval["missing"]), ("missing_statements", [(date(2023, 2, 1), date(2023, 3, 31))]))
        self.assertEqual(interval["gap"], Decimal(-30))
        self.assertIn("statements missing for 1 period", result["accounts"][0]["message"])

    def test_a_fully_covered_interval_gives_a_row(self) -> None:
        # Two files that together cover February and March, overlapping by a few days.
        result = self.reconcile((date(2023, 2, 1), date(2023, 3, 3)), (date(2023, 3, 1), date(2023, 4, 30)))
        self.assertEqual([(row["flow_kind"], row["amount_eur"]) for row in result["rows"]], [("calculated_expense", Decimal(30))])
        self.assertEqual(result["intervals"][0]["missing"], [])

    def test_a_partly_covered_interval_gives_no_row_and_lists_the_gap(self) -> None:
        result = self.reconcile((date(2023, 2, 1), date(2023, 2, 28)), (date(2023, 3, 20), date(2023, 3, 25)))
        self.assertEqual(result["rows"], [])
        self.assertEqual(
            result["intervals"][0]["missing"],
            [(date(2023, 3, 1), date(2023, 3, 19)), (date(2023, 3, 26), date(2023, 3, 31))],
        )

    def test_uncovered_days(self) -> None:
        self.assertEqual(uncovered_days(date(2023, 1, 1), date(2023, 1, 1), []), [])
        self.assertEqual(uncovered_days(date(2023, 1, 1), date(2023, 1, 3), [(date(2022, 1, 1), date(2023, 1, 2))]), [(date(2023, 1, 3), date(2023, 1, 3))])


class RevolutBalanceTest(unittest.TestCase):
    def test_the_regular_statement_gives_opening_and_closing_balances_that_reconcile(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "account-statement.csv"
            path.write_text(
                "Tipo,Prodotto,Data di inizio,Data di completamento,Descrizione,Importo,Costo,Valuta,State,Saldo\n"
                "Ricarica,Attuale,2023-02-01 09:00:00,2023-02-01 09:00:00,Top-up,100.00,0.00,EUR,COMPLETATO,150.00\n"
                "Pagamento con carta,Attuale,2023-02-03 09:00:00,2023-02-03 09:00:00,Shop,-10.00,1.00,EUR,COMPLETATO,139.00\n"
                "Pagamento,Attuale,2023-02-04 09:00:00,2023-02-04 09:00:00,A EUR Conto deposito senza vincoli,-20.00,0.00,EUR,COMPLETATO,119.00\n"
                "Pagamento,Deposito,2023-02-04 09:00:00,2023-02-04 09:00:00,Da EUR Conto corrente,20.00,0.00,EUR,COMPLETATO,320.00\n"
                "Pagamento con carta,Attuale,2023-02-05 09:00:00,2023-02-05 09:00:00,Cafe,-3.00,0.00,CHF,COMPLETATO,7.00\n"
                "Pagamento con carta,Attuale,2023-02-06 09:00:00,,Pending,-9.00,0.00,EUR,IN SOSPESO,\n",
                encoding="utf-8",
            )
            movements = app.parse_statement_movements("revolut", path)
        checkpoints = [(row["occurred_on"], row["amount"]) for row in movements if row["event_type"] == "balance_checkpoint"]
        flows = [
            AccountMovement("Revolut", row["occurred_on"].date(), Decimal(str(row["amount"])))
            for row in movements
            if row["event_type"] == "cash_flow" and row["currency"] == "EUR"
        ]
        # Current account 50 + savings 300 before the first row; 119 + 320 after the last.
        self.assertEqual(checkpoints, [(date(2023, 1, 31), Decimal("350.00")), (date(2023, 2, 4), Decimal("439.00"))])
        result = reconcile_balances(flows, [point(day, str(value), "Revolut") for day, value in checkpoints])
        self.assertEqual([(item["gap"], item["calculated"]) for item in result["intervals"]], [(Decimal(0), None)])


class ManualBalanceTest(unittest.TestCase):
    def test_current_balances_are_dated_today_editable_and_removable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            ledger = PersonalLedger(Path(temporary) / "ledger.sqlite3")
            first = ledger.save_account_balance("owner", {"account": "Bank", "amount": "120.50"}, {"Bank"})
            same_day = ledger.save_account_balance("owner", {"account": "Bank", "amount": "-12.00"}, {"Bank"})
            ledger.save_account_balance("owner", {"account": "Bank", "id": first, "amount": "99.99"}, {"Bank"})
            entries = ledger.account_balances("owner")
            with self.assertRaisesRegex(ValueError, "imported account"):
                ledger.save_account_balance("owner", {"account": "Other", "amount": "1"}, {"Bank"})
            with self.assertRaisesRegex(ValueError, "two decimal places"):
                ledger.save_account_balance("owner", {"account": "Bank", "amount": "1.234"}, {"Bank"})
            ledger.delete_account_balance("owner", first)
            remaining = ledger.account_balances("owner")
            with self.assertRaisesRegex(ValueError, "not found"):
                ledger.delete_account_balance("owner", first)

        self.assertEqual(first, same_day)
        self.assertEqual(entries, [{"id": first, "account": "Bank", "date": date.today(), "balance": Decimal("99.99")}])
        self.assertEqual(remaining, [])


class OverlappingExportCoverageTest(unittest.TestCase):
    def test_a_later_export_covers_what_it_lists_even_where_an_earlier_one_stored_the_rows(self) -> None:
        january = [(date(2023, 1, day), "Example market", "Generi alimentari e supermercato", -10) for day in (2, 20)]
        february = [*january, (date(2023, 2, 20), "Example market", "Generi alimentari e supermercato", -10)]
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            root = Path(temporary)
            for name, value in (
                ("ROOT_DIR", root / "sources"),
                ("MOVEMENT_DATABASE", root / "private" / "movements.sqlite3"),
                ("_movement_store", None),
                ("_legacy_imported_portfolios", {app.PRIMARY_PORTFOLIO_ID}),
                ("read_expense_category_rules", lambda *args: []),
            ):
                stack.enter_context(patch.object(app, name, value))
            for name, rows in (("january.xlsx", january), ("february.xlsx", february)):
                (root / name).write_bytes(stated_export(rows, None))
                app.import_statement_path(root / name, original_name=name, requested_source="intesa")
            ledger = PersonalLedger(app.MOVEMENT_DATABASE)
            for day, balance in ((date(2023, 1, 1), "100"), (date(2023, 2, 20), "50")):
                ledger.save_account_balance(app.PRIMARY_PORTFOLIO_ID, {"account": "Intesa", "amount": balance, "date": day.isoformat()}, {"Intesa"})
            stored = [row["occurred_on"] for row in app.get_movement_store().movements() if row["import_id"] == 2]
            (interval,) = app.balance_reconciliation(app.PRIMARY_PORTFOLIO_ID)["intervals"]

        # The second export stored only its new row, yet it covers 2 January to 20 February.
        self.assertEqual(stored, ["2023-02-20"])
        self.assertEqual((interval["missing"], interval["calculated"], interval["gap_eur"]), ([], "expense", -20.0))


def stated_export(rows: list[tuple], period: tuple[str, str] | None) -> bytes:
    """An Intesa XLSX export; above the table it states the period it lists."""

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Lista Operazione"
    if period:
        sheet.append((None, "Data inizio periodo:", period[0]))
        sheet.append((None, "Data fine periodo:", period[1]))
    sheet.append(("Data", "Operazione", "Dettagli", "Conto o carta", "Contabilizzazione", "Categoria ", "Valuta", "Importo"))
    for day, merchant, category, amount in rows:
        sheet.append((day, merchant, f"Payment to {merchant}", "Conto", "SI", category, "EUR", amount))
    output = io.BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


class ReconciliationPayloadTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.stack = ExitStack()
        for target, name, value in (
            (app, "ROOT_DIR", self.root / "sources"),
            (app, "MOVEMENT_DATABASE", self.root / "private" / "movements.sqlite3"),
            (app, "_movement_store", None),
            (app, "_legacy_imported_portfolios", {app.PRIMARY_PORTFOLIO_ID}),
            (app, "SELF_TRANSFER_NAMES", ("account owner",)),
            (app, "read_expense_category_rules", lambda *args: []),
            (app, "pdf_text", lambda path: statement_text()),
            (intesa_pdf, "pdf_layout_text", lambda path: statement_text()),
        ):
            self.stack.enter_context(patch.object(target, name, value))
        self.client = self.stack.enter_context(app.app.test_client())
        for name, content in (
            ("q1.pdf", b"%PDF q1"),
            ("export.xlsx", stated_export([(date(2023, 4, 2), "Example streaming", "Tempo libero varie", -9.99)], ("01/04/2023", "30/04/2023"))),
        ):
            path = self.root / name
            path.write_bytes(content)
            app.import_statement_path(path, original_name=name)
        # A Trade Republic top-up funded by the Intesa transfer to the owner's own name.
        top_up = app.normalize_cash_flow_movement(
            {"date": date(2023, 1, 16), "cash_change": Decimal(200), "contrib_change": Decimal(200), "description": "Top-up"},
            "Trade Republic",
        )
        app.get_movement_store().record_import(
            sha256="c" * 64, source_kind="trade_republic", original_name="tr.csv", stored_path="sources/tr.csv",
            parser_version=app.IMPORT_PARSER_VERSION, movements=[top_up],
        )

    def tearDown(self) -> None:
        self.stack.close()
        self.temporary.cleanup()

    def post(self, **body) -> dict:
        response = self.client.post("/api/expenses", json=body)
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def test_a_dated_balance_inside_imported_coverage_turns_the_gap_into_calculated_expenses(self) -> None:
        before = self.client.get("/api/expenses").get_json()
        after = self.post(action="save_balance", account="Intesa", amount="3000.00", date="2023-04-30")
        intesa = next(item for item in after["reconciliation"]["accounts"] if item["account"] == "Intesa")
        calculated = [row for row in after["rows"] if row["calculated"]]
        statuses = {item["account"]: item["status"] for item in before["reconciliation"]["accounts"]}
        coverage = sorted((account, first.isoformat(), last.isoformat()) for _id, account, first, last in app.get_movement_store().coverage())

        self.assertEqual(statuses, {"Intesa": "reconciled", "Trade Republic": "no_balance"})
        self.assertEqual([item["calculated"] for item in before["reconciliation"]["intervals"]], [None])
        # The statement covers its quarter; the export the period it states, not just its
        # one row. (The Trade Republic row was stored without a file: its row is its span.)
        self.assertEqual(coverage, [("Intesa", "2023-01-01", "2023-03-31"), ("Intesa", "2023-04-01", "2023-04-30")])
        self.assertEqual(intesa["reconciled_to"], "2023-04-30")
        # 3 209.50 at the statement's end, -9.99 recorded since, 3 000.00 on 30 April.
        self.assertEqual(
            [(row["date"], row["source"], row["flow_kind"], row["category"], row["amount_eur"], row["movement_id"]) for row in calculated],
            [("2023-04-30", "Intesa", "calculated_expense", "Calculated expenses", 199.51, None)],
        )
        self.assertEqual(round(after["summary"]["spend_eur"] - before["summary"]["spend_eur"], 2), 199.51)
        self.assertEqual(after["summary"]["calculated_expenses_eur"], 199.51)
        self.assertIn("Calculated expenses", {row["category"] for row in after["by_category"]})

        # Today's balance: nothing imported covers May onwards, so that period is a data gap.
        today = self.post(action="save_balance", account="Intesa", amount="2500.00")
        latest = today["reconciliation"]["intervals"][-1]
        self.assertEqual((latest["status"], latest["calculated"]), ("missing_statements", None))
        self.assertEqual(latest["missing"], [{"from": "2023-05-01", "to": date.today().isoformat()}])
        self.assertEqual(len([row for row in today["rows"] if row["calculated"]]), 1)

        removed = self.post(action="delete_balance", id=intesa["manual_balances"][0]["id"])
        self.assertEqual([row for row in removed["rows"] if row["calculated"]], [])

    def test_balances_are_not_dated_in_the_future(self) -> None:
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        response = self.client.post("/api/expenses", json={"action": "save_balance", "account": "Intesa", "amount": "1", "date": tomorrow})
        self.assertEqual(response.status_code, 400)
        self.assertIn("future", response.get_json()["error"])

    def test_unknown_accounts_are_refused(self) -> None:
        response = self.client.post("/api/expenses", json={"action": "save_balance", "account": "Elsewhere", "amount": "1"})
        self.assertEqual(response.status_code, 400)

    def test_top_ups_unmatched_by_an_imported_transfer_are_reported(self) -> None:
        summary = self.client.get("/api/expenses").get_json()["summary"]
        rows = self.client.get("/api/expenses").get_json()["rows"]
        internal = sorted((row["source_label"], row["flow_kind"]) for row in rows if row["internal"])

        # The Trade Republic top-up pairs with the Intesa transfer to the owner; the
        # Intesa receipt from the owner's own name came from an account not imported.
        self.assertEqual(internal, [("Intesa", "personal_transfer"), ("Trade Republic", "top_up")])
        self.assertEqual((summary["topups_eur"], summary["unmatched_topups_eur"]), (220.0, 20.0))
        self.assertEqual(summary["income_eur"], 2500.0)


if __name__ == "__main__":
    unittest.main()
