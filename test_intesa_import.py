from __future__ import annotations

import io
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from openpyxl import Workbook

import app


def bank_statement() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Lista Operazione"
    sheet.append(("Intesa Sanpaolo",))
    sheet.append(("Data", "Operazione", "Dettagli", "Conto o carta", "Contabilizzazione", "Categoria ", "Valuta", "Importo"))
    for merchant, category, amount, state in [
        ("Example employer", "Stipendi e pensioni", 2000, "SI"),
        ("External payer", "Bonifici ricevuti", 120, "SI"),
        ("Account Owner", "Bonifici ricevuti", 500, "SI"),
        ("Example market", "Generi alimentari e supermercato", -50, "SI"),
        ("Own savings account", "Giroconto in entrata", 500, "SI"),
        ("Own savings account", "Giroconto in uscita", -250, "SI"),
        ("Example store refund", "Rimborsi spese e storni", 20, "SI"),
        ("Pending salary", "Stipendi e pensioni", 999, "NO"),
    ]:
        detail = f"Payment to Account Owner from {merchant}"
        sheet.append((date(2026, 6, 1), merchant, detail, "Conto", state, category, "EUR", amount))
    output = io.BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


class IntesaImportTest(unittest.TestCase):
    def test_auto_upload_is_bank_only_archived_and_deduplicated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with (
                patch.object(app, "ROOT_DIR", root / "sources"),
                patch.object(app, "MOVEMENT_DATABASE", root / "movements.sqlite3"),
                patch.object(app, "_movement_store", None),
                patch.object(app, "_legacy_imported_portfolios", {app.PRIMARY_PORTFOLIO_ID}),
                patch.object(app, "SELF_TRANSFER_NAMES", ("account owner",)),
                patch.object(app, "read_expense_category_rules", return_value=[]),
                app.app.test_client() as client,
            ):
                content = bank_statement()
                def upload():
                    return client.post("/api/imports", data={
                        "source": "auto", "portfolio_id": app.PRIMARY_PORTFOLIO_ID,
                        "file": (io.BytesIO(content), "Lista_Operazioni_18062026.xlsx"),
                    }, content_type="multipart/form-data")
                response = upload()
                self.assertEqual(response.status_code, 200, response.get_json())
                self.assertEqual(response.get_json()["source"], "intesa")
                self.assertEqual(response.get_json()["movements"], 6)
                self.assertEqual(upload().get_json()["status"], "duplicate")
                events = app.read_ledger_expenses()
                summary = app.summarize_expense_events(events)["summary"]
                self.assertEqual(summary["income_eur"], 2120)
                self.assertEqual(summary["spend_eur"], 50)
                self.assertEqual(summary["credits_eur"], 20)
                self.assertEqual(summary["transfers_eur"], 750)
                self.assertEqual(summary["investments_eur"], 0)
                self.assertEqual(app.get_movement_store().movements(event_types=("trade", "cash_flow")), [])
                self.assertEqual(len(list((root / "sources/cash_exports/intesa").glob("account_operations-*.xlsx"))), 1)


if __name__ == "__main__":
    unittest.main()
