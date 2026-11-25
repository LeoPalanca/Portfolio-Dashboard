"""Movers count what a window did to the money in a position, not the stock's move times today's shares."""

from __future__ import annotations

import unittest
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

import app

TODAY = date.today()  # noqa: DTZ011 - variations are measured back from today


def trade(day: date, quantity: str, amount: str, source: str = "test") -> app.Trade:
    qty = Decimal(quantity)
    cash = Decimal(amount)
    return app.Trade(
        asset="Example Corp", isin="XX0000000001", broker="Example", action="Acquisto" if qty > 0 else "Vendita",
        currency_hint="EUR", cash_currency="EUR", date=day, price=abs(cash / qty) if qty and cash else Decimal(0),
        quantity=abs(qty), quantity_diff=qty, total_spend=-cash if qty > 0 else cash, fees=Decimal(0), tax=Decimal(0),
        grand_total=-cash if qty > 0 else cash, grand_total_present=bool(cash), source=source,
    )


def history(before: float, recent: float, change_day: date) -> dict:
    """Price `before` up to `change_day` (exclusive), then `recent`."""

    prices = {}
    day = TODAY - timedelta(days=45)
    while day <= TODAY:
        prices[day.isoformat()] = before if day < change_day else recent
        day += timedelta(days=1)
    return {"status": "priced", "currency": "EUR", "prices": prices}


def variations(quantity: str, value: str, trades: list[app.Trade], prices: dict, splits: dict | None = None) -> dict:
    with patch.object(app, "fetch_history", return_value=prices):
        return app.compute_position_variations(
            asset="Example Corp", symbol="EXMP", currency="EUR", quantity=Decimal(quantity),
            current_value_eur=Decimal(value), is_crypto_wallet=False, known_splits=splits, trades=trades,
        )


class PositionMoversTest(unittest.TestCase):
    def test_a_position_bought_inside_the_window_counts_from_what_was_paid(self) -> None:
        # The stock fell from 150 to 100 before the buy; the money only saw 100 -> 101.
        prices = history(150.0, 100.0, TODAY - timedelta(days=10))
        bought = TODAY - timedelta(days=3)
        month = variations("4", "404", [trade(bought, "4", "400")], prices)["1m"]
        self.assertEqual(month["amount"], 4.0)
        self.assertEqual(month["pct"], 1.0)
        self.assertEqual(month["price_pct"], -32.67)

    def test_buys_and_sales_in_the_window_are_not_gains_or_losses(self) -> None:
        prices = history(100.0, 110.0, TODAY - timedelta(days=5))
        held = trade(TODAY - timedelta(days=60), "2", "180")
        topped_up = variations("4", "480", [held, trade(TODAY - timedelta(days=3), "2", "220")], prices)["1w"]
        self.assertEqual(topped_up["amount"], 60.0)  # 480 - 200 held - 220 paid
        self.assertEqual(topped_up["pct"], 14.29)  # on the 420 at stake
        self.assertEqual(topped_up["price_pct"], 20.0)

        held = trade(TODAY - timedelta(days=60), "4", "360")
        trimmed = variations("2", "240", [held, trade(TODAY - timedelta(days=3), "-2", "220")], prices)["1w"]
        self.assertEqual(trimmed["amount"], 60.0)  # 240 - 400 held + 220 received
        self.assertEqual(trimmed["pct"], 15.0)

    def test_without_trades_in_the_window_it_is_the_price_move_on_the_shares(self) -> None:
        prices = history(100.0, 90.0, TODAY - timedelta(days=5))
        week = variations("3", "270", [trade(TODAY - timedelta(days=60), "3", "250")], prices)["1w"]
        self.assertEqual(week, {"pct": -10.0, "amount": -30.0, "price_pct": -10.0})

    def test_a_split_inside_the_window_does_not_inflate_the_shares_held_before(self) -> None:
        split_day = TODAY - timedelta(days=4)
        prices = history(50.0, 50.0, split_day)  # split-adjusted history
        trades = [
            trade(TODAY - timedelta(days=6), "1", "100"),
            trade(split_day, "1", "0", source="fineco_corporate_action"),
        ]
        week = variations("2", "104", trades, prices, splits={split_day.isoformat(): 2.0})["1w"]
        self.assertEqual(week["amount"], 4.0)
        self.assertEqual(week["pct"], 4.0)

    def test_without_a_start_price_only_a_position_opened_in_the_window_is_measured(self) -> None:
        empty = {"status": "history_error", "prices": {}}
        opened = variations("1", "105", [trade(TODAY - timedelta(days=2), "1", "100")], empty)["1w"]
        self.assertEqual(opened["amount"], 5.0)
        self.assertIsNone(opened["price_pct"])
        held = variations("1", "105", [trade(TODAY - timedelta(days=60), "1", "100")], empty)["1w"]
        self.assertEqual(held, {"pct": 0.0, "amount": 0.0})

    def test_enrich_positions_hands_each_position_its_own_trades(self) -> None:
        mine = trade(TODAY - timedelta(days=2), "1", "100")
        other = app.Trade(**{**mine.__dict__, "asset": "Other Corp", "isin": "XX0000000002"})
        position = {"asset": "Example Corp", "isin": "XX0000000001", "quantity": 1.0, "cost_basis_eur": 100.0, "is_open": True}
        seen: dict = {}

        def capture(**kwargs):
            seen.update(kwargs)
            return {}

        with (
            patch.object(app, "read_exposures", return_value={}),
            patch.object(app, "resolve_isin", return_value={"status": "resolved", "symbol": "EXMP"}),
            patch.object(app, "fetch_price", return_value={"status": "priced", "price": 105.0, "currency": "EUR"}),
            patch.object(app, "fx_to_eur", return_value={"rate": 1.0}),
            patch.object(app, "compute_position_variations", side_effect=capture),
        ):
            app.enrich_positions([position], {}, trades=[mine, other])
        self.assertEqual(seen.get("trades"), [mine])


if __name__ == "__main__":
    unittest.main()
