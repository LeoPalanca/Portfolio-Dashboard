from __future__ import annotations

import unittest

import app


def result(*quotes: dict[str, str]) -> dict[str, list[dict[str, str]]]:
    return {"quotes": list(quotes)}


class ExtractSymbolTest(unittest.TestCase):
    def test_prefers_a_venue_ticker_over_the_isin_placeholder(self) -> None:
        found = app.extract_symbol(
            result(
                {"symbol": "IE00BLRPRL42.SG", "shortname": "WisdomTree NASDAQ 100 3x", "exchange": "STU"},
                {"symbol": "QQQ3.MI", "shortname": "WISDOMTREE NASDAQ 100 3X", "exchange": "MIL"},
            )
        )
        self.assertEqual(found["symbol"], "QQQ3.MI")

    def test_falls_back_to_the_placeholder_when_it_is_the_only_match(self) -> None:
        found = app.extract_symbol(
            result({"symbol": "JE00B2NFV803.SG", "shortname": "WisdomTree Cocoa 2x", "exchange": "STU"})
        )
        self.assertEqual(found["symbol"], "JE00B2NFV803.SG")

    def test_keeps_the_first_ticker_when_no_placeholder_is_present(self) -> None:
        found = app.extract_symbol(
            result(
                {"symbol": "KO", "shortname": "Coca-Cola", "exchange": "NYQ"},
                {"symbol": "KO.MI", "shortname": "Coca-Cola", "exchange": "MIL"},
            )
        )
        self.assertEqual(found["symbol"], "KO")

    def test_returns_nothing_without_quotes(self) -> None:
        self.assertIsNone(app.extract_symbol(result()))


if __name__ == "__main__":
    unittest.main()
