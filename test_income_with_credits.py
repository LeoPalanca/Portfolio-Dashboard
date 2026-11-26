"""The "Income + money received − expenses" metric of Income & expenses (synthetic rows)."""

from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal

import app


def event(flow_kind: str, native: str, category: str) -> dict:
    return {
        "date": date(2026, 6, 1), "source": "intesa", "merchant": category, "description": category,
        "flow_kind": flow_kind, "category": category, "subcategory": "", "amount_eur": abs(Decimal(native)),
        "currency": "EUR", "native_amount": Decimal(native), "confidence": 0.5,
    }


class IncomeWithCreditsTest(unittest.TestCase):
    def test_money_received_counts_next_to_income_minus_expenses(self) -> None:
        summary = app.summarize_expense_events([
            event("income", "1000", "Income"),
            event("spend", "-400", "Groceries"),
            event("credit", "150", "Money received"),
            event("investment", "250", "Investments"),
        ])["summary"]
        self.assertEqual(summary["balance_eur"], 600.0)
        self.assertEqual(summary["balance_with_credits_eur"], 750.0)
        # Money back from an investment is neither income nor money received.
        self.assertEqual(summary["investments_eur"], -250.0)
        empty = app.empty_expenses()["summary"]
        self.assertEqual((empty["balance_eur"], empty["balance_with_credits_eur"]), (0.0, 0.0))


if __name__ == "__main__":
    unittest.main()
