"""Money the holder moves into the Revolut joint account is "Family account" spending (synthetic rows).

The joint account belongs to the household profile (see test_revolut_sub_accounts);
the holder's own profile sees only its side of each transfer.
"""

from __future__ import annotations

import csv
import io
import tempfile
import unittest
from contextlib import ExitStack
from datetime import date
from pathlib import Path

from openpyxl import Workbook

import app
from test_revolut_sub_accounts import EUR_HEADER, HOUSEHOLD, eur, isolated_app, summary, table, upload

OWNER = app.PRIMARY_PORTFOLIO_ID
TO_JOINT = "Pagamento a favore di EXAMPLE OWNER & EXAMPLE PARTNER"
FROM_JOINT = "Pagamento da parte di EXAMPLE OWNER & EXAMPLE PARTNER"


def statement() -> str:
    rows: list[list[str]] = [["Conti correnti Riepiloghi"], []]
    rows += summary("Conto personale (EUR)")
    rows += summary("Conto cointestato (EUR)", "Cointestato", holders=("Example Owner", "Example Partner"))
    rows += [["Conti correnti Estratti conto delle operazioni"], []]
    rows += table("Conto personale (EUR)", EUR_HEADER, [
        eur("2 mag 2026", "Ricarica di Apple Pay con *0000", "Ricarica", "300,00", "300,00"),
        eur("4 mag 2026", TO_JOINT, "Altri", "-100,00", "200,00"),
        eur("9 mag 2026", FROM_JOINT, "Altri", "30,00", "230,00"),
    ])
    rows += table("Conto cointestato (EUR)", EUR_HEADER, [
        eur("4 mag 2026", "Pagamento da parte di EXAMPLE OWNER", "Altri", "100,00", "100,00"),
        eur("6 mag 2026", "Example Grocer", "Esercente", "-45,00", "55,00"),
        eur("9 mag 2026", "Pagamento a favore di EXAMPLE OWNER", "Altri", "-30,00", "25,00"),
    ])
    output = io.StringIO()
    csv.writer(output).writerows(rows)
    return output.getvalue()


def intesa_income(day: date, amount: int) -> bytes:
    """An Intesa credit of the same amount days later, which a transfer out would pair with."""

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Lista Operazione"
    sheet.append(("Intesa Sanpaolo",))
    sheet.append(("Data", "Operazione", "Dettagli", "Conto o carta", "Contabilizzazione", "Categoria ", "Valuta", "Importo"))
    sheet.append((day, "Example employer", "Salary", "Conto", "SI", "Stipendi e pensioni", "EUR", amount))
    output = io.BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


class FamilyAccountTest(unittest.TestCase):
    def setUp(self) -> None:
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        temporary = self.stack.enter_context(tempfile.TemporaryDirectory())
        isolated_app(self.stack, Path(temporary))
        self.client = self.stack.enter_context(app.app.test_client())
        for owner in (OWNER, HOUSEHOLD):
            self.assertEqual(upload(self.client, owner, statement()).get_json()["status"], "imported")
        response = self.client.post(
            "/api/imports",
            data={"portfolio_id": OWNER, "file": (io.BytesIO(intesa_income(date(2026, 5, 6), 100)), "account_operations.xlsx")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.get_json()["status"], "imported", response.get_json())

    def expenses(self, owner: str) -> dict:
        return self.client.get(f"/api/expenses?person={owner}").get_json()

    def correct(self, row: dict, category: str, flow_kind: str, learn: bool = False) -> dict:
        response = self.client.post("/api/expenses", json={
            "action": "category", "portfolio_id": OWNER, "movement_id": row["movement_id"],
            "category": category, "subcategory": "", "flow_kind": flow_kind, "learn": learn,
        })
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    @staticmethod
    def family(payload: dict) -> dict[str, dict]:
        return {row["description"]: row for row in payload["rows"] if row["merchant"] == "Family account"}

    def test_money_into_the_joint_account_is_spending_and_money_back_refunds_it(self) -> None:
        own = self.expenses(OWNER)
        family = self.family(own)
        self.assertEqual(
            {description: (row["flow_kind"], row["category"], row["amount_eur"], row["internal"]) for description, row in family.items()},
            {TO_JOINT: ("spend", "Family account", 100.0, False), FROM_JOINT: ("refund", "Family account", 30.0, False)},
        )
        categories = {item["category"]: item["amount_eur"] for item in own["by_category"]}
        self.assertEqual(categories["Family account"], 70.0)
        self.assertEqual(own["summary"]["spend_eur"], 70.0)
        self.assertIn("Family account", own["categories"])
        # Nothing pairs the spending with Intesa's credit of the same amount two days later.
        salary = next(row for row in own["rows"] if row["merchant"] == "Example employer")
        self.assertEqual((salary["flow_kind"], salary["internal"]), ("income", False))
        self.assertFalse([row for row in own["rows"] if row["flow_kind"] == "transfer_out"])

    def test_the_household_side_is_unchanged(self) -> None:
        household = self.expenses(HOUSEHOLD)
        self.assertFalse(self.family(household))
        flows = sorted((row["merchant"], row["flow_kind"], row["amount_eur"]) for row in household["rows"])
        self.assertEqual(flows, [
            ("EXAMPLE OWNER", "top_up", 100.0), ("EXAMPLE OWNER", "transfer_out", 30.0), ("Example Grocer", "spend", 45.0),
        ])
        self.assertEqual(household["summary"]["spend_eur"], 45.0)

    def test_the_user_can_recategorise_or_retype_it(self) -> None:
        family = self.family(self.expenses(OWNER))
        # Changing a refund's category keeps it a refund.
        payload = self.correct(family[FROM_JOINT], "Groceries", "refund")
        refund = self.family(payload)[FROM_JOINT]
        self.assertEqual((refund["flow_kind"], refund["category"]), ("refund", "Groceries"))
        # A learned rule for the merchant recategorises the spending.
        payload = self.correct(family[TO_JOINT], "Housing & Utilities", "spend", learn=True)
        self.assertEqual(self.family(payload)[TO_JOINT]["category"], "Housing & Utilities")
        self.assertIn(("revolut", "family account", "spend"), {(rule["source"], rule["merchant"], rule["flow_kind"]) for rule in payload["rules"]})
        # An explicit type correction turns it back into a transfer.
        payload = self.correct(family[TO_JOINT], "Personal Transfers", "personal_transfer")
        self.assertEqual(self.family(payload)[TO_JOINT]["flow_kind"], "personal_transfer")


if __name__ == "__main__":
    unittest.main()
