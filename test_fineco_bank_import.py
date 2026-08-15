from __future__ import annotations

import io
import stat
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from openpyxl import Workbook

import app
from src.portfolio_dashboard.imports import detect_statement_source, fineco_statement_kind, read_fineco_bank_movements


def fineco_bank_workbook() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Movimenti"
    sheet.append(("Conto Corrente: 1234567",))
    for _ in range(11):
        sheet.append(())
    sheet.append(
        (
            "Data_Operazione",
            "Data_Valuta",
            "Entrate",
            "Uscite",
            "Descrizione",
            "Descrizione_Completa",
            "Stato",
        )
    )
    sheet.append(
        (
            date(2026, 8, 5),
            date(2026, 7, 31),
            None,
            "-3,95",
            "Canone Mensile Conto",
            "Canone Mensile Conto Luglio 2026",
            "Contabilizzato",
        )
    )
    sheet.append(
        (
            date(2026, 8, 5),
            date(2026, 7, 31),
            3.95,
            None,
            "Sconto Canone Mensile",
            "Sconto Canone Mensile Luglio 2026",
            "Contabilizzato",
        )
    )
    sheet.append(
        (
            date(2026, 8, 4),
            date(2026, 8, 4),
            None,
            "1.234,56",
            "Bonifico Istantaneo",
            "Bonifico Istantaneo esempio",
            "Contabilizzato",
        )
    )
    sheet.append(
        (
            date(2026, 8, 3),
            date(2026, 8, 3),
            None,
            -250,
            "Compravendita Titoli",
            "Compravendita Titoli esempio",
            "Contabilizzato",
        )
    )
    sheet.append(
        (
            date(2026, 8, 2),
            date(2026, 8, 2),
            None,
            -10,
            "Pagamento carta",
            "Pagamento ancora da contabilizzare",
            "Non contabilizzato",
        )
    )
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


class FinecoBankImportTest(unittest.TestCase):
    def test_detects_and_reads_native_current_account_export(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "movements.xlsx"
            path.write_bytes(fineco_bank_workbook())

            self.assertEqual(detect_statement_source(path), "fineco")
            self.assertEqual(fineco_statement_kind(path), "bank")
            rows = read_fineco_bank_movements(path)

        self.assertEqual(len(rows), 4)
        self.assertEqual(str(rows[0]["amount"]), "-3.95")
        self.assertEqual(str(rows[2]["amount"]), "-1234.56")
        self.assertEqual(rows[0]["value_date"].isoformat(), "2026-07-31")

    def test_classifies_fineco_bank_movements(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "movements.xlsx"
            path.write_bytes(fineco_bank_workbook())
            events = app.read_fineco_bank_expense_events(path, rules=[])

        by_category = {event["source_category"]: event for event in events}
        self.assertEqual(by_category["Canone Mensile Conto"]["flow_kind"], "fee")
        self.assertEqual(by_category["Sconto Canone Mensile"]["flow_kind"], "income")
        self.assertEqual(by_category["Bonifico Istantaneo"]["flow_kind"], "personal_transfer")
        self.assertEqual(by_category["Compravendita Titoli"]["flow_kind"], "investment")

    def test_import_api_archives_and_normalizes_fineco_bank_export(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with (
                patch.object(app, "ROOT_DIR", root / "sources"),
                patch.object(app, "MOVEMENT_DATABASE", root / "private" / "movements.sqlite3"),
                patch.object(app, "_movement_store", None),
                app.app.test_client() as client,
            ):
                response = client.post(
                    "/api/imports",
                    data={"source": "auto", "file": (io.BytesIO(fineco_bank_workbook()), "movements.xlsx")},
                    content_type="multipart/form-data",
                )
                rows = app.get_movement_store().movements(app.PRIMARY_PORTFOLIO_ID)
                archived = next((root / "sources" / "broker_exports" / "fineco").glob("*.xlsx"))
                archived_mode = stat.S_IMODE(archived.stat().st_mode)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["source"], "fineco")
        self.assertEqual(response.get_json()["movements"], 4)
        self.assertEqual({row["event_type"] for row in rows}, {"fee", "income", "personal_transfer", "investment"})
        self.assertTrue(all(row["account"] == "fineco" for row in rows))
        self.assertEqual(archived_mode, 0o600)


if __name__ == "__main__":
    unittest.main()
