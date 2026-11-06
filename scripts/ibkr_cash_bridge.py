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


async def broker_cash(port: int, suffix: str) -> dict[str, Any]:
    # Import inside an active loop: ib_async's event utilities require one on Python 3.14+.
    from ib_async import IB, StartupFetch

    ib = IB()
    try:
        await ib.connectAsync(
            "127.0.0.1", port, clientId=71, timeout=12, readonly=True, raiseSyncErrors=True, fetchFields=StartupFetch(0)
        )
        accounts = [a for a in ib.managedAccounts() if a.endswith(suffix)]
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
        if parsed.path != "/cash" or not re.fullmatch(r"\d{4}", suffix) or port not in {"4001", "4002"}:
            self.send_error(400)
            return
        try:
            with CASH_LOCK:
                payload = asyncio.run(broker_cash(int(port), suffix))
            code = 200
        except Exception:
            payload = {"error": "Broker cash unavailable. Check Gateway login, API port and unique account suffix."}
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
