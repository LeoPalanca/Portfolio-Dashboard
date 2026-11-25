"""Numbers that used to change without warning: wallet wipes, splits, eToro sales, pence quotes."""

from __future__ import annotations

import argparse
import csv
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import ClassVar
from unittest.mock import patch
from urllib.error import HTTPError

from openpyxl import Workbook

import app
import crypto_wallet_fetcher as wallets
from src.portfolio_dashboard.domain.issues import collect_import_issues


def trade(day: str, quantity: str, amount: str, source: str = "fineco", asset: str = "EXAMPLE") -> app.Trade:
    quantity_value = Decimal(quantity)
    return app.Trade(
        asset=asset,
        isin="",
        broker="Fineco",
        action="Acquisto" if quantity_value > 0 else "Vendita",
        currency_hint="EUR",
        cash_currency="EUR",
        date=date.fromisoformat(day),
        price=abs(Decimal(amount) / quantity_value) if quantity_value else Decimal(0),
        quantity=abs(quantity_value),
        quantity_diff=quantity_value,
        total_spend=Decimal(amount),
        fees=Decimal(0),
        tax=Decimal(0),
        grand_total=Decimal(amount),
        grand_total_present=True,
        source=source,
    )


CORPORATE = "fineco_corporate_action"


class WalletFetchFailureTest(unittest.TestCase):
    CONFIG = "person,wallet_label,address,chain,asset,symbol,source,enabled\n,Ledger,EQexample,ton,TON,TON-EUR,tonapi,1\n"

    def run_update(self, folder: Path) -> None:
        args = argparse.Namespace(
            config=str(folder / "wallets.csv"),
            output=str(folder / "positions.csv"),
            transactions_output=str(folder / "transactions.csv"),
            binance_history=str(folder / "missing.csv"),
            cdp_key="",
            dry_run=False,
        )
        wallets.update(args)

    def test_a_rate_limited_fetch_keeps_the_last_balance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            (folder / "wallets.csv").write_text(self.CONFIG, encoding="utf-8")
            balance = {"balance": "12500000000"}
            with patch.object(wallets, "request_json", lambda url, headers=None: balance if "tonapi" in url else {"data": {"amount": "2"}}):
                self.run_update(folder)

            def too_many_requests(url: str, headers: dict | None = None) -> dict:
                raise HTTPError(url, 429, "Too Many Requests", {}, None)

            with patch.object(wallets, "request_json", too_many_requests):
                self.run_update(folder)
            with (folder / "positions.csv").open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["quantity"], rows[0]["market_value_eur"]), ("12.5", "25"))
        self.assertEqual(rows[0]["status"], "stale")
        self.assertIn("429", rows[0]["message"])

    def test_only_the_failed_network_is_replaced(self) -> None:
        previous = [
            {"source": "coinbase_cdp", "wallet_address": "0xabc", "asset": "USDC", "network": "base", "quantity": "5", "fetched_at": "t0"},
            {"source": "coinbase_cdp", "wallet_address": "0xabc", "asset": "USDC", "network": "ethereum", "quantity": "7", "fetched_at": "t0"},
        ]
        current = [
            {"source": "coinbase_cdp", "wallet_address": "0xabc", "asset": "USDC", "network": "base", "quantity": "6", "status": "ok"},
            {"source": "coinbase_cdp", "wallet_address": "0xabc", "asset": "USDC", "network": "ethereum", "quantity": "0", "status": "error", "message": "HTTP 429"},
        ]
        merged = wallets.keep_last_good_positions(current, previous)
        self.assertEqual([(row["network"], row["quantity"], row["status"]) for row in merged], [("base", "6", "ok"), ("ethereum", "7", "stale")])

    def test_failed_accounts_keep_their_transaction_audit(self) -> None:
        previous = [{"source": "coinbase_account", "asset": "ETH", "transaction_id": "a"}, {"source": "coinbase_account", "asset": "BTC", "transaction_id": "b"}]
        kept = wallets.keep_last_good_transactions([], previous, [{"source": "coinbase_account", "asset": "eth"}])
        self.assertEqual([row["transaction_id"] for row in kept], ["a"])


class SmallSplitTest(unittest.TestCase):
    PRICES: ClassVar[dict[str, float]] = {"2026-03-02": 100.0, "2026-03-03": 97.0, "2026-03-04": 99.0, "2026-03-05": 95.0, "2026-03-06": 96.0}

    def test_small_ratios_are_left_to_the_provider(self) -> None:
        events = {date(2026, 3, 5): 1.05}
        self.assertEqual(app.split_adjusted_prices(self.PRICES, events), self.PRICES)

    def test_adjusting_twice_changes_nothing(self) -> None:
        prices = {"2026-03-02": 300.0, "2026-03-03": 290.0, "2026-03-04": 297.0, "2026-03-05": 100.0, "2026-03-06": 101.0}
        events = {date(2026, 3, 5): 3.0}
        once = app.split_adjusted_prices(prices, events)
        self.assertAlmostEqual(once["2026-03-02"], 100.0)
        self.assertEqual(app.split_adjusted_prices(once, events), once)

    def test_a_ratio_near_one_no_longer_flips_the_history(self) -> None:
        events = {date(2026, 3, 5): 1.25}
        once = app.split_adjusted_prices(self.PRICES, events)
        self.assertEqual(once, self.PRICES)
        self.assertEqual(app.split_adjusted_prices(once, events), once)


class ReverseSplitTest(unittest.TestCase):
    HISTORY: ClassVar[list[app.Trade]] = [
        trade("2026-01-05", "100", "-1000"),
        trade("2026-04-01", "-100", "0", CORPORATE),
        trade("2026-04-01", "10", "0", CORPORATE),
    ]

    def test_a_reverse_split_is_not_a_loss(self) -> None:
        summary = app.summarize_trades(self.HISTORY)
        position = summary["positions"][0]
        self.assertEqual(summary["totals"]["realized_pl"], 0)
        self.assertEqual((position["quantity"], position["cost_basis_eur"], position["is_open"]), (10.0, 1000.0, True))

    def test_a_single_row_reverse_split_keeps_the_cost(self) -> None:
        summary = app.summarize_trades([trade("2026-01-05", "100", "-1000"), trade("2026-04-01", "-90", "0", CORPORATE)])
        self.assertEqual(summary["totals"]["realized_pl"], 0)
        self.assertEqual(summary["positions"][0]["cost_basis_eur"], 1000.0)

    def test_shares_written_off_to_zero_are_still_a_loss(self) -> None:
        summary = app.summarize_trades([trade("2026-01-05", "100", "-1000"), trade("2026-04-01", "-100", "0", CORPORATE)])
        self.assertEqual(summary["totals"]["realized_pl"], -1000)

    def test_history_is_restated_by_the_net_factor_of_the_day(self) -> None:
        adjusted = app.split_adjusted_trade_history(self.HISTORY)
        self.assertEqual(len(adjusted), 1)
        self.assertEqual(adjusted[0].quantity_diff, Decimal(10))
        self.assertEqual(app.corporate_action_split_events(self.HISTORY), {"EXAMPLE": {"2026-04-01": 0.1}})


def etoro_workbook(path: Path, closed: list[tuple]) -> None:
    workbook = Workbook()
    workbook.active.title = "Dividendi"
    workbook["Dividendi"].append(("Data di pagamento",) + ("",) * 13)
    workbook["Dividendi"].append(("02/02/2026", "Example Corp", 1, 1, "USD", "", "", 0.9, 15, 0.2, 0.18, "1001", "Azioni", "US0000000001"))
    activity = workbook.create_sheet("Attività account")
    activity.append(("Data", "Tipologia", "Dettagli", "Importo", "Unità", "", "", "", "ID Posizione", "Tipo di asset", "NWA"))
    activity.append(("05/01/2026 10:00:00", "Apri posizione", "EXA/USD", 500, 10, "", "", "", "1001", "Azioni", ""))
    activity.append(("06/01/2026 10:00:00", "Apri posizione", "OTH/USD", 300, 3, "", "", "", "1002", "Azioni", ""))
    sheet = workbook.create_sheet("Posizioni chiuse")
    sheet.append(("ID Posizione",) + ("",) * 22)
    for row in closed:
        sheet.append(row)
    workbook.save(path)


def closed_row(position_id: str, side: str, amount: float, units: float, profit: float, closed_at: str = "10/03/2026 15:00:00") -> tuple:
    row = [""] * 23
    row[0], row[1], row[2], row[3], row[4] = position_id, "Acquista Example", side, amount, units
    row[5], row[6], row[10], row[21] = "05/01/2026 10:00:00", closed_at, profit, "US0000000001"
    return tuple(row)


class EtoroClosedPositionsTest(unittest.TestCase):
    def test_closed_positions_become_sales_of_the_opened_asset(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "etoro.xlsx"
            unknown = list(closed_row("9999", "Long", 100, 1, 5))
            unknown[21] = "US0000000009"
            etoro_workbook(path, [closed_row("1001", "Long", 500, 10, 120), closed_row("1002", "Short", 300, 3, 10), tuple(unknown)])
            with collect_import_issues() as issues:
                trades = app.read_etoro_trades(path)

        sales = [item for item in trades if item.quantity_diff < 0]
        self.assertEqual(len(sales), 1)
        sale = sales[0]
        self.assertEqual((sale.asset, sale.isin, sale.date), ("EXA", "US0000000001", date(2026, 3, 10)))
        self.assertEqual((sale.quantity_diff, sale.grand_total, sale.action), (Decimal(-10), Decimal(620), "Vendita"))
        self.assertEqual(
            issues.warnings(), ["2 rows skipped: eToro short position 1002; eToro closed position 9999 opened outside this statement"]
        )

        with patch.object(app, "convert_cash_to_eur", lambda amount, currency, day: (amount, False)):
            summary = app.summarize_trades(trades)
        by_asset = {position["asset"]: position for position in summary["positions"]}
        self.assertFalse(by_asset["EXA"]["is_open"])
        self.assertEqual(by_asset["EXA"]["realized_pl_eur"], 120.0)
        self.assertTrue(by_asset["OTH"]["is_open"])


class PenceQuoteTest(unittest.TestCase):
    def test_pence_quotes_are_converted_as_hundredths_of_a_pound(self) -> None:
        with patch.object(app, "fetch_price", lambda symbol, refresh=False: {"status": "priced", "price": 1.2}):
            pounds = app.fx_to_eur("GBP")["rate"]
            pence = app.fx_to_eur("GBp")["rate"]
        self.assertAlmostEqual(pounds, 1.2)
        self.assertAlmostEqual(pence, 0.012)


if __name__ == "__main__":
    unittest.main()
