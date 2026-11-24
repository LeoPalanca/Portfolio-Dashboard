"""Statement parsing: number formats, refused imports and reported skipped rows."""

from __future__ import annotations

import io
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import app
from src.portfolio_dashboard.domain import parse_decimal
from src.portfolio_dashboard.domain.issues import (
    MISSING_FX_RATE,
    SKIPPED_ROW,
    UNREADABLE_NUMBER,
    collect_import_issues,
    report_import_issue,
)
from src.portfolio_dashboard.domain.money import parse_decimal_or_none

TR_HEADER = (
    "datetime,date,account_type,category,type,asset_class,name,symbol,shares,price,amount,fee,tax,currency,"
    "original_amount,original_currency,fx_rate,description,transaction_id,counterparty_name,counterparty_iban,"
    "payment_reference,mcc_code\n"
)
REVOLUT_HEADER = "Tipo,Prodotto,Data di inizio,Data di completamento,Descrizione,Importo,Costo,Valuta,State,Saldo\n"


class NumberFormatTest(unittest.TestCase):
    def test_european_and_english_notation(self) -> None:
        cases = {
            "1234.56": "1234.56",
            "1.234,56": "1234.56",
            "1,234.56": "1234.56",
            "-2.500,00 EUR": "-2500.00",
            "€1,234.56": "1234.56",
            "$12.50": "12.50",
            "EUR12,50": "12.50",
            "(2.00)": "-2.00",
            "−3,50": "-3.50",
            "1 234,56": "1234.56",
            "1 234,56": "1234.56",
            "1.234.567": "1234567",
            "1,234,567": "1234567",
            "12,5": "12.5",
            "5.800000": "5.800000",
            "+7": "7",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(parse_decimal(raw), Decimal(expected))

    def test_empty_cells_and_placeholders_are_zero(self) -> None:
        for raw in ["", "  ", None, "-", "n/a", "N.D.", "nan", "EUR"]:
            with self.subTest(raw=raw):
                self.assertEqual(parse_decimal_or_none(raw), Decimal(0))

    def test_unreadable_text_is_zero_outside_imports_and_reported_inside(self) -> None:
        self.assertIsNone(parse_decimal_or_none("abc"))
        self.assertEqual(parse_decimal("abc"), Decimal(0))
        with collect_import_issues() as issues:
            self.assertEqual(parse_decimal("12,5x"), Decimal(0))
            self.assertEqual(parse_decimal("Infinity"), Decimal(0))
        self.assertTrue(issues.blocking)
        self.assertIn("2 values could not be read as a number", issues.blocking_message())

    def test_issue_messages(self) -> None:
        with collect_import_issues() as issues:
            for day in range(1, 6):
                report_import_issue(MISSING_FX_RATE, f"USD on 2026-01-0{day}")
            report_import_issue(SKIPPED_ROW, "row with unreadable date")
        self.assertIn(
            "5 rows (USD on 2026-01-01; USD on 2026-01-02; USD on 2026-01-03; and 2 more)", issues.blocking_message()
        )
        self.assertEqual(issues.warnings(), ["1 row skipped: row with unreadable date"])
        report_import_issue(UNREADABLE_NUMBER, "ignored outside an import")


class RefusedImportTest(unittest.TestCase):
    def upload(self, name: str, content: str, source: str) -> tuple[int, dict, int]:
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
                    data={"source": source, "file": (io.BytesIO(content.encode()), name)},
                    content_type="multipart/form-data",
                )
                stored = client.get("/api/imports/status").get_json()["movements"]
                archived = list((root / "sources").rglob("*.csv")) if (root / "sources").exists() else []
        self.assertEqual(archived, [], "a refused statement must not be archived")
        return response.status_code, response.get_json(), stored

    def test_unreadable_amount_refuses_the_whole_statement(self) -> None:
        export = TR_HEADER + (
            ",2026-01-02,,TRADING,BUY,,Example ETF,XX0000000001,2,50,-100,-1,0,EUR,,,,Purchase,tx-1,,,,\n"
            ",2026-01-03,,TRADING,BUY,,Example ETF,XX0000000001,2,50,-1OO,-1,0,EUR,,,,Purchase,tx-2,,,,\n"
        )
        status, body, stored = self.upload("export.csv", export, "trade_republic")
        self.assertEqual(status, 400)
        self.assertIn("could not be read as a number ('-1OO')", body["error"])
        self.assertEqual(stored, 0)

    def test_missing_exchange_rate_refuses_instead_of_dropping_rows(self) -> None:
        statement = REVOLUT_HEADER + (
            "Pagamento con carta,Attuale,2026-01-05 09:00:00,2026-01-05 09:00:00,Store,-120.00,0.00,USD,COMPLETATO,0.00\n"
            "Pagamento con carta,Attuale,2026-01-06 09:00:00,2026-01-06 09:00:00,Coop,-10.00,0.00,EUR,COMPLETATO,0.00\n"
        )
        with (
            patch.object(app, "add_revolut_fx_histories", lambda *args, **kwargs: None),
            patch.object(app, "historical_fx_rate", lambda *args, **kwargs: None),
            patch.object(app, "fetch_history", lambda *args, **kwargs: {"prices": {}}),
        ):
            status, body, stored = self.upload("account-statement_2026_it-it.csv", statement, "revolut")
        self.assertEqual(status, 400)
        self.assertIn("no EUR exchange rate was available", body["error"])
        self.assertIn("USD on 2026-01-05", body["error"])
        self.assertEqual(stored, 0)


class BbvaAmountTest(unittest.TestCase):
    def test_italian_thousands_and_numeric_cells(self) -> None:
        self.assertEqual(app.bbva_amount("-2.500,00 EUR"), Decimal("-2500.00"))
        self.assertEqual(app.bbva_amount("12,34 EUR"), Decimal("12.34"))
        self.assertEqual(app.bbva_amount(-12.5), Decimal("-12.5"))

    def test_unreadable_date_is_reported_as_a_skipped_row(self) -> None:
        with collect_import_issues() as issues:
            self.assertIsNone(app.bbva_date("Saldo finale"))
        self.assertFalse(issues.blocking)
        self.assertEqual(issues.warnings(), ["1 row skipped: BBVA row with unreadable date 'Saldo finale'"])


class InteractiveBrokersParserTest(unittest.TestCase):
    PDF_TEXT = "\n".join(
        [
            "Azioni",
            "USD",
            "U7654321 AAPL 2026-01-05, 10:00:00 2026-01-07 - BUY 1,000 150.25 -150,250.00 -1.00 0.00",
            "U7654321 MSFT 2026-01-06, 10:00:00 2026-01-08 - SELL -10 400 4,000.00 -1.00 0.00",
            "U7654321 BRK B 2026-01-06, 11:00:00 2026-01-08 - BUY 1 500 -500.00 -1.00 0.00",
            "Forex",
            "U7654321 EUR.USD 2026-01-06, 12:00:00 2026-01-08 - BUY 100 1.1 -110 0 0",
        ]
    )

    def test_any_account_and_thousands_separators(self) -> None:
        with (
            patch.object(app, "pdf_text", lambda path: self.PDF_TEXT),
            patch.object(app, "parse_ib_instruments", lambda text: {}),
            collect_import_issues() as issues,
        ):
            trades = app.read_interactive_brokers_trades(Path("statement.pdf"))
        by_asset = {trade.asset: trade for trade in trades}
        self.assertEqual(by_asset["AAPL"].quantity, Decimal("1000"))
        self.assertEqual(by_asset["AAPL"].total_spend, Decimal("-150251.00"))
        self.assertEqual(by_asset["MSFT"].total_spend, Decimal("3999.00"))
        self.assertNotIn("BRK", by_asset)
        self.assertEqual(len(issues.warnings()), 1)
        self.assertIn("1 row skipped: Interactive Brokers trade line not recognised", issues.warnings()[0])
        self.assertFalse(issues.blocking)


if __name__ == "__main__":
    unittest.main()
