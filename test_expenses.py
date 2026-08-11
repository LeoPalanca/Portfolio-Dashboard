from __future__ import annotations

import csv
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from openpyxl import Workbook

import app


class ExpenseRuleTest(unittest.TestCase):
    def write_rules(self, directory: str, rows: list[str]) -> Path:
        path = Path(directory) / "rules.csv"
        path.write_text(
            "\n".join(
                [
                    "priority,enabled,source,match_field,match_type,pattern,category,subcategory,merchant",
                    *rows,
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        return path

    def test_rule_priority_source_and_match_types(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rules_path = self.write_rules(
                tmp,
                [
                    "20,1,all,merchant,contains,market,Shopping,Retail,",
                    "10,1,all,merchant,contains,market,Groceries,Supermarket,",
                    "30,1,revolut,merchant,exact,Source Only,Dining,Cafe,",
                    "40,1,all,merchant,exact,Source Only,Shopping,Retail,",
                    "50,1,all,description,regex,^Monthly .*,Subscriptions & Digital,Software,",
                    "60,0,all,merchant,contains,market,Entertainment,Disabled,",
                ],
            )

            rules = app.read_expense_category_rules(rules_path)

        priority_event = app.classify_expense_event(
            {
                "source": "trade_republic",
                "merchant": "City Market",
                "description": "",
                "flow_kind": "spend",
                "category": "Uncategorized",
            },
            rules,
        )
        source_event = app.classify_expense_event(
            {
                "source": "revolut",
                "merchant": "Source Only",
                "description": "",
                "flow_kind": "spend",
                "category": "Uncategorized",
            },
            rules,
        )
        regex_event = app.classify_expense_event(
            {
                "source": "trade_republic",
                "merchant": "Cloud",
                "description": "Monthly cloud subscription",
                "flow_kind": "spend",
                "category": "Uncategorized",
            },
            rules,
        )
        fallback_event = app.classify_expense_event(
            {
                "source": "trade_republic",
                "merchant": "Unknown",
                "description": "Nothing matching",
                "flow_kind": "spend",
                "category": "Uncategorized",
            },
            rules,
        )

        self.assertEqual(priority_event["category"], "Groceries")
        self.assertEqual(priority_event["subcategory"], "Supermarket")
        self.assertEqual(source_event["category"], "Dining")
        self.assertEqual(regex_event["category"], "Subscriptions & Digital")
        self.assertEqual(fallback_event["category"], "Uncategorized")

    def test_example_rules_classify_generic_merchants(self) -> None:
        rules = app.read_expense_category_rules(app.APP_DIR / "data" / "expense_category_rules.example.csv")
        cases = [
            ("City Market Central", "Card payment", "Groceries", "Supermarket", "spend", "City Market Central"),
            ("Metro Transit", "Monthly pass", "Transport & Fuel", "Public transport", "spend", "Metro Transit"),
            ("Example Cloud", "Subscription", "Subscriptions & Digital", "Software", "spend", "Example Cloud"),
            ("Property Manager", "Monthly rent", "Housing & Utilities", "Rent", "spend", "Property Manager"),
            ("Example University", "Tuition payment", "Education", "Tuition", "spend", "Example University"),
            ("Property Manager", "Refundable deposit", "Credits", "Housing deposit", "credit", "Example Housing Deposit"),
        ]

        for item in cases:
            merchant, description, category, subcategory, flow_kind, expected_merchant = item[:6]
            amount = item[6] if len(item) > 6 else Decimal("-10.00")
            with self.subTest(merchant=merchant, amount=amount):
                event = app.classify_expense_event(
                    {
                        "source": "trade_republic",
                        "merchant": merchant,
                        "description": description,
                        "flow_kind": "personal_transfer" if category == "Credits" else "spend",
                        "category": "Personal Transfers" if category == "Credits" else "Uncategorized",
                        "native_amount": amount,
                        "amount_eur": amount,
                    },
                    rules,
                )
                self.assertEqual(event["category"], category)
                self.assertEqual(event["subcategory"], subcategory)
                self.assertEqual(event["flow_kind"], flow_kind)
                self.assertEqual(event["merchant"], expected_merchant)


class RevolutExpenseExtractionTest(unittest.TestCase):
    def write_statement(self, directory: str, rows: list[str]) -> Path:
        path = Path(directory) / "account-statement_test_it-it.csv"
        path.write_text(
            "\n".join(
                [
                    "Tipo,Prodotto,Data di inizio,Data di completamento,Descrizione,Importo,Costo,Valuta,State,Saldo",
                    *rows,
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        return path

    def test_revolut_expenses_include_spend_transfers_investments_and_income(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_statement(
                tmp,
                [
                    "Pagamento con carta,Attuale,2026-01-01 09:00:00,2026-01-01 09:00:00,Coop,-10.00,0.00,EUR,COMPLETATO,90.00",
                    "Pagamento,Attuale,2026-01-01 10:00:00,2026-01-01 10:00:00,Accredita EUR Vault da EUR,-20.00,0.00,EUR,COMPLETATO,70.00",
                    "Cambia valuta,Attuale,2026-01-01 11:00:00,2026-01-01 11:00:00,Conversione in CHF,-10.00,0.00,EUR,COMPLETATO,60.00",
                    "Pagamento,Attuale,2026-01-02 08:00:00,2026-01-02 08:00:00,To Account Owner,-20.00,0.00,EUR,COMPLETATO,40.00",
                    "Pagamento,Attuale,2026-01-02 09:00:00,2026-01-02 09:00:00,To Michele Rossi,-20.00,0.00,EUR,COMPLETATO,20.00",
                    "Pagamento,Attuale,2026-01-03 09:00:00,2026-01-03 09:00:00,Al conto di investimento,-50.00,0.00,EUR,COMPLETATO,-10.00",
                    "Rimborso su carta,Attuale,2026-01-04 09:00:00,2026-01-04 09:00:00,Amazon,5.00,0.00,EUR,COMPLETATO,-5.00",
                    "CASHBACK,Attuale,2026-01-05 09:00:00,2026-01-05 09:00:00,Cashback,1.00,0.00,EUR,COMPLETATO,-4.00",
                    "Ricarica,Attuale,2026-01-06 09:00:00,2026-01-06 09:00:00,Ricarica di Apple Pay con *1234,100.00,0.00,EUR,COMPLETATO,96.00",
                    "Pagamento con carta,Attuale,2026-01-07 09:00:00,,Cancelled,-9.00,0.00,EUR,OPERAZIONE ANNULLATA,",
                ],
            )

            with patch.object(app, "SELF_TRANSFER_NAMES", ("account owner",)):
                events = app.read_revolut_expense_events([path], rules=[])

        self.assertEqual(len(events), 5)
        by_merchant = {event["merchant"]: event for event in events}
        self.assertEqual(by_merchant["Coop"]["flow_kind"], "spend")
        self.assertNotIn("To Account Owner", by_merchant)
        self.assertEqual(by_merchant["To Michele Rossi"]["category"], "Personal Transfers")
        self.assertEqual(by_merchant["Al conto di investimento"]["category"], "Investments")
        self.assertEqual(by_merchant["Amazon"]["category"], "Income")
        self.assertEqual(by_merchant["Cashback"]["category"], "Income")

    def test_revolut_chf_expense_uses_historical_fx(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_statement(
                tmp,
                [
                    "Pagamento con carta,Attuale,2026-02-01 09:00:00,2026-02-01 09:00:00,Coop,-10.00,0.00,CHF,COMPLETATO,90.00",
                ],
            )
            fx_history = {"status": "priced", "prices": {"2026-02-01": 1.1}}
            with patch.object(app, "fetch_history", return_value=fx_history):
                events = app.read_revolut_expense_events([path], rules=[])

        self.assertEqual(events[0]["amount_eur"], Decimal("11.000"))
        self.assertEqual(events[0]["currency"], "CHF")


class TradeRepublicExpenseExtractionTest(unittest.TestCase):
    columns = [
        "datetime",
        "date",
        "account_type",
        "category",
        "type",
        "asset_class",
        "name",
        "symbol",
        "shares",
        "price",
        "amount",
        "fee",
        "tax",
        "currency",
        "original_amount",
        "original_currency",
        "fx_rate",
        "description",
        "transaction_id",
        "counterparty_name",
        "counterparty_iban",
        "payment_reference",
        "mcc_code",
    ]

    def write_export(self, directory: str, rows: list[dict[str, str]]) -> Path:
        path = Path(directory) / "trade_republic.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.columns)
            writer.writeheader()
            for row in rows:
                base = {column: "" for column in self.columns}
                base.update(row)
                writer.writerow(base)
        return path

    def test_trade_republic_card_scope_and_exclusions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_export(
                tmp,
                [
                    {"date": "2026-01-01", "type": "CARD_TRANSACTION", "name": "Market", "amount": "-12.00", "currency": "EUR", "description": "TR Card Transaction"},
                    {"date": "2026-01-02", "type": "CARD_TRANSACTION_INTERNATIONAL", "name": "OpenAI", "amount": "-18.80", "currency": "EUR", "original_amount": "-21.62", "original_currency": "USD", "description": "OpenAI USD card"},
                    {"date": "2026-01-03", "type": "CARD_ORDERING_FEE", "name": "", "amount": "0.00", "fee": "-5.00", "currency": "EUR", "description": "Trade Republic Card"},
                    {"date": "2026-01-04", "type": "CARD_TRANSACTION", "name": "Refund", "amount": "3.00", "currency": "EUR", "description": "Refund"},
                    {"date": "2026-01-05", "type": "BUY", "name": "Stock", "amount": "-10.00", "fee": "-1.00", "currency": "EUR"},
                    {"date": "2026-01-06", "type": "CUSTOMER_INPAYMENT", "amount": "100.00", "currency": "EUR"},
                    {"date": "2026-01-07", "type": "DIVIDEND", "amount": "1.00", "tax": "-0.26", "currency": "EUR"},
                    {"date": "2026-01-08", "type": "INTEREST_PAYMENT", "amount": "1.00", "currency": "EUR"},
                    {"date": "2026-01-09", "type": "BENEFITS_SAVEBACK", "amount": "1.00", "currency": "EUR"},
                    {"date": "2026-01-10", "type": "STOCKPERK", "amount": "1.00", "currency": "EUR"},
                    {"date": "2026-01-11", "type": "CARD_TRANSACTION", "name": "Revolut**2841*", "amount": "-50.00", "currency": "EUR", "description": "Revolut**2841*"},
                ],
            )

            events = app.read_trade_republic_expense_events(path, rules=[])

        self.assertEqual(len(events), 4)
        by_merchant = {event["merchant"]: event for event in events}
        self.assertEqual(by_merchant["Market"]["flow_kind"], "spend")
        self.assertEqual(by_merchant["OpenAI"]["currency"], "USD")
        self.assertEqual(by_merchant["OpenAI"]["native_amount"], Decimal("-21.62"))
        self.assertEqual(by_merchant["OpenAI"]["amount_eur"], Decimal("18.80"))
        self.assertEqual(by_merchant["Trade Republic Card"]["category"], "Fees")
        self.assertEqual(by_merchant["Refund"]["category"], "Income")
        self.assertNotIn("Revolut**2841*", by_merchant)


class IntesaExpenseExtractionTest(unittest.TestCase):
    columns = [
        "Data",
        "Operazione",
        "Dettagli",
        "Conto o carta",
        "Contabilizzazione",
        "Categoria ",
        "Valuta",
        "Importo",
    ]

    def write_workbook(self, directory: str, rows: list[list[object]]) -> Path:
        path = Path(directory) / "Lista_Operazioni_18062026.xlsx"
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Lista Operazione"
        for _ in range(18):
            sheet.append([])
        sheet.append(self.columns)
        for row in rows:
            sheet.append(row)
        workbook.save(path)
        return path

    def test_intesa_expenses_include_accounted_spend_transfers_fees_cash_and_income(self) -> None:
        rules = [
            app.ExpenseRule(
                priority=1,
                source="intesa",
                match_field="source_category",
                match_type="exact",
                pattern="Generi alimentari e supermercato",
                category="Groceries",
                subcategory="Supermarkets",
                merchant="",
            )
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_workbook(
                tmp,
                [
                    [datetime(2026, 1, 1), "City Market", "Pagamento POS", "Conto", "SI", "Generi alimentari e supermercato", "EUR", -12.34],
                    [date(2026, 1, 2), "Bonifico Rossi", "Bonifico a favore di Rossi", "Conto", "SI", "Bonifici in uscita", "EUR", -100.00],
                    [date(2026, 1, 3), "Commissione Pagamento Cbill", "Commissione", "Conto", "SI", "Imposte, bolli e commissioni", "EUR", -1.50],
                    [date(2026, 1, 4), "Prelievo Sportello", "Prelievo ATM", "Carta", "SI", "Prelievi", "EUR", -50.00],
                    [date(2026, 1, 5), "Rimborso carta", "Rimborso", "Conto", "SI", "Rimborsi spese e storni", "EUR", 8.00],
                    [date(2026, 1, 6), "Pending", "Da ignorare", "Conto", "NO", "Generi alimentari e supermercato", "EUR", -99.00],
                    [date(2026, 1, 7), "Bonifico Account Owner", "Bonifico a favore di ACCOUNT OWNER", "Conto", "SI", "Bonifici in uscita", "EUR", -200.00],
                    [date(2026, 1, 8), "Account Owner", "Giroconto in entrata ACCOUNT OWNER", "Conto", "SI", "Giroconto in entrata", "EUR", 200.00],
                ],
            )

            with patch.object(app, "SELF_TRANSFER_NAMES", ("account owner",)):
                events = app.read_intesa_expense_events(path, rules=rules)

        self.assertEqual(len(events), 5)
        by_merchant = {event["merchant"]: event for event in events}
        self.assertEqual(by_merchant["City Market"]["source"], "intesa")
        self.assertEqual(by_merchant["City Market"]["flow_kind"], "spend")
        self.assertEqual(by_merchant["City Market"]["category"], "Groceries")
        self.assertEqual(by_merchant["City Market"]["source_category"], "Generi alimentari e supermercato")
        self.assertEqual(by_merchant["Bonifico Rossi"]["category"], "Personal Transfers")
        self.assertEqual(by_merchant["Commissione Pagamento Cbill"]["category"], "Fees")
        self.assertEqual(by_merchant["Prelievo Sportello"]["category"], "Cash Withdrawals")
        self.assertEqual(app.expense_row_kind(by_merchant["Prelievo Sportello"]), "spend")
        self.assertEqual(by_merchant["Rimborso carta"]["category"], "Income")
        self.assertEqual(by_merchant["Rimborso carta"]["amount_eur"], Decimal("8.0"))
        self.assertNotIn("Bonifico Account Owner", by_merchant)
        self.assertNotIn("Account Owner", by_merchant)

        summary = app.summarize_expense_events(events)["summary"]
        self.assertEqual(summary["spend_eur"], 63.84)
        self.assertEqual(summary["transfers_eur"], 100.0)
        self.assertEqual(summary["income_eur"], 8.0)


class ExpenseSummaryTest(unittest.TestCase):
    def event(self, day: date, flow_kind: str, amount: str, category: str) -> dict[str, object]:
        return {
            "date": day,
            "source": "revolut",
            "merchant": category,
            "description": category,
            "flow_kind": flow_kind,
            "category": category,
            "subcategory": "",
            "amount_eur": Decimal(amount),
            "currency": "EUR",
            "native_amount": Decimal(amount),
            "confidence": 0.5,
        }

    def test_summary_reconciles_net_outflow(self) -> None:
        payload = app.summarize_expense_events(
            [
                self.event(date(2026, 1, 1), "spend", "100", "Shopping"),
                self.event(date(2026, 1, 2), "income", "20", "Income"),
                self.event(date(2026, 1, 3), "personal_transfer", "30", "Personal Transfers"),
                self.event(date(2026, 1, 4), "investment", "40", "Investments"),
                self.event(date(2026, 1, 5), "credit", "60", "Credits"),
            ]
        )

        summary = payload["summary"]
        self.assertEqual(summary["spend_eur"], 100.0)
        self.assertEqual(summary["income_eur"], 20.0)
        self.assertEqual(summary["transfers_eur"], 30.0)
        self.assertEqual(summary["investments_eur"], 40.0)
        self.assertEqual(summary["credits_eur"], 60.0)
        self.assertEqual(summary["net_outflow_eur"], 120.0)
        self.assertEqual(len(payload["credits"]), 1)

    def test_export_period_filter_changes_expense_rows(self) -> None:
        rows = [
            {"date": "2026-01-01", "amount_eur": 10.0, "category": "Shopping", "flow_kind": "spend"},
            {"date": "2026-02-01", "amount_eur": 20.0, "category": "Dining", "flow_kind": "spend"},
        ]

        all_rows = app.export_period_rows_by_date(rows, "all")
        one_month_rows = app.export_period_rows_by_date(rows, "1m")

        self.assertEqual(len(all_rows), 2)
        self.assertEqual(one_month_rows, [rows[1]])


class BBVAExpenseExtractionTest(unittest.TestCase):
    columns = [
        "Empty",
        "Data valuta",
        "Data",
        "Causale",
        "Movimento",
        "Beneficiario",
        "Importo",
    ]

    def write_workbook(self, directory: str, rows: list[list[object]]) -> Path:
        path = Path(directory) / "test_BBVA_Estratto_conto.xls"
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(self.columns)
        for row in rows:
            sheet.append(row)
        workbook.save(path)
        return path

    def test_bbva_expenses_parsing(self) -> None:
        rules = [
            app.ExpenseRule(
                priority=1,
                source="bbva",
                match_field="merchant",
                match_type="contains",
                pattern="Example Utilities",
                category="Housing & Utilities",
                subcategory="Utilities",
                merchant="Example Utilities",
            )
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_workbook(
                tmp,
                [
                    [None, "01/05/2026", "06/05/2026", "LIQUIDAZIONE INTERESSI", "", "-", "0.01 EUR"],
                    [None, "03/03/2026", "03/03/2026", "BONIFICO ESEGUITO", "Monthly utility bill", "Example Utilities\nIT57...", "-161.50 EUR"],
                    [None, "03/03/2026", "03/03/2026", "BONIFICO RICEVUTO", "Internal transfer", "Account Owner\nIT60...", "50.00 EUR"],
                ],
            )

            with patch.object(app, "SELF_TRANSFER_NAMES", ("account owner",)):
                events = app.read_bbva_expense_events([path], rules=rules)

        self.assertEqual(len(events), 2)  # 1 interest, 1 outflow (giroconto is skipped)
        by_merchant = {event["merchant"]: event for event in events}
        self.assertEqual(by_merchant["Example Utilities"]["flow_kind"], "spend")
        self.assertEqual(by_merchant["Example Utilities"]["category"], "Housing & Utilities")
        self.assertEqual(by_merchant["Example Utilities"]["subcategory"], "Utilities")
        self.assertEqual(by_merchant["Example Utilities"]["native_amount"], Decimal("-161.50"))

        self.assertEqual(by_merchant["LIQUIDAZIONE INTERESSI"]["flow_kind"], "income")
        self.assertEqual(by_merchant["LIQUIDAZIONE INTERESSI"]["category"], "Income")


if __name__ == "__main__":
    unittest.main()
