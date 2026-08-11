from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import app


class DividendTaxTest(unittest.TestCase):
    def test_fineco_net_dividend_implies_26_percent_tax(self) -> None:
        net = Decimal("74")
        tax = app.fineco_dividend_tax_from_net(net)

        self.assertEqual(tax, Decimal("26"))

    def test_dividend_summary_includes_gross_amount(self) -> None:
        summary = app.summarize_dividends(
            [
                app.Dividend(
                    broker="Fineco",
                    asset="Example",
                    isin="IT0000000000",
                    date=date(2026, 1, 1),
                    amount_eur=Decimal("74"),
                    tax_eur=Decimal("26"),
                )
            ]
        )

        self.assertEqual(summary["total_eur"], 74.0)
        self.assertEqual(summary["tax_eur"], 26.0)
        self.assertEqual(summary["gross_eur"], 100.0)
        self.assertEqual(summary["rows"][0]["gross_eur"], 100.0)

    def test_fineco_sell_net_gain_implies_capital_gain_tax_event(self) -> None:
        trades = [
            app.Trade(
                asset="Example",
                isin="IT0000000000",
                broker="Fineco",
                action="Acquisto",
                currency_hint="EUR",
                cash_currency="EUR",
                date=date(2026, 1, 1),
                price=Decimal("74"),
                quantity=Decimal("1"),
                quantity_diff=Decimal("1"),
                total_spend=Decimal("74"),
                fees=Decimal("0"),
                tax=Decimal("0"),
                grand_total=Decimal("74"),
                grand_total_present=True,
                source="test",
            ),
            app.Trade(
                asset="Example",
                isin="IT0000000000",
                broker="Fineco",
                action="Vendita",
                currency_hint="EUR",
                cash_currency="EUR",
                date=date(2026, 2, 1),
                price=Decimal("148"),
                quantity=Decimal("1"),
                quantity_diff=Decimal("-1"),
                total_spend=Decimal("148"),
                fees=Decimal("0"),
                tax=Decimal("0"),
                grand_total=Decimal("148"),
                grand_total_present=True,
                source="test",
            ),
        ]

        events = app.inferred_fineco_sell_tax_events(trades)
        summary = app.summarize_trades(trades)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].amount_eur, Decimal("26"))
        self.assertEqual(summary["totals"]["taxes"], 26.0)


class RevolutCashHistoryTest(unittest.TestCase):
    def write_statement(self, directory: str, name: str, rows: list[str]) -> Path:
        path = Path(directory) / name
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

    def test_revolut_eur_cash_history_keeps_internal_transfers_out_of_contributions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_statement(
                tmp,
                "account-statement_2026-01-01_2026-01-04_it-it_test.csv",
                [
                    "Ricarica,Attuale,2026-01-01 09:00:00,2026-01-01 09:00:01,Ricarica di Apple Pay con *1234,100.00,0.00,EUR,COMPLETATO,100.00",
                    "Pagamento,Attuale,2026-01-02 09:00:00,2026-01-02 09:00:00,Accredita EUR Vault da EUR,-40.00,0.00,EUR,COMPLETATO,60.00",
                    "Pagamento,Risparmi,2026-01-02 09:00:00,2026-01-02 09:00:00,Accredita EUR Vault da EUR,40.00,0.00,EUR,COMPLETATO,40.00",
                    "Pagamento con carta,Attuale,2026-01-03 09:00:00,2026-01-03 09:00:00,Coop,-10.00,0.00,EUR,COMPLETATO,50.00",
                    "Pagamento,Risparmi,2026-01-03 10:00:00,2026-01-03 10:00:00,To EUR,-5.00,0.00,EUR,COMPLETATO,35.00",
                    "Pagamento,Attuale,2026-01-03 10:00:00,2026-01-03 10:00:00,To EUR,5.00,0.00,EUR,COMPLETATO,55.00",
                    "Pagamento,Attuale,2026-01-03 11:00:00,2026-01-03 11:00:00,To Account Owner,-20.00,0.00,EUR,COMPLETATO,35.00",
                    "Pagamento con carta,Attuale,2026-01-04 09:00:00,,Cancelled,-50.00,0.00,EUR,OPERAZIONE ANNULLATA,",
                ],
            )

            history = app.read_revolut_cash_history([path])

        self.assertEqual(sum((cash for _, cash, _ in history), Decimal("0")), Decimal("70.00"))
        self.assertEqual(sum((contrib for _, _, contrib in history), Decimal("0")), Decimal("70.00"))
        self.assertTrue(any(cash == Decimal("-40.00") and contrib == Decimal("0") for _, cash, contrib in history))
        self.assertTrue(any(cash == Decimal("40.00") and contrib == Decimal("0") for _, cash, contrib in history))
        self.assertTrue(any(cash == Decimal("-5.00") and contrib == Decimal("0") for _, cash, contrib in history))
        self.assertTrue(any(cash == Decimal("5.00") and contrib == Decimal("0") for _, cash, contrib in history))
        self.assertTrue(any(cash == Decimal("-20.00") and contrib == Decimal("-20.00") for _, cash, contrib in history))

    def test_revolut_chf_cash_history_converts_to_eur(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_statement(
                tmp,
                "account-statement_2026-02-01_2026-02-03_it-it_test.csv",
                [
                    "Cambia valuta,Attuale,2026-02-01 09:00:00,2026-02-01 09:00:00,Conversione in CHF,100.00,1.00,CHF,COMPLETATO,99.00",
                    "Ricarica,Attuale,2026-02-02 09:00:00,2026-02-02 09:00:00,Pagamento da UNIVERSITA DELLA SVIZZERA ITALIANA,50.00,0.00,CHF,COMPLETATO,149.00",
                    "Pagamento con carta,Attuale,2026-02-03 09:00:00,2026-02-03 09:00:00,Coop,-10.00,0.00,CHF,COMPLETATO,139.00",
                ],
            )
            fx_history = {
                "status": "priced",
                "prices": {
                    "2026-02-01": 1.1,
                    "2026-02-02": 1.1,
                    "2026-02-03": 1.1,
                },
            }

            with patch.object(app, "fetch_history", return_value=fx_history):
                history = app.read_revolut_cash_history([path])
                events = app.read_revolut_cash_events([path])
                fx_histories = {}
                app.add_revolut_fx_histories(events, date(2026, 2, 1), date(2026, 2, 3), fx_histories)
                balance = app.revolut_cash_balance_eur(events, date(2026, 2, 3), fx_histories)
                contributions = app.revolut_contributions_eur(events, date(2026, 2, 3), fx_histories)

        self.assertEqual(sum((cash for _, cash, _ in history), Decimal("0")), Decimal("152.900"))
        self.assertEqual(sum((contrib for _, _, contrib in history), Decimal("0")), Decimal("44.00"))
        self.assertTrue(any(cash == Decimal("108.90") and contrib == Decimal("0.0") for _, cash, contrib in history))
        self.assertEqual(balance, Decimal("152.900"))
        self.assertEqual(contributions, Decimal("44.00"))


if __name__ == "__main__":
    unittest.main()
