"""Synthetic order lifecycle tests. No network connection or live orders."""

import asyncio
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock, patch

import pytest

from scripts.ibkr_orders import OrderBlocked, OrderDesk, draft, profit_target


def test_drafts_and_tick_rounding():
    assert draft({"symbol": "AAPL", "quantity": 1, "limit_price": 100.01})["quantity"] == 1
    assert profit_target(100.01, 0.01) == 115.02
    for change in (
        {"symbol": "FAKE"},
        {"quantity": True},
        {"quantity": -1},
        {"limit_price": float("nan")},
        {"limit_price": 10.001},
    ):
        with pytest.raises((ValueError, TypeError)):
            draft({"symbol": "AAPL", "quantity": 1, "limit_price": 100, **change})


def fake_ib():
    ib = Mock()
    ib.client.connectAsync = AsyncMock()
    ib.client.getAccounts.return_value = ["U0001111"]
    ib.client.getReqId.side_effect = [101, 102]
    ib.placeOrder.return_value = NS(orderStatus=NS(status="Submitted"))
    return ib


def run(coro):
    return asyncio.run(coro)


def test_disabled_never_connects(tmp_path):
    ib = fake_ib()
    with patch("ib_async.IB", return_value=ib), pytest.raises(OrderBlocked, match="disabled"):
        run(OrderDesk(tmp_path).execute("preview", {}, 4001, "U0001111", False))
    ib.client.connectAsync.assert_not_called()
    ib.placeOrder.assert_not_called()


def test_confirmation_required_before_connection(tmp_path):
    desk, ib = OrderDesk(tmp_path), fake_ib()
    with patch("ib_async.IB", return_value=ib), pytest.raises(OrderBlocked, match="expired"):
        run(desk.execute("submit", {"preview_token": "fake", "confirm": "BUY"}, 4001, "U0001111", True))
    ib.placeOrder.assert_not_called()
    ib.client.connectAsync.assert_not_called()


def checked():
    from ib_async import LimitOrder

    return (
        NS(conId=123),
        LimitOrder("BUY", 1, 100, account="U0001111", tif="DAY"),
        {
            "symbol": "AAPL",
            "quantity": 1,
            "limit_price": 100,
            "take_profit_price": 115,
        },
    )


def test_preview_is_not_a_purchase_and_submit_rechecks(tmp_path):
    desk, ib = OrderDesk(tmp_path), fake_ib()
    with (
        patch("ib_async.IB", return_value=ib),
        patch.object(desk, "check", new=AsyncMock(side_effect=[checked(), checked()])) as check,
        patch("scripts.ibkr_orders.asyncio.sleep", new=AsyncMock()),
    ):
        preview = run(
            desk.execute("preview", {"symbol": "AAPL", "quantity": 1, "limit_price": 100}, 4001, "U0001111", True)
        )
        ib.placeOrder.assert_not_called()
        assert not desk.intent.exists()
        # Only the sealed server draft is used, even if the client sends a different quantity.
        result = run(
            desk.execute(
                "submit",
                {"preview_token": preview["preview_token"], "confirm": "BUY", "quantity": 999},
                4001,
                "U0001111",
                True,
            )
        )
        assert check.await_count == 2
        assert check.call_args.args[-1]["quantity"] == 1
        assert result["state"] == "ACKNOWLEDGED"
        orders = [call.args[1] for call in ib.placeOrder.call_args_list]
        assert len(orders) == 2
        assert orders[0].action == "BUY" and orders[0].transmit is False
        assert orders[1].action == "SELL" and orders[1].transmit is True
        assert orders[1].parentId == orders[0].orderId
        assert orders[1].tif == "GTC" and orders[1].lmtPrice == 115
        assert all(order.orderType == "LMT" for order in orders)
        assert desk.intent.stat().st_mode & 0o777 == 0o600
        assert "U0001111" not in desk.intent.read_text()
        with pytest.raises(OrderBlocked):
            run(
                desk.execute(
                    "submit", {"preview_token": preview["preview_token"], "confirm": "BUY"}, 4001, "U0001111", True
                )
            )
        assert ib.placeOrder.call_count == 2


def test_durable_intent_precedes_transmit_and_uncertainty_blocks_retry(tmp_path):
    desk, ib = OrderDesk(tmp_path), fake_ib()

    def disconnected(*args):
        assert json.loads(desk.intent.read_text())["state"] == "SUBMITTING"
        raise ConnectionError("lost connection")

    ib.placeOrder.side_effect = disconnected
    with patch("ib_async.IB", return_value=ib), patch.object(desk, "check", new=AsyncMock(return_value=checked())):
        preview = run(desk.execute("preview", {}, 4001, "U0001111", True))
        with pytest.raises(ConnectionError):
            run(
                desk.execute(
                    "submit", {"preview_token": preview["preview_token"], "confirm": "BUY"}, 4001, "U0001111", True
                )
            )
    assert desk.status()["intent"]["state"] == "NEEDS_REVIEW"
    # Restore the real check: a persisted unresolved intent blocks before any broker request.
    with pytest.raises(OrderBlocked, match="intent"):
        run(desk.check(ib, "U0001111", {"symbol": "AAPL", "quantity": 1, "limit_price": 100}))
    assert ib.placeOrder.call_count == 1


def test_failed_recheck_never_submits(tmp_path):
    desk, ib = OrderDesk(tmp_path), fake_ib()
    with (
        patch("ib_async.IB", return_value=ib),
        patch.object(desk, "check", new=AsyncMock(side_effect=[checked(), OrderBlocked("Cash changed")])),
    ):
        preview = run(desk.execute("preview", {}, 4001, "U0001111", True))
        with pytest.raises(OrderBlocked, match="Cash changed"):
            run(
                desk.execute(
                    "submit", {"preview_token": preview["preview_token"], "confirm": "BUY"}, 4001, "U0001111", True
                )
            )
    ib.placeOrder.assert_not_called()


def broker_for_checks():
    import time

    ib = fake_ib()
    ib.qualifyContractsAsync = AsyncMock(return_value=[NS(conId=123, secType="STK", currency="USD")])
    ib.reqContractDetailsAsync = AsyncMock(return_value=[NS(minTick=0.01)])
    ib.reqPositionsAsync = AsyncMock(return_value=[])
    ib.reqAllOpenOrdersAsync = AsyncMock(return_value=[])
    ib.reqAccountUpdatesAsync = AsyncMock()
    ib.accountValues.return_value = [
        NS(tag=tag, currency=currency, value=value)
        for tag, currency, value in [
            ("CashBalance", "USD", "200"),
            ("SettledCash", "USD", "200"),
            ("NetLiquidation", "EUR", "300"),
            ("AvailableFunds", "EUR", "200"),
            ("ExchangeRate", "USD", "0.9"),
        ]
    ]
    from datetime import UTC, datetime

    ib.reqMktData.return_value = NS(bid=99.99, ask=100, time=datetime.fromtimestamp(time.time(), UTC), marketDataType=1)
    ib.whatIfOrderAsync = AsyncMock(
        return_value=NS(warningText="", commissionCurrency="USD", commission=1.0, maxCommission=1.797e308)
    )
    return ib


def test_cash_quotes_warnings_and_existing_orders_fail_closed(tmp_path):
    for mutation in ("settled_cash", "quote", "delayed", "position", "open_order", "warning", "commission", "closed"):
        ib = broker_for_checks()
        if mutation == "settled_cash":
            ib.accountValues.return_value[1].value = "50"
        elif mutation == "quote":
            ib.reqMktData.return_value.ask = float("nan")
        elif mutation == "delayed":
            ib.reqMktData.return_value.marketDataType = 3
        elif mutation == "position":
            ib.reqPositionsAsync.return_value = [NS(account="U0001111", contract=NS(conId=123), position=1)]
        elif mutation == "open_order":
            ib.reqAllOpenOrdersAsync.return_value = [NS(order=NS(account="U0001111"))]
        elif mutation == "warning":
            ib.whatIfOrderAsync.return_value.warningText = "Review warning"
        elif mutation == "commission":
            ib.whatIfOrderAsync.return_value.commission = 1.797e308
        with (
            patch("scripts.ibkr_orders.regular_session", return_value=mutation != "closed"),
            patch("scripts.ibkr_orders.asyncio.sleep", new=AsyncMock()),
            pytest.raises(OrderBlocked),
        ):
            run(OrderDesk(tmp_path).check(ib, "U0001111", {"symbol": "AAPL", "quantity": 1, "limit_price": 100}))
        ib.placeOrder.assert_not_called()


def test_valid_check_only_uses_what_if(tmp_path):
    ib = broker_for_checks()
    with (
        patch("scripts.ibkr_orders.regular_session", return_value=True),
        patch("scripts.ibkr_orders.asyncio.sleep", new=AsyncMock()),
    ):
        _, _, result = run(
            OrderDesk(tmp_path).check(ib, "U0001111", {"symbol": "AAPL", "quantity": 1, "limit_price": 100})
        )
    assert result["settled_usd"] == 200
    assert result["commission_reserve_usd"] == 2
    assert result["take_profit_price"] == 115
    ib.whatIfOrderAsync.assert_awaited_once()
    ib.placeOrder.assert_not_called()
