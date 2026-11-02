import csv
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

import app
from src.portfolio_dashboard.imports import detect_statement_source
from src.portfolio_dashboard.imports.revolut import read_revolut_rows


class ConsolidatedRevolutTest(unittest.TestCase):
    def test_sections_native_currency_fees_and_savings(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "export.csv"
            rows = [
                ["Conti correnti Riepiloghi"],
                ["Saldo di chiusura", "999,00€"], [],
                ["Conto personale (EUR)"], [],
                ["Data", "Descrizione", "Categoria", "Denaro in entrata/uscita", "Saldo", "Costi"],
                ["15 giu 2026", "Ricarica", "Ricarica", "100,00€", "100,00€", "0,00€"],
                ["15 giu 2026", "Commissione carta", "Esercente", "-6,99€", "93,01€", "6,99€"],
                ["15 giu 2026", "A EUR Conto deposito senza vincoli", "Altri", "-20,00€", "73,01€", "0,00€"],
                ["16 giu 2026", "Shop", "Esercente", "-3,00€", "70,01€", "0,00€"],
                ["16 giu 2026", "Shop", "Esercente", "-3,00€", "67,01€", "0,00€"],
                ["Totale", "", "", "0,00€"], [],
                ["Conto personale (CHF)"], [],
                ["Data", "Descrizione", "Categoria", "Denaro in entrata/uscita", "Denaro in entrata/uscita", "Saldo", "Saldo"],
                ["29 giu 2026", "Conversione in CHF", "Cambio valuta", "12,50 CHF", "13,55€", "12,50 CHF", "13,55€"],
                ["30 giu 2026", "Cafe", "Esercente", "-12,50 CHF", "-13,55€", "0,00 CHF", "0,00€"], [],
                ["Deposito senza vincoli  (EUR)"], [],
                ["Data", "Descrizione", "Gross interest", "Imposte trattenute", "Net interest"],
                ["25/06/26", "Interessi netti", "0,02€", "0,01€", "0,01€"],
            ]
            with path.open("w", newline="", encoding="utf-8-sig") as handle:
                csv.writer(handle).writerows(rows)
            self.assertEqual(detect_statement_source(path), "revolut")
            normalized = read_revolut_rows(path)
            self.assertEqual(len(normalized), 9)
            self.assertEqual(normalized[-2]["Importo"], "-12.50")
            events = app.read_revolut_cash_events([path])
            self.assertEqual(sum(e["cash_change"] for e in events if e["currency"] == "EUR"), Decimal("87.02"))
            self.assertEqual(sum(e["contrib_change"] for e in events if e["currency"] == "CHF"), Decimal("-12.50"))
            expenses = app.read_revolut_expense_events([path], rules=[], fx_histories={"CHF": {"history": {date(2026, 6, 30): 1.0}}})
            self.assertEqual(sum(e["flow_kind"] == "fee" for e in expenses), 1)
            self.assertEqual(sum(e["merchant"] == "Shop" for e in expenses), 2)
            self.assertTrue(any(e["flow_kind"] == "income" and e["merchant"] == "Interessi netti" for e in expenses))


if __name__ == "__main__":
    unittest.main()
