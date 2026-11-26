"""Statement detection without an explicit source, including Revolut's consolidated CSV."""

from __future__ import annotations

import csv
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app
from src.portfolio_dashboard.imports import detect_statement_source
from src.portfolio_dashboard.imports.revolut import read_revolut_rows


def consolidated(rows_before: int = 0) -> str:
    """A synthetic consolidated statement: section titles, then per-account tables."""

    rows = [[] for _ in range(rows_before)] + [
        ["Conti correnti Riepiloghi"],
        ["Prodotto", "Saldo di apertura", "Denaro in uscita", "Denaro in entrata", "Saldo di chiusura"],
        ["Conto personale", "0,00€", "3,00€", "100,00€", "97,00€"],
        [],
        ["Conto personale (EUR)"],
        [],
        ["Data", "Descrizione", "Categoria", "Denaro in entrata/uscita", "Saldo", "Costi"],
        ["15 giu 2023", "Ricarica", "Ricarica", "100,00€", "100,00€", "0,00€"],
        ["16 giu 2023", "Example shop", "Esercente", "-3,00€", "97,00€", "0,00€"],
        [],
        ["Riepilogo delle transazioni"],
        ["Categoria", "Denaro in entrata/uscita"],
        ["Esercente", "-3,00€"],
    ]
    output = io.StringIO()
    csv.writer(output).writerows(rows)
    return output.getvalue()


class DetectionTest(unittest.TestCase):
    def write(self, folder: str, name: str, text: str) -> Path:
        path = Path(folder) / name
        path.write_text(text, encoding="utf-8-sig")
        return path

    def test_no_requested_source_means_automatic_detection(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            trade_republic = self.write(folder, "export.csv", "type,category,shares,amount,date\n")
            self.assertEqual(detect_statement_source(trade_republic, None), "trade_republic")
            self.assertEqual(detect_statement_source(trade_republic, ""), "trade_republic")

    def test_the_consolidated_revolut_statement_is_detected_and_read(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            for leading in (0, 2):
                with self.subTest(leading_blank_lines=leading):
                    path = self.write(folder, f"consolidated-{leading}.csv", consolidated(leading))
                    self.assertEqual(detect_statement_source(path, None), "revolut")
                    self.assertEqual(detect_statement_source(path), "revolut")
                    self.assertEqual([row["Importo"] for row in read_revolut_rows(path)], ["100.00", "-3.00"])

    def test_uploading_it_without_a_source_imports_it_as_revolut(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with (
                patch.object(app, "ROOT_DIR", root / "sources"),
                patch.object(app, "MOVEMENT_DATABASE", root / "movements.sqlite3"),
                patch.object(app, "_movement_store", None),
                patch.object(app, "_legacy_imported_portfolios", {app.PRIMARY_PORTFOLIO_ID}),
                patch.object(app, "read_expense_category_rules", return_value=[]),
                app.app.test_client() as client,
            ):
                response = client.post(
                    "/api/imports",
                    data={"file": (io.BytesIO(consolidated().encode("utf-8")), "statement.csv")},
                    content_type="multipart/form-data",
                )
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual((response.get_json()["status"], response.get_json()["source"]), ("imported", "revolut"))


if __name__ == "__main__":
    unittest.main()
