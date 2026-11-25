"""Taxes & costs: the Fineco capital-gain estimate, pre-tax realised P/L, signs, after-tax value."""

from __future__ import annotations

import io
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import app

TR_HEADER = (
    "datetime,date,account_type,category,type,asset_class,name,symbol,shares,price,amount,fee,tax,currency,"
    "original_amount,original_currency,fx_rate,description,transaction_id,counterparty_name,counterparty_iban,"
    "payment_reference,mcc_code\n"
)


def trade(
    day: str,
    quantity: str,
    cash: str,
    *,
    asset: str = "Example Stock",
    isin: str = "XX0000000001",
    broker: str = "Fineco",
    tax: str = "0",
    source: str = "fineco",
) -> app.Trade:
    """A buy (positive quantity) or sale (negative quantity) for ``cash`` EUR."""

    qty = Decimal(quantity)
    amount = Decimal(cash)
    signed_cash = amount if qty < 0 else -amount
    return app.Trade(
        asset=asset,
        isin=isin,
        broker=broker,
        action="Vendita" if qty < 0 else "Acquisto",
        currency_hint="EUR",
        cash_currency="EUR",
        date=date.fromisoformat(day),
        price=amount / abs(qty),
        quantity=abs(qty),
        quantity_diff=qty,
        total_spend=signed_cash,
        fees=Decimal(0),
        tax=Decimal(tax),
        grand_total=signed_cash,
        grand_total_present=True,
        source=source,
    )


FUND = {"asset": "Example World UCITS ETF", "isin": "XX0000000009"}


def by_name(item: app.Trade) -> bool:
    return item.asset == FUND["asset"]


def taxes(trades: list[app.Trade]) -> list[Decimal]:
    return [item["tax_eur"] for item in app.estimate_fineco_sell_taxes(trades, by_name)]


class FinecoCapitalGainRateTest(unittest.TestCase):
    def test_gain_is_taxed_at_26_percent_not_grossed_up(self) -> None:
        trades = [trade("2026-01-05", "10", "1000"), trade("2026-03-02", "-10", "2000")]
        estimates = app.estimate_fineco_sell_taxes(trades, by_name)
        events = app.inferred_fineco_sell_tax_events(trades, estimates)
        summary = app.summarize_trades(trades, estimates)

        self.assertEqual(estimates[0]["tax_eur"], Decimal("260.00"))
        self.assertEqual([event.amount_eur for event in events], [Decimal("260.00")])
        self.assertTrue(events[0].estimated)
        self.assertEqual(summary["totals"]["taxes"], 260.0)
        self.assertEqual(summary["totals"]["realized_pl"], 1000.0)

    def test_dividends_keep_the_gross_up(self) -> None:
        self.assertEqual(app.fineco_dividend_tax_from_net(Decimal("74")), Decimal("26"))
        self.assertEqual(app.capital_gain_tax(Decimal("74")), Decimal("19.24"))


class FinecoLossCreditTest(unittest.TestCase):
    def test_stock_loss_offsets_a_later_stock_gain(self) -> None:
        trades = [
            trade("2026-01-05", "10", "1000"),
            trade("2026-02-02", "-10", "500"),
            trade("2026-03-02", "10", "1000", asset="Other Stock", isin="XX0000000002"),
            trade("2026-04-01", "-10", "1500", asset="Other Stock", isin="XX0000000002"),
        ]
        self.assertEqual(taxes(trades), [Decimal(0), Decimal(0)])

    def test_etf_loss_offsets_a_stock_gain(self) -> None:
        trades = [
            trade("2026-01-05", "10", "1000", **FUND),
            trade("2026-02-02", "-10", "800", **FUND),
            trade("2026-03-02", "10", "1000"),
            trade("2026-04-01", "-10", "1500"),
        ]
        estimates = app.estimate_fineco_sell_taxes(trades, by_name)
        self.assertEqual(estimates[1]["loss_offset_eur"], Decimal(200))
        self.assertEqual(estimates[1]["tax_eur"], Decimal("78.00"))  # 26% of 500 - 200
        events = app.inferred_fineco_sell_tax_events(trades, estimates)
        self.assertEqual(len(events), 1)
        self.assertIn("after 200.00 EUR loss offset", events[0].description)

    def test_stock_loss_does_not_offset_an_etf_gain(self) -> None:
        trades = [
            trade("2026-01-05", "10", "1000"),
            trade("2026-02-02", "-10", "500"),
            trade("2026-03-02", "10", "1000", **FUND),
            trade("2026-04-01", "-10", "1500", **FUND),
            # The credit is still there for a later stock gain.
            trade("2026-05-04", "10", "1000", asset="Other Stock", isin="XX0000000002"),
            trade("2026-06-01", "-10", "1300", asset="Other Stock", isin="XX0000000002"),
        ]
        self.assertEqual(taxes(trades), [Decimal(0), Decimal("130.00"), Decimal(0)])

    def test_oldest_credit_is_used_first_and_partly(self) -> None:
        trades = [
            trade("2020-01-06", "10", "1000"),
            trade("2020-02-03", "-10", "900"),  # 100 credit, expires end of 2024
            trade("2021-01-04", "10", "1000", asset="Other Stock", isin="XX0000000002"),
            trade("2021-02-01", "-10", "700", asset="Other Stock", isin="XX0000000002"),  # 300, end of 2025
            trade("2024-06-03", "10", "1000", asset="Third Stock", isin="XX0000000003"),
            trade("2024-07-01", "-10", "1250", asset="Third Stock", isin="XX0000000003"),  # 100 + 150 used
            trade("2025-03-03", "10", "1000", asset="Fourth Stock", isin="XX0000000004"),
            trade("2025-04-01", "-10", "1200", asset="Fourth Stock", isin="XX0000000004"),  # 150 left
        ]
        estimates = app.estimate_fineco_sell_taxes(trades, by_name)
        self.assertEqual(estimates[2]["loss_offset_eur"], Decimal(250))
        self.assertEqual(estimates[2]["tax_eur"], Decimal(0))
        self.assertEqual(estimates[3]["loss_offset_eur"], Decimal(150))
        self.assertEqual(estimates[3]["tax_eur"], Decimal("13.00"))

    def test_credit_expires_after_the_fourth_year(self) -> None:
        loss = [trade("2020-01-06", "10", "1000"), trade("2020-02-03", "-10", "500")]
        last_day = loss + [
            trade("2024-12-02", "10", "1000", asset="Other Stock", isin="XX0000000002"),
            trade("2024-12-31", "-10", "1500", asset="Other Stock", isin="XX0000000002"),
        ]
        expired = loss + [
            trade("2024-12-02", "10", "1000", asset="Other Stock", isin="XX0000000002"),
            trade("2025-01-02", "-10", "1500", asset="Other Stock", isin="XX0000000002"),
        ]
        self.assertEqual(taxes(last_day)[-1], Decimal(0))
        self.assertEqual(taxes(expired)[-1], Decimal("130.00"))

    def test_split_booked_as_shares_out_and_in_is_not_a_loss(self) -> None:
        corporate = {"source": "fineco_corporate_action"}
        trades = [
            trade("2026-01-05", "10", "1000"),
            trade("2026-02-02", "-10", "0", **corporate),
            trade("2026-02-02", "1", "0", **corporate),
            trade("2026-03-02", "-1", "1500"),
        ]
        self.assertEqual(taxes(trades), [Decimal("130.00")])


class FinecoCostPoolTest(unittest.TestCase):
    def test_fineco_uses_its_own_average_cost(self) -> None:
        trades = [
            trade("2026-01-05", "10", "1000"),
            trade("2026-01-06", "10", "2000", broker="Trade Republic", source="trade_republic"),
            trade("2026-03-02", "-10", "1500"),
        ]
        estimates = app.estimate_fineco_sell_taxes(trades, by_name)
        self.assertEqual(estimates[0]["gain_eur"], Decimal(500))
        self.assertEqual(estimates[0]["tax_eur"], Decimal("130.00"))
        # The displayed realised P/L stays on the cross-broker average (150 a share).
        self.assertEqual(app.summarize_trades(trades, estimates)["totals"]["realized_pl"], 0.0)

    def test_shares_transferred_in_use_the_cross_broker_average(self) -> None:
        trades = [
            trade("2026-01-05", "5", "500"),
            trade("2026-01-06", "5", "1500", broker="Trade Republic", source="trade_republic"),
            trade("2026-03-02", "-10", "2500"),  # 5 on record at 100, 5 at the 200 average
        ]
        self.assertEqual(app.estimate_fineco_sell_taxes(trades, by_name)[0]["gain_eur"], Decimal(1000))

    def test_filtered_view_keeps_the_whole_ledger_estimate(self) -> None:
        ledger = [
            trade("2026-01-05", "10", "2000", broker="Trade Republic", source="trade_republic"),
            trade("2026-03-02", "-10", "2500"),  # shares transferred in from Trade Republic
        ]
        estimates = app.estimate_fineco_sell_taxes(ledger, by_name)
        fineco_only = ledger[1:]
        events = app.inferred_fineco_sell_tax_events(fineco_only, estimates)
        self.assertEqual([event.amount_eur for event in events], [Decimal("130.00")])
        self.assertEqual(app.summarize_trades(fineco_only, estimates)["totals"]["taxes"], 130.0)
        self.assertEqual(app.inferred_fineco_sell_tax_events(ledger[:1], estimates), [])
        # Without the ledger the view has no cost for those shares.
        self.assertEqual(app.inferred_fineco_sell_tax_events(fineco_only)[0].amount_eur, Decimal("650.00"))


class FundClassificationTest(unittest.TestCase):
    def classify(self, asset: str, isin: str = "XX0000000001", rows: list[str] | None = None, funds: set[str] | None = None) -> bool:
        exposures = {app.exposure_key(asset, isin): [{"asset_class": value} for value in rows]} if rows else {}
        return app.is_fund_for_tax(asset, isin, exposures, funds or set())

    def test_signals(self) -> None:
        self.assertTrue(self.classify("Example World UCITS ETF"))
        self.assertTrue(self.classify("ISHS EXAMPLE USD-ACC"))
        self.assertTrue(self.classify("Example Basket", rows=["Equity", "Fixed Income"]))
        self.assertTrue(self.classify("Example Money Market", rows=["Cash equivalent"]))
        self.assertTrue(self.classify("Plain Name", funds={"XX0000000001"}))
        self.assertFalse(self.classify("Example Physical Gold ETC"))
        self.assertFalse(self.classify("Example Gold Tracker", rows=["Gold"]))
        self.assertFalse(self.classify("Example MSCI Index Corp", rows=["Single share"]))
        self.assertFalse(self.classify("Accentor Holdings"))
        # Nothing to go on: treated as a single stock.
        self.assertFalse(self.classify("Plain Name"))


class TradeRepublicRealizedBeforeTaxTest(unittest.TestCase):
    def test_withheld_tax_is_added_back_to_realised_pl_only(self) -> None:
        export = TR_HEADER + (
            ",2026-01-05,,TRADING,BUY,,Example Stock,XX0000000001,10,100,-1000,-1,0,EUR,,,,Buy,tx-1,,,,\n"
            ",2026-03-02,,TRADING,SELL,,Example Stock,XX0000000001,-10,150,1500,-1,-130,EUR,,,,Sell,tx-2,,,,\n"
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "tr.csv"
            path.write_text(export, encoding="utf-8")
            trades = app.read_trade_republic_trades(path)

        sale = next(item for item in trades if item.quantity_diff < 0)
        self.assertEqual((sale.grand_total, sale.tax), (Decimal(1369), Decimal(130)))  # cash is net of the tax
        totals = app.summarize_trades(trades)["totals"]
        self.assertEqual(totals["realized_pl"], 498.0)  # 1,499 before tax - 1,001 cost
        self.assertEqual(totals["proceeds"], 1369.0)
        self.assertEqual(totals["net_contributions"], -368.0)
        self.assertEqual(totals["taxes"], 130.0)
        self.assertEqual(app.summarize_net_contributions(trades)["total_sells_eur"], 1369.0)


class FrictionSignTest(unittest.TestCase):
    def test_refunds_and_reversals_lower_taxes_through_the_ledger(self) -> None:
        export = TR_HEADER + (
            ",2026-01-02,,,TAX_OPTIMIZATION,,,,,,0,,-10.00,EUR,,,,Tax,tx-1,,,,\n"
            ",2026-02-02,,,TAX_OPTIMIZATION,,,,,,0,,4.00,EUR,,,,Tax refund,tx-2,,,,\n"
            ",2026-03-02,,,DIVIDEND,,Example AG,XX0000000002,2,,1.00,,-0.26,EUR,,,,Cash Dividend,tx-3,,,,\n"
            ",2026-03-09,,,DIVIDEND,,Example AG,XX0000000002,2,,-1.00,,0.26,EUR,,,,Cash Dividend,tx-4,,,,\n"
        )
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
                    data={"source": "trade_republic", "file": (io.BytesIO(export.encode()), "tr.csv")},
                    content_type="multipart/form-data",
                )
                self.assertEqual(response.status_code, 200, response.get_json())
                events = app.read_ledger_frictions()

        self.assertEqual(sorted(event.amount_eur for event in events), [Decimal("-4.00"), Decimal("-0.26"), Decimal("0.26"), Decimal("10.00")])
        frictions = app.summarize_frictions(events, None)
        self.assertEqual(frictions["total_taxes_eur"], 6.0)
        self.assertEqual(frictions["dividend_tax_eur"], 0.0)
        self.assertEqual(frictions["estimated_taxes_eur"], 0.0)


class FrictionSummaryTest(unittest.TestCase):
    def event(self, kind: str, amount: str, estimated: bool = False, broker: str = "Fineco") -> app.FrictionEvent:
        return app.FrictionEvent(broker, kind, date(2026, 3, 2), Decimal(amount), "Example", estimated=estimated)

    def test_withheld_and_estimated_taxes_are_split(self) -> None:
        frictions = app.summarize_frictions(
            [
                self.event("tax", "130", estimated=True),
                self.event("dividend_tax", "26", estimated=True),
                self.event("tax", "50", broker="Trade Republic"),
                self.event("cost", "5", broker="Trade Republic"),
            ],
            0,
        )
        self.assertEqual(frictions["total_taxes_eur"], 206.0)
        self.assertEqual(frictions["estimated_taxes_eur"], 156.0)
        self.assertEqual(frictions["withheld_taxes_eur"], 50.0)
        self.assertEqual(frictions["total_drag_eur"], 211.0)
        labels = {row["type_label"] for row in frictions["rows"]}
        self.assertEqual(labels, {"Tax (estimated)", "Dividend tax (estimated)", "Tax", "Cost"})

    def test_after_tax_value_deducts_tax_on_open_gains_only(self) -> None:
        positions = [
            {"is_open": True, "unrealized_pl_eur": 1000.0, "market_value_eur": 6000.0, "cost_basis_eur": 5000.0},
            {"is_open": True, "unrealized_pl_eur": -500.0, "market_value_eur": 3500.0, "cost_basis_eur": 4000.0},
            {"is_open": True, "market_value_eur": 500.0, "cost_basis_eur": 400.0, "pricing_status": "snapshot"},
            {"is_open": False, "unrealized_pl_eur": None, "display_pl_eur": 900.0, "cost_basis_eur": 0.0},
        ]
        frictions = app.summarize_frictions([self.event("cost", "50"), self.event("tax", "70")], 10000, positions)
        self.assertEqual(frictions["estimated_exit_tax_eur"], 286.0)  # 26% of 1,000 + 26% of 100, no offset
        self.assertEqual(frictions["net_liquidation_eur"], 9714.0)  # fees and taxes already paid are not deducted again


class PenceCashTest(unittest.TestCase):
    def test_gbx_cash_is_divided_by_100(self) -> None:
        history = {"status": "priced", "prices": {"2026-03-02": 1.2}}
        with patch.object(app, "fetch_history", return_value=history):
            self.assertEqual(app.convert_cash_to_eur(Decimal(1000), "GBX", date(2026, 3, 2)), (Decimal("12.0"), False))
            self.assertEqual(app.convert_cash_to_eur(Decimal(1000), "GBp", date(2026, 3, 2)), (Decimal("12.0"), False))
            self.assertEqual(app.convert_cash_to_eur(Decimal(10), "GBP", date(2026, 3, 2)), (Decimal("12.0"), False))


if __name__ == "__main__":
    unittest.main()
