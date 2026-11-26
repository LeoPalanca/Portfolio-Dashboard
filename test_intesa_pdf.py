"""Intesa quarterly PDF statements, read from synthetic ``pdftotext -layout`` text.

CI has no poppler, so the parser is fed the text pdftotext would print: columns
padded with spaces, thousands written as U+0019 plus a space, a table that
continues on the next page under a repeated header, and descriptions that wrap.
"""

from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import ExitStack
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from openpyxl import Workbook

import app
from src.portfolio_dashboard.imports import detect_statement_source, import_destination, intesa_pdf
from src.portfolio_dashboard.imports.intesa_pdf import (
    IntesaStatementError,
    is_intesa_statement_text,
    parse_intesa_statement_text,
    statement_row_fields,
)

DESCRIPTION_COLUMN = 47


def header(shift: int = 0) -> str:
    pad = " " * (3 + shift)
    return f"{pad}{'Data Operazione':<23}{'Data Valuta':<21}{'Descrizione':<44}{'Addebiti':>12}{'Accrediti':>22}"


def movement(operation: str, description: str, debit: str = "", credit: str = "", shift: int = 0) -> str:
    pad = " " * (3 + shift)
    return f"{pad}{operation:<23}{operation:<21}{description:<44}{debit:>12}{credit:>22}".rstrip()


def more(text: str, shift: int = 0) -> str:
    return " " * (DESCRIPTION_COLUMN + shift) + text


def statement_text(opening: str = "+1\x19 000, 00", closing: str = "+3\x19 209, 50", period=("31.12.2022", "31.03.2023")) -> str:
    start, end = period
    page_head = [
        f"{'':80}ESTRATTO CONTO N. 001/2023",
        f"{'':80}AL {end}",
        f"{'':80}C/C N. 00000/0000/00000000",
    ]
    return "\n".join(
        [
            *page_head,
            "Tipologia conto:",
            "XME Conto",
            "      Riepilogo conto corrente.",
            f"      Saldo iniziale al {start}{'':60}{opening} €",
            f"       Totale accrediti{'':60}+2\x19 520, 00 €",
            f"       Totale addebiti{'':63}310, 50 €",
            f"      Saldo finale al {end}{'':60}{closing} €",
            f"    Ci segua anche su{'':80}Pagina 1 di 3",
            "\f" + page_head[0],
            *page_head[1:],
            "Dettaglio movimenti del conto corrente.",
            f"   Saldo iniziale al {start}{'':90}{opening}",
            header(),
            movement("05.01.2023", "Pagamento POS", debit="60, 50"),
            more("EFFETTUATO IL 04/01/2023 ALLE ORE 10:00"),
            more("PRESSO EXAMPLE MARKET"),
            more("Example City"),
            movement("10.01.2023", "Bonifico a Vostro favore disposto da:", credit="2\x19 500, 00"),
            more("MITT.: EXAMPLE EMPLOYER SPA"),
            more("COD. DISP.: 0000000000000001 CASH SALARY"),
            more("BENEF.: ACCOUNT OWNER"),
            movement("15.01.2023", "Bonifico da Voi disposto a favore di:", debit="200, 00"),
            more("ACCOUNT OWNER"),
            more("0000000000000002 NOTPROVIDED"),
            more("-"),
            movement("20.01.2023", "Bonifico a Vostro favore disposto da:", credit="20, 00"),
            more("MITT.: ACCOUNT OWNER"),
            more("BENEF.: ACCOUNT OWNER"),
            movement("25.01.2023", "Prelievo sportello banca del gruppo", debit="50, 00"),
            "",
            f"{'':90}Pagina 2 di 3",
            "\f" + page_head[0],
            *page_head[1:],
            header(shift=-2),
            more("Prelievo Cardless presso ATM 0001", shift=-2),
            more("Totali", shift=-2) + f"{'':40}310, 50 €{'':14}2\x19 520, 00 €",
            f"   Saldo finale al {end}{'':60}a Vostro credito{'':20}{closing} €",
            "",
            "Giacenza media riferita all'anno 2023 .",
            f"   Saldo finale al {end}{'':40}3\x19 209, 50",
            f"{'':90}Pagina 3 di 3",
            "Dettaglio competenze di chiusura.",
            f"   29.12.2022{'':40}0%{'':20}9\x19 999, 99{'':20}0, 00",
            "www.intesasanpaolo.com",
        ]
    )


def xlsx_export(rows: list[tuple]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Lista Operazione"
    sheet.append(("Intesa Sanpaolo",))
    sheet.append(("Data", "Operazione", "Dettagli", "Conto o carta", "Contabilizzazione", "Categoria ", "Valuta", "Importo"))
    for day, merchant, details, category, amount in rows:
        sheet.append((day, merchant, details, "Conto", "SI", category, "EUR", amount))
    output = io.BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


class StatementTextTest(unittest.TestCase):
    def test_rows_wrapped_descriptions_columns_and_balances(self) -> None:
        statement = parse_intesa_statement_text(statement_text())

        self.assertEqual((statement.opening_date, statement.opening_balance), (date(2022, 12, 31), Decimal("1000.00")))
        self.assertEqual((statement.closing_date, statement.closing_balance), (date(2023, 3, 31), Decimal("3209.50")))
        self.assertEqual(
            [row.amount for row in statement.rows],
            [Decimal("-60.50"), Decimal("2500.00"), Decimal("-200.00"), Decimal("20.00"), Decimal("-50.00")],
        )
        self.assertEqual(statement.rows[0].description, "Pagamento POS EFFETTUATO IL 04/01/2023 ALLE ORE 10:00 PRESSO EXAMPLE MARKET Example City")
        # The withdrawal's description continues after the page break and its repeated header.
        self.assertEqual(statement.rows[-1].description, "Prelievo sportello banca del gruppo Prelievo Cardless presso ATM 0001")
        self.assertEqual(statement.rows[1].value_date, date(2023, 1, 10))
        self.assertEqual(statement.opening_checkpoint_date, date(2022, 12, 31))

    def test_a_new_accounts_first_statement_opens_the_day_before_its_first_movement(self) -> None:
        text = statement_text().replace("Saldo iniziale al 31.12.2022", "Saldo iniziale al 05.01.2023")
        self.assertEqual(parse_intesa_statement_text(text).opening_checkpoint_date, date(2023, 1, 4))

    def test_counterparty_and_xlsx_style_categories(self) -> None:
        fields = [statement_row_fields(row)[:2] for row in parse_intesa_statement_text(statement_text()).rows]
        self.assertEqual(
            fields,
            [
                ("Pagamento POS", "EXAMPLE MARKET"),
                ("Bonifici ricevuti", "EXAMPLE EMPLOYER SPA"),
                ("Bonifici in uscita", "ACCOUNT OWNER"),
                ("Bonifici ricevuti", "ACCOUNT OWNER"),
                ("Prelievi", "Prelievo sportello banca del gruppo"),
            ],
        )

    def test_statements_without_readable_amounts_are_refused(self) -> None:
        # Some statements draw their amounts with fonts pdftotext cannot read: the
        # dates and descriptions remain, every amount and balance is missing.
        unreadable = "\n".join(
            line for line in statement_text().splitlines() if "," not in line or "Dettaglio" in line
        ).replace("+1\x19 000, 00", "")
        for text in (unreadable, "Intesa Sanpaolo\nAllegato all'Estratto Conto\n"):
            with self.subTest(text=text[:20]), self.assertRaisesRegex(IntesaStatementError, "no readable movement amounts"):
                parse_intesa_statement_text(text)

    def test_balances_that_do_not_add_up_are_refused(self) -> None:
        with self.assertRaisesRegex(IntesaStatementError, "does not equal its closing balance"):
            parse_intesa_statement_text(statement_text(closing="+3\x19 300, 00"))
        broken_totals = statement_text().replace("310, 50 €              2", "311, 50 €              2")
        with self.assertRaisesRegex(IntesaStatementError, "debit and credit totals"):
            parse_intesa_statement_text(broken_totals)

    def test_statement_detection(self) -> None:
        self.assertTrue(is_intesa_statement_text(statement_text()))
        self.assertTrue(is_intesa_statement_text("www.intesasanpaolo.com\nAllegato all'Estratto Conto del 30.06.2023"))
        self.assertFalse(is_intesa_statement_text("Interactive Brokers\nActivity Statement\nINTESA SANPAOLO ISP"))
        self.assertFalse(is_intesa_statement_text("Activity Statement\nEstratto conto"))


class StatementDetectionTest(unittest.TestCase):
    def test_pdf_source_follows_the_text_and_falls_back_to_interactive_brokers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "statement.pdf"
            path.write_bytes(b"%PDF-1.4 synthetic")
            with patch.object(intesa_pdf, "pdf_layout_text", return_value=statement_text()):
                self.assertEqual(detect_statement_source(path), "intesa")
                self.assertEqual(detect_statement_source(path, "intesa"), "intesa")
            with patch.object(intesa_pdf, "pdf_layout_text", return_value="Interactive Brokers Activity Statement"):
                self.assertEqual(detect_statement_source(path), "interactive_brokers")
            with patch.object(intesa_pdf, "pdf_layout_text", side_effect=FileNotFoundError("pdftotext")):
                self.assertEqual(detect_statement_source(path), "interactive_brokers")
        destination = import_destination(Path("/private/source"), "intesa", "b" * 64, "statement.pdf")
        self.assertEqual(destination.parent, Path("/private/source/cash_exports/intesa"))
        self.assertTrue(destination.name.startswith("intesa-statement-") and destination.suffix == ".pdf")


class StatementImportTest(unittest.TestCase):
    def ledger(self, root: Path, text: str | None = None) -> ExitStack:
        stack = ExitStack()
        text = statement_text() if text is None else text
        for target, name, value in (
            (app, "ROOT_DIR", root / "sources"),
            (app, "MOVEMENT_DATABASE", root / "private" / "movements.sqlite3"),
            (app, "_movement_store", None),
            (app, "_legacy_imported_portfolios", {app.PRIMARY_PORTFOLIO_ID}),
            (app, "SELF_TRANSFER_NAMES", ("account owner",)),
            (app, "read_expense_category_rules", lambda *args: []),
            (app, "pdf_text", lambda path: text),
            (intesa_pdf, "pdf_layout_text", lambda path: text),
        ):
            stack.enter_context(patch.object(target, name, value))
        return stack

    def write(self, root: Path, name: str, content: bytes) -> Path:
        path = root / name
        path.write_bytes(content)
        return path

    def test_pdf_rows_look_like_xlsx_rows_and_balances_stay_out_of_the_flows(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.ledger(root):
                result = app.import_statement_path(self.write(root, "q1.pdf", b"%PDF q1"), original_name="q1.pdf")
                rows = app.get_movement_store().movements()
                events = app.read_ledger_expenses()
                summary = app.summarize_expense_events(events)["summary"]

        self.assertEqual((result["status"], result["source"], result["movements"]), ("imported", "intesa", 7))
        self.assertTrue(result["stored_path"].startswith("sources/cash_exports/intesa/intesa-statement-"))
        checkpoints = [(row["occurred_on"], row["amount"]) for row in rows if row["event_type"] == "balance_checkpoint"]
        self.assertEqual(checkpoints, [("2022-12-31", "1000.00"), ("2023-03-31", "3209.50")])
        kinds = sorted(row["event_type"] for row in rows if row["event_type"] != "balance_checkpoint")
        # Transfers to and from the owner's own name are transfers and top-ups, not spending or income.
        self.assertEqual(kinds, ["cash_withdrawal", "income", "personal_transfer", "spend", "top_up"])
        self.assertTrue(all(row["account"] == "intesa" for row in rows))
        self.assertNotIn("balance_checkpoint", {event["flow_kind"] for event in events})
        self.assertEqual(summary["income_eur"], 2500.0)
        self.assertEqual(summary["spend_eur"], 60.5)
        self.assertEqual(summary["topups_eur"], 20.0)
        self.assertEqual(summary["transfers_eur"], 250.0)

    def test_the_same_movement_from_the_pdf_and_the_xlsx_is_stored_once_in_either_order(self) -> None:
        export = xlsx_export(
            [
                (date(2023, 1, 5), "Example market", "Pagamento POS presso EXAMPLE MARKET", "Generi alimentari e supermercato", -60.5),
                (date(2023, 1, 11), "Example Employer Spa", "Bonifico da EXAMPLE EMPLOYER SPA", "Stipendi e pensioni", 2500),
                (date(2023, 4, 2), "Example streaming", "Addebito EXAMPLE STREAMING", "Tempo libero varie", -9.99),
            ]
        )
        for order in (("q1.pdf", "export.xlsx"), ("export.xlsx", "q1.pdf")):
            with self.subTest(order=order), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                files = {"q1.pdf": self.write(root, "q1.pdf", b"%PDF q1"), "export.xlsx": self.write(root, "export.xlsx", export)}
                with self.ledger(root):
                    results = [app.import_statement_path(files[name], original_name=name) for name in order]
                    flows = [row for row in app.get_movement_store().movements() if row["event_type"] != "balance_checkpoint"]
                    with patch.object(app, "IMPORT_PARSER_VERSION", "next"), patch.object(app, "_legacy_imported_portfolios", set()):
                        app.ensure_legacy_statements_imported(app.PRIMARY_PORTFOLIO_ID)
                    after = [row for row in app.get_movement_store().movements() if row["event_type"] != "balance_checkpoint"]

                self.assertEqual(results[1]["duplicates"], 2)
                # 5 statement rows and 3 export rows, of which 2 are the same movements.
                self.assertEqual(len(flows), 6)
                self.assertEqual(sorted(Decimal(row["amount"]) for row in flows).count(Decimal("-60.5")), 1)
                self.assertEqual([row["id"] for row in after], [row["id"] for row in flows])

    def test_an_unreadable_statement_is_a_clear_import_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.ledger(root, "Intesa Sanpaolo\nAllegato all'Estratto Conto\n"), app.app.test_client() as client:
                response = client.post(
                    "/api/imports",
                    data={"source": "auto", "file": (io.BytesIO(b"%PDF unreadable"), "statement.pdf")},
                    content_type="multipart/form-data",
                )
                archived = list((root / "sources").rglob("*.pdf"))
        self.assertEqual(response.status_code, 400)
        self.assertIn("XLSX movement list", response.get_json()["error"])
        self.assertEqual(archived, [])


if __name__ == "__main__":
    unittest.main()
