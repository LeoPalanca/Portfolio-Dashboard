from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import etf_fetcher


class EtfFetcherTest(unittest.TestCase):
    def test_parse_csv_holdings_with_preamble(self) -> None:
        payload = (
            "Issuer disclaimer\n"
            "Generated,2026-06-07\n"
            "Name,Ticker,ISIN,Weight (%),Sector,Country\n"
            "Apple,AAPL,US0378331005,4.5,Information Technology,United States\n"
            "Microsoft,MSFT,US5949181045,3.1,Information Technology,United States\n"
        ).encode()
        position = etf_fetcher.Position("Sample ETF", "IE0000000000")

        holdings = etf_fetcher.parse_csv_holdings(payload, position, "https://issuer.example/holdings.csv", "now")

        self.assertEqual([row.holding_name for row in holdings], ["Apple", "Microsoft"])
        self.assertEqual(holdings[0].weight_pct, Decimal("4.5"))
        self.assertEqual(holdings[0].geo, "United States")

    def test_validate_holdings_adds_explicit_issuer_remainder(self) -> None:
        holdings = [
            etf_fetcher.Holding("ETF", "IE0000000000", "Apple", "AAPL", Decimal("40"), "", "", "ETF underlying"),
            etf_fetcher.Holding("ETF", "IE0000000000", "Microsoft", "MSFT", Decimal("30"), "", "", "ETF underlying"),
        ]

        validated, weight_sum, normalized = etf_fetcher.validate_holdings(holdings)

        self.assertFalse(normalized)
        self.assertEqual(weight_sum, Decimal("100"))
        self.assertEqual(validated[-1].holding_name, "Other issuer holdings")
        self.assertEqual(validated[-1].weight_pct, Decimal("30"))

    def test_validate_holdings_normalizes_above_100(self) -> None:
        holdings = [
            etf_fetcher.Holding("ETF", "IE0000000000", "A", "A", Decimal("60"), "", "", "ETF underlying"),
            etf_fetcher.Holding("ETF", "IE0000000000", "B", "B", Decimal("60"), "", "", "ETF underlying"),
        ]

        validated, weight_sum, normalized = etf_fetcher.validate_holdings(holdings)

        self.assertTrue(normalized)
        self.assertEqual(weight_sum, Decimal("100"))
        self.assertEqual(validated[0].weight_pct, Decimal("50.0"))

    def test_parse_html_holdings_table(self) -> None:
        payload = b"""
        <table>
          <thead><tr><th>Holding name</th><th>% of market value</th><th>Sector</th><th>Region</th></tr></thead>
          <tbody><tr><td>NVIDIA Corp</td><td>4.58%</td><td>Technology</td><td>US</td></tr></tbody>
        </table>
        """
        holdings = etf_fetcher.parse_html_holdings(
            payload,
            etf_fetcher.Position("Vanguard ETF", "IE00BK5BQT80"),
            "https://issuer.example/product",
            "now",
        )

        self.assertEqual(len(holdings), 1)
        self.assertEqual(holdings[0].holding_name, "NVIDIA Corp")
        self.assertEqual(holdings[0].weight_pct, Decimal("4.58"))

    def test_parse_dws_json_holdings_table(self) -> None:
        payload = b"""{
          "tables": [{
            "columns": [
              {"key": "header", "value": "ISIN"},
              {"key": "column_0", "value": "Name"},
              {"key": "column_1", "value": "% Weight"},
              {"key": "column_3", "value": "Country"},
              {"key": "column_4", "value": "Industry"},
              {"key": "column_5", "value": "Asset class"}
            ],
            "values": [{
              "header": {"value": "US46625H1005"},
              "column_0": {"value": "JPMORGAN CHASE"},
              "column_1": {"value": "6.026%"},
              "column_3": {"value": "United States"},
              "column_4": {"value": "Diversified Banks"},
              "column_5": {"value": "Equities"}
            }]
          }]
        }"""
        parser, holdings = etf_fetcher.parse_holdings(
            payload,
            "https://etf.dws.com/api/pdp/en-gb/etf/IE00BM67HL84/holdings",
            "application/json",
            etf_fetcher.Position("Xtrackers ETF", "IE00BM67HL84"),
            "now",
        )

        self.assertEqual(parser, "json")
        self.assertEqual(len(holdings), 1)
        self.assertEqual(holdings[0].holding_isin, "US46625H1005")
        self.assertEqual(holdings[0].sector, "Diversified Banks")

    def test_parse_text_plain_json_holdings(self) -> None:
        payload = b'{"holdings":[{"name":"ALLIANZ ORD","isin":"DE0008404005","weight":15.5}]}'
        parser, holdings = etf_fetcher.parse_holdings(
            payload,
            "https://dng-api.invesco.com/cache/v1/accounts/en_IE/shareclasses/IE00B5MTXJ97/holdings/index?idType=isin",
            "text/plain;charset=UTF-8",
            etf_fetcher.Position("Invesco ETF", "IE00B5MTXJ97"),
            "now",
        )

        self.assertEqual(parser, "json")
        self.assertEqual(len(holdings), 1)
        self.assertEqual(holdings[0].holding_name, "ALLIANZ ORD")

    def test_offline_dry_run_does_not_write_outputs(self) -> None:
        with patch.object(etf_fetcher, "current_open_positions") as positions, patch.object(
            etf_fetcher, "load_existing_exposure_rows", return_value=[]
        ), patch.object(etf_fetcher, "save_documents") as save_documents, patch.object(
            etf_fetcher, "write_csv"
        ) as write_csv:
            positions.return_value = [etf_fetcher.Position("FTSE All-World USD (Acc)", "IE00BK5BQT80")]
            parser = etf_fetcher.build_parser()
            args = parser.parse_args(["update", "--official-only", "--dry-run", "--offline"])
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = etf_fetcher.update(args)

        self.assertEqual(code, 0)
        self.assertIn("Dry-run enabled", buffer.getvalue())
        save_documents.assert_not_called()
        write_csv.assert_not_called()


if __name__ == "__main__":
    unittest.main()
