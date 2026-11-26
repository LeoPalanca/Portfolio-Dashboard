"""Money coming into Revolut, classified by what it is (synthetic consolidated statement rows).

Every name, payer and amount below is made up. "Example Owner" plays the account
holder, configured as a ``self_transfer_names`` entry where a test says so.
"""

from __future__ import annotations

import csv
import io
import tempfile
import unittest
from collections import Counter
from contextlib import ExitStack
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from openpyxl import Workbook

import app
from src.portfolio_dashboard.domain.models import ExpenseRule
from test_revolut_sub_accounts import EUR_HEADER, eur, isolated_app, no_network, table, upload

OWNER = app.PRIMARY_PORTFOLIO_ID
SELF_NAMES = ("example owner",)
TOP_UPS = (
    ("Ricarica di Apple Pay con *0000", "Ricarica", "200,00"),
    ("Pagamento da EXAMPLE OWNER", "Ricarica", "50,00"),
    ("Pagamento da OWNER EXAMPLE", "Ricarica", "40,00"),
    ("Pagamento da TRADE REPUBLIC BANK GMBH", "Ricarica", "35,00"),
    ("Deposito", "Ricarica", "100,00"),
)
CLASSIFIED = (
    ("Pagamento da UNIVERSITA DI ESEMPIO", "Ricarica", "900,00", "income", "Income"),
    ("Pagamento da EXAMPLE EMPLOYER S.R.L.", "Ricarica", "1200,00", "income", "Income"),
    ("Pagamento da PAYPAL EXAMPLE S.A.R.L.", "Ricarica", "25,00", "credit", "Money received"),
    ("Pagamento da SATISPAY EXAMPLE OWNER", "Ricarica", "15,00", "credit", "Money received"),
    ("Pagamento da MANGOPAY EXAMPLE", "Ricarica", "11,00", "credit", "Money received"),
    ("Pagamento da ORANGEBUDDIES EXAMPLE B.V.", "Ricarica", "3,00", "credit", "Money received"),
    ("Pagamento da ROSSI MARIA", "Ricarica", "20,00", "credit", "Money received"),
    ("Pagamento da parte di Example Friend", "Altri", "12,00", "credit", "Money received"),
    ("Example Store", "Rimborso", "9,00", "refund", "Refunds"),
    ("Shops cashback for Example Store", "Cashback", "1,00", "credit", "Credits"),
    ("Ricompensa per la campagna di esempio", "Interessi o rendimenti", "10,00", "credit", "Credits"),
)


def statement(rows: list[tuple[str, str, str]]) -> str:
    """A consolidated statement with one personal EUR account and a consistent running balance."""

    running = Decimal(0)
    lines = []
    for index, (description, category, amount) in enumerate(rows, start=1):
        running += Decimal(amount.replace(",", "."))
        lines.append(eur(f"{index} mag 2026", description, category, amount, f"{running:.2f}".replace(".", ",")))
    content = [["Conti correnti Riepiloghi"], [], ["Conti correnti Estratti conto delle operazioni"], []]
    content += table("Conto personale (EUR)", EUR_HEADER, lines)
    output = io.StringIO()
    csv.writer(output).writerows(content)
    return output.getvalue()


def every_inflow() -> str:
    return statement([*TOP_UPS, *((description, category, amount) for description, category, amount, *_ in CLASSIFIED)])


def intesa_transfer_out(day: date, amount: int) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Lista Operazione"
    sheet.append(("Intesa Sanpaolo",))
    sheet.append(("Data", "Operazione", "Dettagli", "Conto o carta", "Contabilizzazione", "Categoria ", "Valuta", "Importo"))
    sheet.append((day, "Bonifico a favore di Example Owner", "Bonifico disposto", "Conto", "SI", "Bonifici in uscita", "EUR", -amount))
    output = io.BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


class RevolutInflowParsingTest(unittest.TestCase):
    def parse(self, text: str) -> list[dict]:
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            stack.enter_context(patch.object(app, "fetch_history", no_network))
            stack.enter_context(patch.object(app, "SELF_TRANSFER_NAMES", SELF_NAMES))
            stack.enter_context(patch.object(app, "read_expense_category_rules", return_value=[]))
            path = Path(temporary) / "statement.csv"
            path.write_text(text, encoding="utf-8")
            return app.parse_statement_movements("revolut", path, OWNER)

    def test_each_kind_of_money_in(self) -> None:
        rows = [row for row in self.parse(every_inflow()) if row["event_type"] not in {"cash_flow", "balance_checkpoint"}]
        found = Counter((row["description"], row["event_type"], row["metadata"]["category"]) for row in rows)
        self.assertEqual(found, Counter({(description, kind, category): 1 for description, _c, _a, kind, category in CLASSIFIED}))
        # Top-ups have no statement row: their cash row is the top-up the ledger shows.
        self.assertFalse({description for description, *_ in TOP_UPS} & {row["description"] for row in rows})

    def test_payers(self) -> None:
        with patch.object(app, "SELF_TRANSFER_NAMES", SELF_NAMES):
            kinds = {
                payer: app.revolut_payer_classification(payer)[0]
                for payer in (
                    "EXAMPLE OWNER", "Owner Example", "INTESA SANPAOLO", "Fineco Bank", "EXAMPLE SCHOOL",
                    "Comune di Esempio", "Example Consulting Ltd", "Società Esempio S.p.A.", "PAYPAL EXAMPLE S.A R.L.",
                    "SATISPAY EXAMPLE S.A.", "Example Partner", "BIANCHI LUCA",
                )
            }
        self.assertEqual(kinds, {
            "EXAMPLE OWNER": "", "Owner Example": "", "INTESA SANPAOLO": "", "Fineco Bank": "",
            "EXAMPLE SCHOOL": "income", "Comune di Esempio": "income", "Example Consulting Ltd": "income",
            "Società Esempio S.p.A.": "income", "PAYPAL EXAMPLE S.A R.L.": "credit", "SATISPAY EXAMPLE S.A.": "credit",
            "Example Partner": "credit", "BIANCHI LUCA": "credit",
        })

    def test_a_category_rule_overrides_the_payer_guess(self) -> None:
        rules = [
            ExpenseRule(1, "revolut", "description", "contains", "ROSSI MARIA", "Income", "Lessons", ""),
            ExpenseRule(2, "revolut", "description", "contains", "UNIVERSITA DI ESEMPIO", "Money received", "", ""),
        ]
        with patch.object(app, "read_expense_category_rules", return_value=rules):
            text = every_inflow()
            with tempfile.TemporaryDirectory() as temporary, patch.object(app, "fetch_history", no_network):
                path = Path(temporary) / "statement.csv"
                path.write_text(text, encoding="utf-8")
                rows = app.parse_statement_movements("revolut", path, OWNER)
        kinds = {row["description"]: (row["event_type"], row["metadata"]["category"]) for row in rows
                 if row["event_type"] not in {"cash_flow", "balance_checkpoint"}}
        self.assertEqual(kinds["Pagamento da ROSSI MARIA"], ("income", "Income"))
        self.assertEqual(kinds["Pagamento da UNIVERSITA DI ESEMPIO"], ("credit", "Money received"))


class RevolutInflowLedgerTest(unittest.TestCase):
    def ledger(self, revolut: str, intesa: bytes | None = None, self_names: tuple[str, ...] = SELF_NAMES) -> dict:
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            isolated_app(stack, Path(temporary))
            stack.enter_context(patch.object(app, "SELF_TRANSFER_NAMES", self_names))
            client = stack.enter_context(app.app.test_client())
            self.assertEqual(upload(client, OWNER, revolut).get_json()["status"], "imported")
            if intesa is not None:
                response = client.post(
                    "/api/imports",
                    data={"portfolio_id": OWNER, "file": (io.BytesIO(intesa), "account_operations.xlsx")},
                    content_type="multipart/form-data",
                )
                self.assertEqual(response.get_json()["status"], "imported", response.get_json())
            return client.get(f"/api/expenses?person={OWNER}").get_json()

    def test_top_ups_stay_top_ups_and_the_rest_is_income_money_received_or_refunds(self) -> None:
        payload = self.ledger(every_inflow())
        kinds = {row["description"]: row["flow_kind"] for row in payload["rows"]}
        self.assertEqual({description: kinds[description] for description, *_ in TOP_UPS}, dict.fromkeys((d for d, *_ in TOP_UPS), "top_up"))
        self.assertEqual({description: kinds[description] for description, *_ in CLASSIFIED},
                         {description: kind for description, _c, _a, kind, _cat in CLASSIFIED})
        summary = payload["summary"]
        self.assertEqual(summary["income_eur"], 2100.0)
        self.assertEqual(summary["credits_eur"], 97.0)
        self.assertEqual(summary["spend_eur"], -9.0)  # the refund, with nothing spent
        self.assertEqual(summary["topups_eur"], 425.0)
        self.assertEqual(summary["calculated_income_eur"] + summary["calculated_expenses_eur"], 0)

    def test_a_payment_another_imported_account_sent_is_an_internal_top_up(self) -> None:
        # Without a configured name the payer reads as a person (money received) until
        # Intesa's outgoing transfer of the same amount pairs with it; with the name it
        # is a top-up from the start. Either way both legs end up internal.
        revolut = statement([("Pagamento da EXAMPLE OWNER", "Ricarica", "50,00"), ("Pagamento da ROSSI MARIA", "Ricarica", "20,00")])
        for self_names in ((), SELF_NAMES):
            with self.subTest(self_names=self_names):
                payload = self.ledger(revolut, intesa_transfer_out(date(2026, 5, 1), 50), self_names)
                legs = {(row["source_label"], row["flow_kind"], row["category"], row["internal"]) for row in payload["rows"] if row["amount_eur"] == 50.0}
                self.assertEqual(len(legs), 2)
                self.assertIn(("Revolut", "top_up", "Top-ups", True), legs)
                self.assertIn(("Intesa", "personal_transfer", True), {(source, kind, internal) for source, kind, _category, internal in legs})
                friend = next(row for row in payload["rows"] if row["description"] == "Pagamento da ROSSI MARIA")
                self.assertEqual((friend["flow_kind"], friend["internal"]), ("credit", False))


if __name__ == "__main__":
    unittest.main()
