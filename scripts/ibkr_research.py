"""Scheduled OpenCode research. Public market data only; never submits orders."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.portfolio_dashboard.ibkr_monitor import collect  # noqa: E402


def market_open() -> bool:
    """Fail closed using the provider's dated regular-session interval, including DST."""
    req = urllib.request.Request(
        "https://query1.finance.yahoo.com/v8/finance/chart/SPY?interval=1d&range=1d",
        headers={"User-Agent": "Mozilla/5.0 PortfolioDashboard"},
    )
    with urllib.request.urlopen(req, timeout=12) as response:
        meta = json.load(response)["chart"]["result"][0]["meta"]
    period = meta["currentTradingPeriod"]["regular"]
    return bool(period["start"] <= datetime.now(UTC).timestamp() < period["end"])


def public_prompt(snapshot: dict) -> str:
    # Do not send account identity, cash, equity, positions or affordable quantities to the model.
    quotes = [
        {key: row.get(key) for key in ("symbol", "price_usd", "previous_close_usd", "change_pct", "price_time")}
        for row in snapshot["rows"]
        if row["reference_usable"]
    ]
    candidates = [
        row["symbol"]
        for row in snapshot["rows"]
        if row["reference_usable"]
        and isinstance(row.get("whole_shares_with_cash"), (int, float))
        and row["whole_shares_with_cash"] > 0
    ]
    return (
        "You are a stock-research analyst, not an execution agent. Use no tools and change no files. "
        "Review this dated S&P 500 stock watchlist after a possible market decline. Prices are public Yahoo "
        "reference data and may be delayed or from a closed session. Explain the pattern and name at most "
        "three research candidates for a manually reviewed first purchase, or say WAIT. A large drop alone "
        "does not imply recovery. News, earnings, valuations and broker execution quotes have NOT been "
        "provided: do not invent causes or claim to have checked them. Mark those checks as required. "
        "Do not recommend quantities, assume a budget, set profit targets without evidence, or claim an "
        "order is approved. Explain uncertainty and what would invalidate a rebound hypothesis. "
        "No autonomous trading is authorized. For purchase research, use ONLY these locally preselected "
        "tickers: " + json.dumps(candidates) + ". If the list is empty, say WAIT. The full public table "
        "is context, not permission to suggest other stocks. Be concise. Snapshot UTC: "
        + snapshot["captured_at"]
        + "\nPublic reference data:\n"
        + json.dumps(quotes, allow_nan=False)
    )


def text_output(raw: str) -> str:
    chunks = []
    for line in raw.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") == "text" and isinstance(event.get("part", {}).get("text"), str):
            chunks.append(event["part"]["text"])
    if not chunks:
        raise RuntimeError("OpenCode did not return a text research report")
    return "\n".join(chunks)[:32000]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-suffix", required=True)
    parser.add_argument("--port", type=int, choices=(4001, 4002), default=4001)
    parser.add_argument("--opencode", required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--review-last-session", action="store_true")
    args = parser.parse_args()
    if not (len(args.account_suffix) == 4 and args.account_suffix.isascii() and args.account_suffix.isdigit()):
        parser.error("Use the last four account digits")
    if not args.review_last_session and not market_open():
        print("Outside the regular US session. No analysis run.")
        return
    snapshot = collect(args.port, args.account_suffix)
    if not any(r["reference_usable"] for r in snapshot["rows"]):
        raise RuntimeError("No usable reference prices")
    workspace = args.state_dir / "opencode"
    workspace.mkdir(parents=True, exist_ok=True)
    config = {"$schema": "https://opencode.ai/config.json", "model": "opencode/big-pickle", "permission": {"*": "deny"}}
    (workspace / "opencode.json").write_text(json.dumps(config))
    result = subprocess.run(
        [
            args.opencode,
            "--standalone",
            "run",
            "--model",
            "opencode/big-pickle",
            "--format",
            "json",
            "--title",
            "IBKR read-only market research",
            public_prompt(snapshot),
        ],
        cwd=workspace,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    if result.returncode:
        raise RuntimeError("OpenCode research failed; inspect local service logs")
    report = {
        "captured_at": snapshot["captured_at"],
        "completed_at": datetime.now(UTC).isoformat(),
        "model": "opencode/big-pickle",
        "execution_enabled": False,
        "manual_confirmation_required": True,
        "review_last_session": args.review_last_session,
        "report": text_output(result.stdout),
    }
    temporary = args.state_dir / "latest.tmp"
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        json.dump(report, handle, allow_nan=False)
    os.replace(temporary, args.state_dir / "latest.json")
    print("Research saved. Manual review required; no orders submitted.")


if __name__ == "__main__":
    main()
