"""Reconcile each cash account's recorded movements with the balances known for it.

A balance checkpoint is an account's end-of-day balance: a statement's opening or
closing balance, or a current balance the user entered. Between two consecutive
checkpoints the balance must change by exactly the movements recorded in between;
whatever it does not explain left (or reached) the account without a recorded
movement. Beyond a small tolerance that gap becomes a calculated expense or a
calculated income, dated at the interval's end, so the account's running balance
ends where the real one does. Nothing is calculated before an account's first
checkpoint or after its last one.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from itertools import pairwise
from typing import Any

TOLERANCE = Decimal(1)
ORIGIN_ORDER = {"statement": 0, "manual": 1}


@dataclass(frozen=True)
class BalanceCheckpoint:
    account: str
    day: date
    balance: Decimal
    origin: str = "statement"  # "statement" or "manual"
    reference: str = ""


@dataclass(frozen=True)
class AccountMovement:
    account: str
    day: date
    amount: Decimal


def account_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name or "").casefold())


def _distinct(checkpoints: list[BalanceCheckpoint]) -> list[BalanceCheckpoint]:
    """Sort by day (statements before a same-day manual entry) and drop same-day repeats.

    One statement's closing balance is the next one's opening balance; both are kept
    only when they disagree, so the disagreement shows up as a gap.
    """

    result: list[BalanceCheckpoint] = []
    for checkpoint in sorted(checkpoints, key=lambda item: (item.day, ORIGIN_ORDER.get(item.origin, 2))):
        previous = result[-1] if result else None
        if previous and previous.day == checkpoint.day and abs(previous.balance - checkpoint.balance) < Decimal("0.005"):
            if checkpoint.origin == "manual":
                result[-1] = checkpoint
            continue
        result.append(checkpoint)
    return result


def reconcile_balances(
    movements: Iterable[AccountMovement],
    checkpoints: Iterable[BalanceCheckpoint],
    tolerance: Decimal = TOLERANCE,
) -> dict[str, Any]:
    """Per-account status, one interval per pair of consecutive checkpoints, and the calculated rows."""

    labels: dict[str, str] = {}
    by_account: dict[str, list[AccountMovement]] = {}
    for movement in movements:
        key = account_key(movement.account)
        labels.setdefault(key, movement.account)
        by_account.setdefault(key, []).append(movement)
    points: dict[str, list[BalanceCheckpoint]] = {}
    for checkpoint in checkpoints:
        key = account_key(checkpoint.account)
        labels.setdefault(key, checkpoint.account)
        points.setdefault(key, []).append(checkpoint)

    accounts: list[dict[str, Any]] = []
    intervals: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    for key in sorted(labels, key=lambda item: labels[item].casefold()):
        label = labels[key]
        recorded = sorted(by_account.get(key, []), key=lambda item: item.day)
        known = _distinct(points.get(key, []))
        account_intervals: list[dict[str, Any]] = []
        for start, end in pairwise(known):
            inside = [item.amount for item in recorded if start.day < item.day <= end.day]
            total = sum(inside, Decimal(0))
            gap = end.balance - start.balance - total
            kind = "expense" if gap < -tolerance else "income" if gap > tolerance else None
            interval = {
                "account": label,
                "start": start.day,
                "end": end.day,
                "opening": start.balance,
                "closing": end.balance,
                "recorded": total,
                "movements": len(inside),
                "gap": gap,
                "calculated": kind,
                "origin": f"{start.origin}→{end.origin}",
            }
            account_intervals.append(interval)
            if kind:
                rows.append(calculated_row(label, start, end, gap))
        intervals.extend(account_intervals)
        if len(known) >= 2:
            status, message = "reconciled", f"Reconciled to {known[-1].day.isoformat()}"
        elif known:
            status = "single_balance"
            message = f"One balance ({known[0].day.isoformat()}) — reconciles once a later balance is entered"
        else:
            status, message = "no_balance", "No balance yet — enter the current balance to reconcile"
        accounts.append(
            {
                "account": label,
                "status": status,
                "message": message,
                "reconciled_to": known[-1].day if len(known) >= 2 else None,
                "movements": len(recorded),
                "first_movement": recorded[0].day if recorded else None,
                "last_movement": recorded[-1].day if recorded else None,
                "latest_balance": known[-1].balance if known else None,
                "latest_balance_date": known[-1].day if known else None,
                "calculated_expenses": sum((-item["gap"] for item in account_intervals if item["calculated"] == "expense"), Decimal(0)),
                "calculated_income": sum((item["gap"] for item in account_intervals if item["calculated"] == "income"), Decimal(0)),
            }
        )
    return {"accounts": accounts, "intervals": intervals, "rows": rows}


def calculated_row(account: str, start: BalanceCheckpoint, end: BalanceCheckpoint, gap: Decimal) -> dict[str, Any]:
    expense = gap < 0
    name = "Calculated expenses" if expense else "Calculated income"
    return {
        "date": end.day,
        "source": account,
        "merchant": name,
        "description": (
            f"Balance change {start.day.isoformat()} → {end.day.isoformat()} not explained by recorded movements"
        ),
        "flow_kind": "calculated_expense" if expense else "calculated_income",
        "category": name,
        "subcategory": "",
        "amount_eur": abs(gap),
        "currency": "EUR",
        "native_amount": gap,
        "confidence": 1.0,
        "calculated": True,
    }
