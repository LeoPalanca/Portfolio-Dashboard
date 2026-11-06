"""Human-confirmed cash-only orders. Never called by the research model.

One unresolved purchase at a time; durable intent precedes transmission. Unknown
submission outcomes require broker reconciliation, never automatic retries.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import secrets
import time
from datetime import datetime
from decimal import ROUND_CEILING, Decimal
from pathlib import Path
from zoneinfo import ZoneInfo


class OrderBlocked(ValueError):
    pass


def number(value: object) -> float:
    result = float(value)  # type: ignore[arg-type]
    if not math.isfinite(result) or abs(result) >= 1e100:
        raise OrderBlocked("Broker returned an unavailable numeric value.")
    return result


def draft(body: dict) -> dict:
    from src.portfolio_dashboard.ibkr_monitor import WATCHLIST

    symbol, quantity = body.get("symbol"), body.get("quantity")
    if symbol not in WATCHLIST or type(quantity) is not int or not 1 <= quantity <= 10000:
        raise OrderBlocked("Choose a watchlist ticker and a positive whole-share quantity.")
    if type(body.get("limit_price")) not in (int, float):
        raise OrderBlocked("Enter a numeric USD limit price.")
    limit = number(body.get("limit_price"))
    if limit < 1 or limit > 100000 or Decimal(str(limit)) % Decimal("0.01"):
        raise OrderBlocked("Use a USD limit price of at least $1, in whole cents.")
    return {"symbol": symbol, "quantity": quantity, "limit_price": limit}


def profit_target(limit: float, tick: float) -> float:
    step = Decimal(str(tick))
    return float((Decimal(str(limit)) * Decimal("1.15") / step).to_integral_value(rounding=ROUND_CEILING) * step)


def regular_session(details: object) -> bool:
    """Broker liquidHours encode holidays/early closes; unknown zones fail closed."""
    try:
        now = datetime.now(ZoneInfo(details.timeZoneId))  # type: ignore[attr-defined]
        for interval in details.liquidHours.split(";"):  # type: ignore[attr-defined]
            if "CLOSED" in interval:
                continue
            start, end = interval.split("-")
            opened = datetime.strptime(start, "%Y%m%d:%H%M").replace(tzinfo=now.tzinfo)
            closed = datetime.strptime(end, "%Y%m%d:%H%M").replace(tzinfo=now.tzinfo)
            if opened <= now < closed:
                return True
    except (ValueError, AttributeError, KeyError):
        pass
    return False


class OrderDesk:
    def __init__(self, directory: Path):
        self.directory = directory
        self.intent = directory / "order-intent.json"
        self.previews: dict[str, dict] = {}

    def status(self) -> dict:
        try:
            intent = json.loads(self.intent.read_text())
        except FileNotFoundError:
            intent = None
        return {"manual_confirmation_required": True, "autonomous_entries": False, "intent": intent}

    def save(self, value: dict) -> None:
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = self.intent.with_suffix(".tmp")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as handle:
            json.dump(value, handle, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self.intent)
        directory_fd = os.open(self.directory, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    async def check(self, ib: object, account: str, body: dict) -> tuple:
        from ib_async import LimitOrder, Stock

        proposed = draft(body)
        if self.intent.exists():
            raise OrderBlocked("An order intent already exists. Reconcile it in IBKR before another purchase.")
        symbol = proposed["symbol"].replace("-", " ")
        contracts = await asyncio.wait_for(ib.qualifyContractsAsync(Stock(symbol, "SMART", "USD")), 12)
        if len(contracts) != 1 or contracts[0].secType != "STK" or contracts[0].currency != "USD":
            raise OrderBlocked("Could not uniquely qualify a USD stock.")
        contract = contracts[0]
        details = await asyncio.wait_for(ib.reqContractDetailsAsync(contract), 12)
        if len(details) != 1 or not regular_session(details[0]):
            raise OrderBlocked("Broker regular trading session is closed or unverified.")
        tick = number(details[0].minTick)
        if tick <= 0 or Decimal(str(proposed["limit_price"])) % Decimal(str(tick)):
            raise OrderBlocked("Limit price does not match the broker minimum tick.")
        positions = await asyncio.wait_for(ib.reqPositionsAsync(), 12)
        if any(p.account == account and p.contract.conId == contract.conId and p.position != 0 for p in positions):
            raise OrderBlocked("This stock is already held. Existing holdings are excluded from this first-order flow.")
        orders = await asyncio.wait_for(ib.reqAllOpenOrdersAsync(), 12)
        if any(t.order.account == account for t in orders):
            raise OrderBlocked("Resolve existing account orders before the first purchase.")
        await asyncio.wait_for(ib.reqAccountUpdatesAsync(account), 12)
        values = ib.accountValues(account)

        def value(tag: str, currency: str) -> float:
            matches = [v for v in values if v.tag == tag and v.currency == currency]
            if len(matches) != 1:
                raise OrderBlocked("Settled USD cash is unavailable; automatic FX and borrowing are disabled.")
            return number(matches[0].value)

        available = min(value("CashBalance", "USD"), value("SettledCash", "USD"))
        base = [v.currency for v in values if v.tag == "NetLiquidation" and v.currency not in {"", "BASE"}]
        if len(set(base)) != 1:
            raise OrderBlocked("Account base currency could not be verified.")
        funds = value("AvailableFunds", base[0])
        usd_to_base = 1.0 if base[0] == "USD" else value("ExchangeRate", "USD")
        if usd_to_base <= 0 or funds <= 0:
            raise OrderBlocked("Available account funds or currency conversion could not be verified.")
        if any(number(v.value) < 0 for v in values if v.tag == "CashBalance" and v.currency != "BASE"):
            raise OrderBlocked("Negative currency cash balance detected. Borrowing is excluded from this flow.")
        available = min(available, funds / usd_to_base)
        ticker = ib.reqMktData(contract, "", False, False)
        try:
            # Streaming subscription starts now: never accept old reference prices.
            await asyncio.sleep(3)
            bid, ask = number(ticker.bid), number(ticker.ask)
            stamp = ticker.time.timestamp() if ticker.time else 0
            if ticker.marketDataType != 1 or time.time() - stamp > 10 or stamp > time.time() + 2 or not 0 < bid <= ask:
                raise OrderBlocked("A fresh real-time broker bid/ask is required.")
            if (ask - bid) / ask > 0.02 or proposed["limit_price"] > ask * 1.01:
                raise OrderBlocked("Spread exceeds 2% or the buy limit exceeds the ask by more than 1%.")
        finally:
            ib.cancelMktData(contract)
        order = LimitOrder(
            "BUY", proposed["quantity"], proposed["limit_price"], account=account, tif="DAY", outsideRth=False
        )
        preview = await asyncio.wait_for(ib.whatIfOrderAsync(contract, order), 15)
        if preview.warningText or preview.commissionCurrency != "USD":
            raise OrderBlocked("Broker preview has a warning or an unsupported commission currency; review in IBKR.")
        commissions = []
        for item in (preview.commission, preview.maxCommission):
            try:
                commission = number(item)
                if commission >= 0:
                    commissions.append(commission)
            except OrderBlocked:
                pass
        if not commissions:
            raise OrderBlocked("Broker commission estimate is unavailable.")
        reserve = max(1.0, *commissions) + 1.0
        if proposed["quantity"] * proposed["limit_price"] + reserve > available:
            raise OrderBlocked(
                "Insufficient settled USD cash including the commission reserve. Convert currency manually if needed."
            )
        return (
            contract,
            order,
            {
                **proposed,
                "bid": bid,
                "ask": ask,
                "settled_usd": available,
                "commission_reserve_usd": reserve,
                "take_profit_price": profit_target(proposed["limit_price"], tick),
                "stop_loss": None,
                "account_masked": "•••" + account[-4:],
                "target_basis": "15% above buy limit, before costs; a better entry increases the gross gain",
            },
        )

    async def execute(self, action: str, body: dict, port: int, account: str, enabled: bool) -> dict:
        from ib_async import IB, LimitOrder

        if not enabled:
            raise OrderBlocked(
                "Execution is disabled. Keep Gateway read-only until the manual order flow has been reviewed."
            )
        if action == "submit":
            token = body.get("preview_token")
            previous = self.previews.pop(token, None) if isinstance(token, str) else None
            if not previous or previous["expires_at"] < time.time() or body.get("confirm") != "BUY":
                raise OrderBlocked("Preview expired or confirmation missing. Request a new preview.")
            body = previous
        ib = IB()
        intent = None
        try:
            await ib.client.connectAsync("127.0.0.1", port, clientId=81, timeout=12)
            if account not in ib.client.getAccounts():
                raise OrderBlocked("Saved account is not accessible.")
            contract, order, checked = await self.check(ib, account, body)
            if action == "preview":
                token = secrets.token_urlsafe(32)
                self.previews = {token: {**checked, "expires_at": time.time() + 60}}
                return {**checked, "preview_token": token, "expires_at": self.previews[token]["expires_at"]}
            # All conditions are checked again after the human confirms. The draft
            # comes from server memory, never from editable browser fields.
            reference = "PD-" + secrets.token_hex(12)
            order.orderId = ib.client.getReqId()
            order.orderRef = reference
            order.transmit = False
            child = LimitOrder(
                "SELL",
                order.totalQuantity,
                checked["take_profit_price"],
                orderId=ib.client.getReqId(),
                account=account,
                tif="GTC",
                outsideRth=False,
                parentId=order.orderId,
                transmit=True,
                orderRef=reference + "-TP",
            )
            intent = {
                **checked,
                "reference": reference,
                "state": "SUBMITTING",
                "created_at": time.time(),
                "buy_order_id": order.orderId,
                "profit_order_id": child.orderId,
            }
            self.save(intent)
            parent_trade = ib.placeOrder(contract, order)
            await asyncio.sleep(0.1)
            child_trade = ib.placeOrder(contract, child)
            for _ in range(30):
                await asyncio.sleep(0.2)
                if parent_trade.orderStatus.status in {
                    "Submitted",
                    "PreSubmitted",
                    "Filled",
                    "Cancelled",
                    "Inactive",
                    "ApiCancelled",
                } and child_trade.orderStatus.status in {
                    "Submitted",
                    "PreSubmitted",
                    "Filled",
                    "Cancelled",
                    "Inactive",
                    "ApiCancelled",
                }:
                    break
            parent_status, child_status = parent_trade.orderStatus.status, child_trade.orderStatus.status
            accepted = {"Submitted", "PreSubmitted", "Filled"}
            intent.update(
                state="ACKNOWLEDGED" if parent_status in accepted and child_status in accepted else "NEEDS_REVIEW",
                buy_status=parent_status,
                profit_status=child_status,
            )
            self.save(intent)
            return intent
        except Exception:
            if intent is not None:
                intent["state"] = "NEEDS_REVIEW"
                self.save(intent)
            raise
        finally:
            ib.disconnect()
