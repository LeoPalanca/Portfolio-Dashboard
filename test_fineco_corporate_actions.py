from __future__ import annotations

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook

import app

HEADERS = (
    "Operazione",
    "Data valuta",
    "Descrizione",
    "Titolo",
    "Isin",
    "Segno",
    "Quantita",
    "Divisa",
    "Prezzo",
    "Cambio",
    "Controvalore",
    "Commissioni Fondi Sw/Ingr/Uscita",
    "Commissioni Fondi Banca Corrispondente",
    "Spese Fondi Sgr",
    "Commissioni amministrato",
)


def securities_workbook(rows: list[tuple]) -> Workbook:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Movimenti Dossier Titoli"
    sheet.append(("Dossier n.: 1",))
    sheet.append(("Intestazione Dossier: TEST",))
    sheet.append(())
    sheet.append(("RISULTATO RICERCA MOVIMENTI TITOLI",))
    sheet.append(())
    sheet.append(HEADERS)
    sheet.append(())
    for row in rows:
        sheet.append(row)
    return workbook


def read_rows(rows: list[tuple]) -> list:
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "Fineco_Lista_Titoli.xlsx"
        securities_workbook(rows).save(path)
        return app.read_fineco_trades(path)


class FinecoCorporateActionTest(unittest.TestCase):
    def test_free_shares_add_quantity_without_cost(self) -> None:
        trades = read_rows(
            [
                ("02/01/2026", "02/01/2026", "Compravendita titoli", "MONSTER BEVERAGE", "US61174X1090", "A", 20, "USD", 50, 1, 1000, None, None, None, 3),
                ("02/06/2026", "02/06/2026", "Aumento capitale", "MONSTER BEVERAGE", "US61174X1090", " ", 20, "USD", 0, 1, 0, None, None, None, None),
            ]
        )
        self.assertEqual(len(trades), 2)
        free = [trade for trade in trades if trade.source == "fineco_corporate_action"]
        self.assertEqual(len(free), 1)
        self.assertEqual(free[0].quantity_diff, Decimal(20))
        self.assertEqual(app.trade_cash_amount(free[0])[0], Decimal(0))

    def test_reverse_split_removes_quantity_without_proceeds(self) -> None:
        trades = read_rows(
            [
                ("02/06/2026", "02/06/2026", "Raggruppamento azioni", "SOME STOCK", "US0000000001", "V", 10, "EUR", 0, 1, 0, None, None, None, None),
            ]
        )
        self.assertEqual(trades[0].quantity_diff, Decimal(-10))
        self.assertEqual(app.trade_cash_amount(trades[0])[0], Decimal(0))

    def test_dividend_rows_stay_out_of_trades(self) -> None:
        trades = read_rows(
            [
                ("02/04/2026", "02/04/2026", "Dividendo", "COCA-COLA CO", "US1912161007", " ", 4, "EUR", 0, 1, 0.96, None, None, None, None),
            ]
        )
        self.assertEqual(trades, [])


if __name__ == "__main__":
    unittest.main()
