"""Intesa fund and securities operations are investment flows, not refunds (synthetic rows)."""

from __future__ import annotations

import io
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from openpyxl import Workbook

import app
from src.portfolio_dashboard.imports.intesa_pdf import (
    IntesaStatementRow,
    statement_row_beneficiary,
    statement_row_fields,
)

OWN_NAMES = ("example owner",)
DAY = date(2026, 4, 2)


def pdf_event(lines: list[str], amount: str) -> dict | None:
    row = IntesaStatementRow(DAY, DAY, lines=lines, amount=Decimal(amount))
    category, merchant, description = statement_row_fields(row)
    return app.intesa_raw_event(DAY, merchant, description, category, "EUR", Decimal(amount), True, DAY, beneficiary=statement_row_beneficiary(row))


def workbook(rows: list[tuple[str, str, str, float]]) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.title = "Lista Operazione"
    sheet.append(("Data", "Operazione", "Dettagli", "Conto o carta", "Contabilizzazione", "Categoria ", "Valuta", "Importo"))
    for operation, details, category, amount in rows:
        sheet.append((DAY, operation, details, "Conto", "SI", category, "EUR", amount))
    output = io.BytesIO()
    book.save(output)
    book.close()
    return output.getvalue()


class IntesaInvestmentFlowTest(unittest.TestCase):
    def setUp(self) -> None:
        patcher = patch.object(app, "SELF_TRANSFER_NAMES", OWN_NAMES)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_statement_redemption_of_the_owners_fund_is_an_investment_inflow(self) -> None:
        for beneficiary in (["BENEF.: OWNER EXAMPLE"], []):
            with self.subTest(beneficiary=beneficiary):
                event = pdf_event(["Rimborso titoli/quote/fondi", "EXAMPLE FUND A EUR REDEMPTION", *beneficiary], "500.00")
                self.assertEqual((event["flow_kind"], event["source_category"]), ("investment", "Investimenti titoli e fondi"))

    def test_a_redemption_paid_in_for_someone_elses_fund_is_money_received(self) -> None:
        event = pdf_event(["Rimborso titoli/quote/fondi", "EXAMPLE FUND A EUR REDEMPTION", "BENEF.: EXAMPLE RELATIVE"], "500.00")
        self.assertEqual((event["flow_kind"], event["category"], event["merchant"]), ("credit", "Money received", "EXAMPLE RELATIVE"))

    def test_card_refunds_and_subscriptions(self) -> None:
        refund = pdf_event(["Storno pagamento POS", "EXAMPLE SHOP"], "20.00")
        self.assertEqual((refund["flow_kind"], refund["source_category"]), ("credit", "Rimborsi spese e storni"))
        self.assertNotIn("category", refund)
        subscription = pdf_event(["Sottoscrizione fondi", "EXAMPLE FUND B"], "-200.00")
        self.assertEqual(subscription["flow_kind"], "investment")
        service = pdf_event(["Pagamento sottoscrizione abbonamento", "EXAMPLE GYM"], "-30.00")
        self.assertEqual(service["flow_kind"], "spend")

    def test_the_xlsx_export_classifies_the_same_way(self) -> None:
        rows = [
            ("Rimborso titoli/quote/fondi", "EXAMPLE FUND A REDEMPTION BENEF.: EXAMPLE OWNER ISIN: XX0000000001", "Rimborsi spese e storni", 500),
            ("Rimborso titoli/quote/fondi", "EXAMPLE FUND A REDEMPTION BENEF.: EXAMPLE RELATIVE ISIN: XX0000000001", "Rimborsi spese e storni", 300),
            ("Storno pagamento", "EXAMPLE SHOP", "Rimborsi spese e storni", 20),
            ("Sottoscrizione fondi", "EXAMPLE FUND B", "Altre uscite", -200),
        ]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "account_operations.xlsx"
            path.write_bytes(workbook(rows))
            events = app.read_intesa_expense_events(path, rules=[], own_transfers=True)
        kinds = sorted((event["flow_kind"], event["category"], event["merchant"], float(event["native_amount"])) for event in events)
        self.assertEqual(kinds, [
            ("credit", "Credits", "Storno pagamento", 20.0),
            ("credit", "Money received", "EXAMPLE RELATIVE", 300.0),
            ("investment", "Investments", "Rimborso titoli/quote/fondi", 500.0),
            ("investment", "Investments", "Sottoscrizione fondi", -200.0),
        ])

        summary = app.summarize_expense_events(events)["summary"]
        # 200 paid in, 500 back: a net inflow of 300 from investments; nothing is income or spending.
        self.assertEqual(summary["investments_eur"], -300.0)
        self.assertEqual((summary["income_eur"], summary["spend_eur"]), (0.0, 0.0))
        self.assertEqual(summary["credits_eur"], 320.0)
        self.assertEqual(summary["net_outflow_eur"], -300.0)


if __name__ == "__main__":
    unittest.main()
