"""Local read-only cash bridge. Requires the optional ibkr dependencies.

Run using the existing IBKR virtualenv. Binds only to 127.0.0.1:8766.
No account IDs, credentials, positions or order functions are exposed.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import re
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.parse import parse_qs, urlsplit

CASH_LOCK = Lock()


def saved_connection(path: Path | None = None) -> tuple[int, str, str]:
    config_path = path or Path(os.environ.get("IBKR_CONNECTION_CONFIG", "account_config.json"))
    config = json.loads(config_path.read_text())
    account = config.get("account")
    endpoint_ports = {"gateway-live": 4001, "gateway-paper": 4002}
    port = config.get("port", endpoint_ports.get(config.get("endpoint")))
    if (
        not isinstance(account, str)
        or not re.fullmatch(r"[A-Za-z0-9]+\d{4}", account)
        or type(port) is not int
        or port not in (4001, 4002)
    ):
        raise ValueError("Saved IBKR account connection is incomplete")
    return port, account[-4:], account


async def broker_cash(port: int, suffix: str, account: str | None = None) -> dict[str, Any]:
    # Import inside an active loop: ib_async's event utilities require one on Python 3.14+.
    from ib_async import IB

    ib = IB()
    try:
        # ib_async 2.1.0's IB.connectAsync unconditionally requests positions,
        # ignoring StartupFetch.POSITIONS. Use the protocol handshake directly:
        # this endpoint only requests account summaries, never orders/positions.
        # Gateway's Read-Only API setting remains the enforcement boundary.
        await ib.client.connectAsync("127.0.0.1", port, clientId=71, timeout=12)
        accounts = [a for a in ib.client.getAccounts() if (a == account if account is not None else a.endswith(suffix))]
        if len(accounts) != 1:
            raise ValueError("Account suffix must match exactly one accessible account")
        summary = await asyncio.wait_for(ib.accountSummaryAsync(accounts[0]), timeout=12)
        selected = [v for v in summary if v.account == accounts[0]]
        currencies = {v.currency for v in selected if v.tag == "NetLiquidation" and v.currency}
        if len(currencies) != 1:
            raise ValueError("Cannot establish account base currency")
        currency = currencies.pop()
        if not re.fullmatch(r"[A-Z]{3}", currency):
            raise ValueError("Invalid account currency")
        values = {
            v.tag: float(v.value)
            for v in selected
            if v.currency == currency and v.tag in {"TotalCashValue", "AvailableFunds", "NetLiquidation"}
        }
        if not all(
            k in values and math.isfinite(values[k]) for k in ("TotalCashValue", "AvailableFunds", "NetLiquidation")
        ):
            raise ValueError("Incomplete broker cash data")
        return {
            "account_masked": "•••" + suffix,
            "base_currency": currency,
            "total_cash_base": values["TotalCashValue"],
            "available_funds_base": values["AvailableFunds"],
            "cash_budget_base": max(0.0, min(values["TotalCashValue"], values["AvailableFunds"])),
            "equity_base": values["NetLiquidation"],
            "broker_captured_at": datetime.now(UTC).isoformat(),
        }
    finally:
        ib.disconnect()


class CashHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args: Any) -> None:
        pass  # Do not log account suffixes.

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        query = parse_qs(parsed.query)
        suffix = query.get("suffix", [""])[0]
        port = query.get("port", [""])[0]
        if self.headers.get("Host") not in {"127.0.0.1:8766", "localhost:8766"}:
            self.send_error(403)
            return
        if parsed.path == "/analysis":
            path = Path(os.environ.get("IBKR_RESEARCH_STATE", "research")) / "latest.json"
            try:
                raw = path.read_bytes()
                if len(raw) > 128000:
                    raise ValueError("Report too large")
                report = json.loads(raw)
                if not isinstance(report, dict):
                    raise ValueError("Invalid report")
            except (OSError, ValueError):
                report = {}
            body = json.dumps(report).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path != "/cash" or (query and (not re.fullmatch(r"\d{4}", suffix) or port not in {"4001", "4002"})):
            self.send_error(400)
            return
        try:
            selected_account = None
            if not query:
                saved_port, suffix, selected_account = saved_connection()
                port = str(saved_port)
            with CASH_LOCK:
                payload = asyncio.run(broker_cash(int(port), suffix, selected_account))
            code = 200
        except Exception:
            payload = {
                "error": "Saved broker connection unavailable. Check Gateway login and saved account configuration."
            }
            code = 503
        body = json.dumps(payload, allow_nan=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 8766), CashHandler).serve_forever()
