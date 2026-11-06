"""The model receives public quotes, never account data or execution tools."""
import json
import unittest

from scripts.ibkr_research import public_prompt, text_output


class ResearchTests(unittest.TestCase):
    def test_prompt_excludes_private_cash_account_and_quantities(self):
        prompt = public_prompt({
            "captured_at": "2026-01-01T12:00:00+00:00", "account_masked": "PRIVATE_ACCOUNT",
            "cash_budget_base": "PRIVATE_CASH", "equity_base": "PRIVATE_EQUITY",
            "rows": [{"symbol": "DEMO", "price_usd": 100, "price_time": 12345,
                      "change_pct": -4, "reference_usable": True,
                      "whole_shares_with_cash": "PRIVATE_QUANTITY"}],
        })
        for marker in ("PRIVATE_ACCOUNT", "PRIVATE_CASH", "PRIVATE_EQUITY", "PRIVATE_QUANTITY"):
            self.assertNotIn(marker, prompt)
        self.assertIn("DEMO", prompt)
        self.assertIn("No autonomous trading is authorized", prompt)

    def test_only_text_events_become_report(self):
        raw = '\n'.join(json.dumps(event) for event in [
            {"type": "tool_use", "part": {"text": "not report text"}},
            {"type": "text", "part": {"text": "WAIT. Check news first."}},
        ])
        self.assertEqual(text_output(raw), "WAIT. Check news first.")
        with self.assertRaises(RuntimeError):
            text_output('{"type":"error"}')
