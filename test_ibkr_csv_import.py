"""Interactive Brokers activity statements exported as CSV (Italian or English)."""

from __future__ import annotations

import tempfile
import unittest
from contextlib import ExitStack
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import app
from src.portfolio_dashboard.domain.issues import collect_import_issues
from src.portfolio_dashboard.imports import detect_statement_source
from src.portfolio_dashboard.imports.ibkr_csv import read_activity_statement

ITALIAN = """﻿Statement,Header,Nome del campo,Valore del cmapo
Statement,Data,BrokerName,Interactive Brokers Ireland Limited
Statement,Data,Title,Rendiconto di attività
Dati del conto,Header,Nome del campo,Valore del cmapo
Dati del conto,Data,Conto,U0000000
Dati del conto,Data,Valuta di base,EUR
Dettaglio eseguiti,Header,DataDiscriminator,Tipo di attivo,Valuta,Simbolo,Data/ora,Quantità,Prezzo eseguito,Prezzo di chiusura,Ricavo,Comm./tasse,Base,P/L realizzato,P/L MTM,Codice
Dettaglio eseguiti,Data,Order,Azioni,USD,EXMP,"2026-03-02, 10:00:00",2,50,51,-100,-1.25,101.25,0,2,O
Dettaglio eseguiti,Data,Order,Azioni,EUR,EXEU,"2026-03-03, 10:00:00",-1,200,210,200,-2,-170,28,0,C
Dettaglio eseguiti,Data,Order,Forex,USD,EUR.USD,"2026-03-01, 09:00:00",100,1.1,1.1,-110,0,,0,0,
Dettaglio eseguiti,SubTotal,,Azioni,USD,EXMP,,2,,,-100,-1.25,101.25,0,2,
Dettaglio eseguiti,Total,,Azioni,USD,,,,,,-100,-1.25,101.25,0,2,
Commissioni,Header,Subtitle,Valuta,Data,Descrizione,Importo
Commissioni,Data,Altre commissioni,USD,2026-04-10,EXMP(XX0000000001) Dividendo in contanti USD 0.50 per azione - FEE,-0.10
Commissioni,Data,Totale,,,,-0.10
Commissioni,Data,Totale in EUR,,,,-0.09
Dividendi,Header,Valuta,Data,Descrizione,Importo
Dividendi,Data,EUR,2026-05-20,EXEU(XX0000000002) Dividendo in contanti EUR 0.30 per azione (Rendimento del capitale),3
Dividendi,Data,Totale,,,3
Dividendi,Data,USD,2026-04-10,EXMP(XX0000000001) Dividendo in contanti USD 0.50 per azione (Dividendo ordinario),1.00
Dividendi,Data,Totale,,,1.00
Dividendi,Data,Totale in EUR,,,0.80
Dividendi,Data,Totale Dividendi in EUR,,,3.80
Ritenute alla fonte,Header,Valuta,Data,Descrizione,Importo,Codice
Ritenute alla fonte,Data,USD,2026-04-10,EXMP(XX0000000001) Dividendo in contanti USD 0.50 per azione - US Imposte,-0.15,
Ritenute alla fonte,Data,Totale,,,-0.15,
Ritenute alla fonte,Data,Totale in EUR,,,-0.12,
Informazioni sullo strumento finanziario,Header,Tipo di attivo,Simbolo,Descrizione,Conid,ID titolo,Sottostante,Mercato finanziario,Moltiplicatore,Tipo,Codice
Informazioni sullo strumento finanziario,Data,Azioni,EXMP,EXAMPLE CORP,1,XX0000000001,EXMP,NASDAQ,1,COMMON,
Informazioni sullo strumento finanziario,Data,Azioni,EXEU,EXAMPLE EUROPE SPA,2,XX0000000002,EXEU,BVME,1,COMMON,
"""

ENGLISH = """Statement,Header,Field Name,Field Value
Statement,Data,BrokerName,Interactive Brokers LLC
Account Information,Header,Field Name,Field Value
Account Information,Data,Base Currency,EUR
Trades,Header,DataDiscriminator,Asset Category,Currency,Symbol,Date/Time,Quantity,T. Price,C. Price,Proceeds,Comm/Fee,Basis,Realized P/L,MTM P/L,Code
Trades,Data,Order,Stocks,USD,EXMP,"2026-03-02, 10:00:00",2,50,51,-100,-1.25,101.25,0,2,O
Trades,Data,Order,Stocks,EUR,EXEU,"2026-03-03, 10:00:00",-1,200,210,200,-2,-170,28,0,C
Fees,Header,Subtitle,Currency,Date,Description,Amount
Fees,Data,Other Fees,USD,2026-04-10,EXMP(XX0000000001) Cash Dividend USD 0.50 per Share - FEE,-0.10
Fees,Data,Total,,,,-0.10
Fees,Data,Total in EUR,,,,-0.09
Dividends,Header,Currency,Date,Description,Amount
Dividends,Data,EUR,2026-05-20,EXEU(XX0000000002) Cash Dividend EUR 0.30 per Share (Return of Capital),3
Dividends,Data,Total,,,3
Dividends,Data,USD,2026-04-10,EXMP(XX0000000001) Cash Dividend USD 0.50 per Share (Ordinary Dividend),1.00
Dividends,Data,Total,,,1.00
Dividends,Data,Total in EUR,,,0.80
Dividends,Data,Total Dividends in EUR,,,3.80
Withholding Tax,Header,Currency,Date,Description,Amount,Code
Withholding Tax,Data,USD,2026-04-10,EXMP(XX0000000001) Cash Dividend USD 0.50 per Share - US Tax,-0.15,
Withholding Tax,Data,Total,,,-0.15,
Withholding Tax,Data,Total in EUR,,,-0.12,
Financial Instrument Information,Header,Asset Category,Symbol,Description,Conid,Security ID,Underlying,Listing Exch,Multiplier,Type,Code
Financial Instrument Information,Data,Stocks,EXMP,EXAMPLE CORP,1,XX0000000001,EXMP,NASDAQ,1,COMMON,
Financial Instrument Information,Data,Stocks,EXEU,EXAMPLE EUROPE SPA,2,XX0000000002,EXEU,BVME,1,COMMON,
"""


def no_rate(amount: Decimal, currency: str, day) -> Decimal | None:
    raise AssertionError("the statement's own EUR totals should convert every row")


def write(root: Path, name: str, text: str) -> Path:
    path = root / name
    path.write_text(text, encoding="utf-8")
    return path


def by_type(rows: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["event_type"], []).append(row)
    return grouped


class ActivityStatementTest(unittest.TestCase):
    def read(self, text: str) -> dict[str, list[dict]]:
        with tempfile.TemporaryDirectory() as temporary, collect_import_issues() as issues:
            rows = read_activity_statement(write(Path(temporary), "statement.csv", text), no_rate)
        self.assertEqual(issues.warnings(), [])
        self.assertFalse(issues.blocking)
        return by_type(rows)

    def test_detected_as_interactive_brokers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, text in (("it.csv", ITALIAN), ("en.csv", ENGLISH)):
                path = write(root, name, text)
                self.assertEqual(detect_statement_source(path), "interactive_brokers")
                self.assertEqual(detect_statement_source(path, "interactive_brokers"), "interactive_brokers")

    def test_trades_keep_their_currency_and_cash_effect(self) -> None:
        trades = {row["asset"]: row for row in self.read(ITALIAN)["trade"]}
        self.assertEqual(set(trades), {"EXAMPLE CORP", "EXAMPLE EUROPE SPA"})  # the FX conversion is not a holding
        buy, sale = trades["EXAMPLE CORP"], trades["EXAMPLE EUROPE SPA"]
        self.assertEqual((buy["currency"], buy["isin"], buy["description"]), ("USD", "XX0000000001", "Acquisto"))
        self.assertEqual((buy["quantity"], buy["price"], buy["amount"], buy["fees"]), (2, 50, Decimal("-101.25"), Decimal("1.25")))
        self.assertEqual((sale["quantity"], sale["amount"], sale["description"]), (-1, Decimal(198), "Vendita"))

    def test_dividends_are_net_of_withholding_in_eur_from_the_statement_totals(self) -> None:
        rows = self.read(ITALIAN)
        dividends = {row["isin"]: row for row in rows["dividend"]}
        foreign = dividends["XX0000000001"]
        # 1.00 USD gross at the block's 0.80, less 0.15 USD withheld at the tax block's 0.80.
        self.assertEqual((foreign["amount"], foreign["tax"], foreign["currency"]), (Decimal("0.68"), Decimal("0.12"), "EUR"))
        self.assertEqual(foreign["asset"], "EXAMPLE CORP")
        domestic = dividends["XX0000000002"]
        self.assertEqual((domestic["amount"], domestic["tax"]), (Decimal(3), 0))
        self.assertEqual([(row["amount"], row["description"]) for row in rows["dividend_tax"]],
                         [(Decimal("0.12"), "Dividend withholding - EXAMPLE CORP")])
        self.assertEqual([row["amount"] for row in rows["cost"]], [Decimal("0.09")])  # the ADR fee, a cost not a tax

    def test_english_statement_reads_the_same(self) -> None:
        def comparable(rows: dict[str, list[dict]]) -> dict[str, list[tuple]]:
            return {
                kind: sorted((str(row["occurred_on"]), row.get("isin", ""), row["amount"], row.get("tax")) for row in items)
                for kind, items in rows.items()
            }

        self.assertEqual(comparable(self.read(ENGLISH)), comparable(self.read(ITALIAN)))

    def test_row_identity_does_not_depend_on_the_statement_rate(self) -> None:
        later = ITALIAN.replace("Dividendi,Data,Totale in EUR,,,0.80", "Dividendi,Data,Totale in EUR,,,0.90")
        ids = [
            sorted(row["metadata"]["transaction_id"] for row in self.read(text)["dividend"])
            for text in (ITALIAN, later)
        ]
        self.assertEqual(ids[0], ids[1])

    def test_a_block_without_eur_total_uses_the_market_rate(self) -> None:
        text = ITALIAN.replace("Dividendi,Data,Totale in EUR,,,0.80\n", "")
        with tempfile.TemporaryDirectory() as temporary:
            rows = read_activity_statement(write(Path(temporary), "s.csv", text), lambda amount, currency, day: amount / 2)
        dividend = next(row for row in rows if row["event_type"] == "dividend" and row["isin"] == "XX0000000001")
        self.assertEqual(dividend["amount"], Decimal("0.38"))  # 1.00 / 2 less the 0.12 withheld

    def test_deposits_are_reported_as_not_imported(self) -> None:
        text = ITALIAN + "Depositi e prelievi,Header,Valuta,Data di regolamento,Descrizione,Importo\n" \
                         "Depositi e prelievi,Data,EUR,2026-02-01,Bonifico,100\n"
        with tempfile.TemporaryDirectory() as temporary, collect_import_issues() as issues:
            read_activity_statement(write(Path(temporary), "s.csv", text), no_rate)
        self.assertEqual(issues.warnings(), ["1 row skipped: Interactive Brokers deposits and withdrawals are not imported yet"])


class ActivityStatementImportTest(unittest.TestCase):
    PDF_TEXT = "Azioni\nUSD\nU0000000 EXMP 2026-03-02, 10:00:00 2026-03-04 - BUY 2 50 -100.00 -1.25 0.00\n"

    def ledger(self, root: Path) -> ExitStack:
        stack = ExitStack()
        for target, name, value in (
            (app, "ROOT_DIR", root / "sources"),
            (app, "MOVEMENT_DATABASE", root / "private" / "movements.sqlite3"),
            (app, "_movement_store", None),
            (app, "_legacy_imported_portfolios", {app.PRIMARY_PORTFOLIO_ID}),
            (app, "pdf_text", lambda path: self.PDF_TEXT),
            (app, "parse_ib_instruments", lambda text: {"EXMP": {"asset": "EXMP", "isin": "XX0000000001"}}),
        ):
            stack.enter_context(patch.object(target, name, value))
        return stack

    def test_imports_into_the_ledger_and_the_dashboard_reads_dividends_and_frictions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.ledger(root):
                result = app.import_statement_path(write(root, "activity.csv", ITALIAN), original_name="activity.csv")
                again = app.import_statement_path(write(root, "copy.csv", ITALIAN + "\n"), original_name="copy.csv")
                dividends = app.read_ledger_dividends()
                frictions = app.read_ledger_frictions()
                trades, _source = app.read_ledger_trades()

        self.assertEqual((result["status"], result["source"]), ("imported", "interactive_brokers"))
        self.assertTrue(result["stored_path"].startswith("sources/broker_exports/interactive_brokers/"))
        self.assertEqual(again["movements"], 0)  # a second copy of the same rows adds nothing
        self.assertEqual(sorted(item.amount_eur for item in dividends), [Decimal("0.68"), Decimal(3)])
        self.assertEqual({item.broker for item in dividends}, {"Interactive Brokers"})
        self.assertEqual(sorted((item.event_type, item.amount_eur) for item in frictions),
                         [("cost", Decimal("0.09")), ("dividend_tax", Decimal("0.12"))])
        self.assertEqual(len(trades), 2)

    def test_a_trade_already_stored_from_the_pdf_is_not_stored_again(self) -> None:
        for order in (("confirmations.pdf", "activity.csv"), ("activity.csv", "confirmations.pdf")):
            with self.subTest(order=order), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                files = {"confirmations.pdf": root / "confirmations.pdf", "activity.csv": write(root, "activity.csv", ITALIAN)}
                files["confirmations.pdf"].write_bytes(b"%PDF synthetic")
                with self.ledger(root):
                    results = [app.import_statement_path(files[name], original_name=name, requested_source="interactive_brokers")
                               for name in order]
                    trades = [row for row in app.get_movement_store().movements() if row["event_type"] == "trade"]

                self.assertEqual(results[1]["duplicates"], 1)
                self.assertEqual(sorted(Decimal(row["quantity"]) for row in trades), [Decimal(-1), Decimal(2)])


if __name__ == "__main__":
    unittest.main()
