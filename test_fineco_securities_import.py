from __future__ import annotations

import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook

import app
from src.portfolio_dashboard.imports import detect_statement_source

HEADERS = [
    "Operazione", "Data valuta", "Descrizione", "Titolo", "Isin", "Segno",
    "Quantita", "Divisa", "Prezzo", "Cambio", "Controvalore", "Commissioni amministrato",
]
FUND_HEADERS = ["Commissioni Fondi Sw/Ingr/Uscita", "Commissioni Fondi Banca Corrispondente", "Spese Fondi Sgr"]


def write_export(path: Path, headers: list[str]) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Movimenti Dossier Titoli"
    sheet.append(("Fineco securities export",))
    sheet.append(headers)
    sheet.append(())
    for description, sign, quantity, price, amount, fee in [
        ("Compravendita titoli", "V", "2,00", "100,00000", "200,00", "2,95"),
        ("Compravendita titoli", "A", "3,00", "90,00000", "270,00", "1,95"),
        ("Dividendo", " ", "2,00", "0,00000", "1,48", "0,00"),
    ]:
        values = dict(zip(HEADERS, [
            "15/10/2026", "19/10/2026", description, "Example equity", "US0000000001",
            sign, quantity, "EUR", price, "1,00000", amount, fee,
        ]))
        sheet.append([values.get(header, "9,99") for header in headers])
    workbook.save(path)
    workbook.close()


class FinecoSecuritiesImportTest(unittest.TestCase):
    def test_old_compact_and_reordered_exports_preserve_trades_and_dividends(self) -> None:
        for headers in [HEADERS, HEADERS[:-1] + FUND_HEADERS + HEADERS[-1:], list(reversed(HEADERS))]:
            with self.subTest(columns=headers), tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / "export.xlsx"
                write_export(path, headers)
                self.assertEqual(detect_statement_source(path), "fineco")
                trades = app.read_fineco_trades(path)
                self.assertEqual(len(trades), 2)
                buy = next(trade for trade in trades if trade.action == "Acquisto")
                sell = next(trade for trade in trades if trade.action == "Vendita")
                self.assertEqual(buy.quantity_diff, Decimal(3))
                self.assertEqual(buy.grand_total, Decimal("-271.95"))
                self.assertEqual(sell.quantity_diff, Decimal(-2))
                self.assertEqual(sell.fees, Decimal("2.95"))
                self.assertEqual(sell.grand_total, Decimal("197.05"))
                self.assertEqual(sell.date, date(2026, 10, 15))
                dividends = app.read_fineco_dividends(path)
                self.assertEqual(len(dividends), 1)
                self.assertEqual(dividends[0].amount_eur, Decimal("1.48"))
                taxes = app.read_fineco_friction_events(path)
                self.assertEqual(len(taxes), 1)
                self.assertEqual(taxes[0].amount_eur, dividends[0].tax_eur)

    def test_missing_commission_header_is_reported_instead_of_assuming_zero(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "export.xlsx"
            write_export(path, HEADERS[:-1])
            with self.assertRaisesRegex(ValueError, "missing columns: commissioni_amministrato"):
                app.read_fineco_trades(path)


if __name__ == "__main__":
    unittest.main()
