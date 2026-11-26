"""Own-account transfers between Revolut and Trade Republic, Intesa or BBVA pair up (synthetic rows)."""

from __future__ import annotations

import csv
import io
import tempfile
import unittest
from contextlib import ExitStack
from datetime import date
from decimal import Decimal
from pathlib import Path

import app
from test_revolut_sub_accounts import EUR_HEADER, eur, isolated_app, table, upload

# A made-up IBAN carrying Revolut's Italian bank code (ABI 03669); it is no real account.
REVOLUT_IBAN = "IT00X0366900000000000000000"
TR_HEADER = (
    "datetime,date,account_type,category,type,asset_class,name,symbol,shares,price,amount,fee,tax,currency,"
    "original_amount,original_currency,fx_rate,description,transaction_id,counterparty_name,counterparty_iban,"
    "payment_reference,mcc_code\n"
)


def event(source: str, flow_kind: str, day: int, description: str = "", amount: str = "100") -> dict:
    return {"source": source, "flow_kind": flow_kind, "date": date(2026, 5, day), "amount_eur": Decimal(amount),
            "merchant": "Top-up" if flow_kind == "top_up" else "Withdrawal", "description": description}


class PairingRuleTest(unittest.TestCase):
    def test_a_top_up_sent_from_revolut_pairs_with_the_revolut_transfer_not_a_closer_one(self) -> None:
        revolut = event("revolut", "personal_transfer", 4, "Pagamento a favore di Example Owner")
        intesa = event("intesa", "top_up", 4, "Bonifico a vostro favore")
        trade_republic = event("Trade Republic", "top_up", 5, "Inviato da Revolut")
        app.mark_internal_transfers([revolut, intesa, trade_republic])
        self.assertTrue(revolut.get("internal") and trade_republic.get("internal"))
        self.assertFalse(intesa.get("internal"))

    def test_the_sender_iban_bank_code_names_revolut(self) -> None:
        intesa_out = event("intesa", "personal_transfer", 4, "Bonifico disposto")
        revolut_out = event("Revolut", "transfer_out", 3, "To Example Owner")
        trade_republic = event("Trade Republic", "top_up", 4, f"Incoming transfer from Example Owner ({REVOLUT_IBAN})")
        app.mark_internal_transfers([intesa_out, revolut_out, trade_republic])
        self.assertTrue(revolut_out.get("internal") and trade_republic.get("internal"))
        self.assertFalse(intesa_out.get("internal"))

    def test_revolut_pairs_with_intesa_and_bbva_too(self) -> None:
        to_intesa = event("Revolut", "transfer_out", 6, "To Example Owner", "250")
        intesa = event("intesa", "top_up", 7, f"Bonifico a vostro favore ORDINANTE EXAMPLE OWNER {REVOLUT_IBAN}", "250")
        to_bbva = event("revolut", "personal_transfer", 8, "Pagamento a favore di Example Owner", "75")
        bbva = event("BBVA", "income", 9, "Transferencia recibida Revolut", "75")
        app.mark_internal_transfers([to_intesa, intesa, to_bbva, bbva])
        self.assertTrue(all(item.get("internal") for item in (to_intesa, intesa, to_bbva, bbva)))

    def test_without_a_hint_the_closest_day_wins_and_a_top_up_before_income(self) -> None:
        out = event("revolut", "personal_transfer", 10)
        far = event("intesa", "top_up", 13)
        income = event("bbva", "income", 11)
        near = event("Trade Republic", "top_up", 11)
        app.mark_internal_transfers([out, far, income, near])
        self.assertEqual([bool(item.get("internal")) for item in (far, income, near)], [False, False, True])

    def test_a_row_already_matched_is_left_alone(self) -> None:
        out = event("revolut", "personal_transfer", 10)
        deposit = {**event("intesa", "top_up", 10), "internal": True}
        app.mark_internal_transfers([out, deposit])
        self.assertFalse(out.get("internal"))


class LedgerPairingTest(unittest.TestCase):
    def test_the_consolidated_revolut_transfer_matches_the_trade_republic_top_up(self) -> None:
        rows = [["Conti correnti Riepiloghi"], [], ["Conti correnti Estratti conto delle operazioni"], []]
        rows += table("Conto personale (EUR)", EUR_HEADER, [
            eur("2 mag 2026", "Ricarica di Apple Pay con *0000", "Ricarica", "500,00", "500,00"),
            eur("4 mag 2026", "Pagamento a favore di Example Owner", "Altri", "-300,00", "200,00"),
        ])
        output = io.StringIO()
        csv.writer(output).writerows(rows)
        trade_republic = TR_HEADER + (
            ",2026-05-05,,CASH,CUSTOMER_INBOUND,,,,,,300.00,0,0,EUR,,,,Inviato da Revolut,tr-0001,Example Owner,,,\n"
            ",2026-05-06,,CASH,CUSTOMER_INBOUND,,,,,,40.00,0,0,EUR,,,,Incoming transfer,tr-0002,Example Owner,,,\n"
        )
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            isolated_app(stack, Path(temporary))
            client = stack.enter_context(app.app.test_client())
            self.assertEqual(upload(client, app.PRIMARY_PORTFOLIO_ID, output.getvalue()).get_json()["status"], "imported")
            self.assertEqual(upload(client, app.PRIMARY_PORTFOLIO_ID, trade_republic, "trade-republic.csv").get_json()["status"], "imported")
            payload = app.personal_expenses_payload(app.PRIMARY_PORTFOLIO_ID)

        transfers = {(row["source_label"], row["flow_kind"], row["amount_eur"]): row["internal"] for row in payload["rows"] if row["flow_kind"] != "top_up" or row["amount_eur"] != 500.0}
        self.assertEqual(transfers, {
            ("Revolut", "personal_transfer", 300.0): True,
            ("Trade Republic", "top_up", 300.0): True,
            ("Trade Republic", "top_up", 40.0): False,
        })
        # The Apple Pay top-up and the 40 came from accounts that are not imported.
        self.assertEqual(payload["summary"]["unmatched_topups_eur"], 540.0)


if __name__ == "__main__":
    unittest.main()
