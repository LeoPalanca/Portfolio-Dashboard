from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import app


class DistributionAggregationTest(unittest.TestCase):
    @staticmethod
    def sample_trade() -> app.Trade:
        return app.Trade(
            asset="Example ETF",
            isin="IE0000000001",
            broker="Example Broker",
            action="BUY",
            currency_hint="EUR",
            cash_currency="EUR",
            date=date(2026, 1, 2),
            price=Decimal("100"),
            quantity=Decimal("1"),
            quantity_diff=Decimal("1"),
            total_spend=Decimal("100"),
            fees=Decimal("0"),
            tax=Decimal("0"),
            grand_total=Decimal("100"),
            grand_total_present=True,
            source="synthetic_test",
        )

    def test_canonical_holding_name_merges_issuer_name_variants(self) -> None:
        examples = {
            "NVIDIA CORP": "NVIDIA",
            "NVIDIA Corp": "NVIDIA",
            "APPLE INC": "Apple",
            "Apple Inc": "Apple",
            "MICROSOFT CORP": "Microsoft",
            "Alphabet Inc Class A": "Alphabet",
            "ALPHABET INC CLASS C": "Alphabet",
            "JPMORGAN CHASE & CO": "JPMorgan Chase",
            "BERKSHIRE HATHAWAY INC CLASS B": "Berkshire Hathaway",
        }

        for raw, expected in examples.items():
            with self.subTest(raw=raw):
                self.assertEqual(app.canonical_holding_name(raw), expected)

    def test_distribution_merges_underlying_variants(self) -> None:
        positions = [
            {"asset": "ETF A", "isin": "AAA", "is_open": True, "market_value_eur": 100, "symbol": "ETFA"},
            {"asset": "ETF B", "isin": "BBB", "is_open": True, "market_value_eur": 100, "symbol": "ETFB"},
        ]
        exposures = {
            app.exposure_key("ETF A", "AAA"): [
                {
                    "holding_name": "NVIDIA CORP",
                    "holding_ticker": "NVDA",
                    "weight_pct": Decimal("10"),
                    "sector": "Information Technology",
                    "geo": "United States",
                    "asset_class": "ETF underlying",
                }
            ],
            app.exposure_key("ETF B", "BBB"): [
                {
                    "holding_name": "NVIDIA Corp",
                    "holding_ticker": "",
                    "weight_pct": Decimal("20"),
                    "sector": "Information Technology",
                    "geo": "United States",
                    "asset_class": "ETF underlying",
                }
            ],
        }

        distribution = app.calculate_distribution(positions, exposures)
        nvidia_rows = [row for row in distribution["underlying"] if row["holding"] == "NVIDIA"]

        self.assertEqual(len(nvidia_rows), 1)
        self.assertEqual(nvidia_rows[0]["market_value_eur"], 30.0)
        self.assertEqual(nvidia_rows[0]["source_assets"], ["ETFA", "ETFB"])

    def test_underlying_source_pills_use_stock_for_direct_single_shares(self) -> None:
        positions = [
            {"asset": "ETF A", "isin": "AAA", "is_open": True, "market_value_eur": 100, "symbol": "ETFA"},
            {"asset": "NVIDIA", "isin": "US67066G1040", "is_open": True, "market_value_eur": 50, "symbol": "NVDA"},
        ]
        exposures = {
            app.exposure_key("ETF A", "AAA"): [
                {
                    "holding_name": "NVIDIA CORP",
                    "holding_ticker": "NVDA",
                    "weight_pct": Decimal("100"),
                    "sector": "Information Technology",
                    "geo": "United States",
                    "asset_class": "ETF underlying",
                }
            ],
            app.exposure_key("NVIDIA", "US67066G1040"): [
                {
                    "holding_name": "NVIDIA",
                    "holding_ticker": "NVDA",
                    "weight_pct": Decimal("100"),
                    "sector": "Information Technology",
                    "geo": "United States",
                    "asset_class": "Single share",
                }
            ],
        }

        distribution = app.calculate_distribution(positions, exposures)
        nvidia_row = next(row for row in distribution["underlying"] if row["holding"] == "NVIDIA")

        self.assertEqual(nvidia_row["market_value_eur"], 150.0)
        self.assertEqual(nvidia_row["source_assets"], ["ETFA", "stock"])

    def test_ticker_resolution_for_underlying(self) -> None:
        # Test 1: resolving using COMMON_HOLDING_TICKERS (e.g. "ALLIANZ ORD" -> "ALV")
        # Test 2: resolving dynamically using position name matching (e.g. "MY CUSTOM ASSET CO" -> ticker "MCAC")
        positions = [
            {"asset": "ETF A", "isin": "AAA", "is_open": True, "market_value_eur": 100, "symbol": "ETFA"},
            {"asset": "My Custom Asset Co", "isin": "US1112223334", "is_open": True, "market_value_eur": 50, "symbol": "MCAC"},
        ]
        exposures = {
            app.exposure_key("ETF A", "AAA"): [
                {
                    "holding_name": "ALLIANZ ORD",
                    "holding_ticker": "",
                    "weight_pct": Decimal("40"),
                    "sector": "Financials",
                    "geo": "Germany",
                    "asset_class": "ETF underlying",
                },
                {
                    "holding_name": "MY CUSTOM ASSET CO CORP",
                    "holding_ticker": "",
                    "weight_pct": Decimal("40"),
                    "sector": "Technology",
                    "geo": "United States",
                    "asset_class": "ETF underlying",
                },
                {
                    "holding_name": "AXA SE",
                    "holding_ticker": "CS FP",
                    "weight_pct": Decimal("10"),
                    "sector": "Financials",
                    "geo": "France",
                    "asset_class": "ETF underlying",
                },
                {
                    "holding_name": "SAMSUNG ELECTRONICS CO LTD",
                    "holding_ticker": "005930",
                    "weight_pct": Decimal("10"),
                    "sector": "Technology",
                    "geo": "Korea (South)",
                    "asset_class": "ETF underlying",
                }
            ]
        }
        
        distribution = app.calculate_distribution(positions, exposures)
        underlying_rows = distribution["underlying"]
        
        allianz_row = next(row for row in underlying_rows if row["holding"] == "Allianz")
        custom_row = next(row for row in underlying_rows if row["holding"] == "My Custom Asset")
        axa_row = next(row for row in underlying_rows if row["holding"] == "Axa")
        samsung_row = next(row for row in underlying_rows if row["holding"] == "Samsung Electronics")
        
        # Allianz should resolve to ALV via COMMON_HOLDING_TICKERS
        self.assertEqual(allianz_row["holding_ticker"], "ALV")
        # My Custom Asset should resolve to MCAC via matching positions
        self.assertEqual(custom_row["holding_ticker"], "MCAC")
        # Axa should normalize to CS.PA from CS FP
        self.assertEqual(axa_row["holding_ticker"], "CS.PA")
        # Samsung Electronics should append .KS based on Korea geo
        self.assertEqual(samsung_row["holding_ticker"], "005930.KS")

    def test_crypto_wallet_position_uses_wallet_market_value(self) -> None:
        positions = [
            {
                "asset": "TON",
                "isin": "",
                "quantity": 12.34595442,
                "cost_basis_eur": 0.0,
                "is_open": True,
                "broker": "Crypto Wallet",
                "symbol": "NON_EXISTENT_COIN",
                "market_value_eur": 19.27,
                "asset_class": "Crypto",
                "sector": "Crypto",
                "geo": "Global",
            }
        ]

        with (
            patch.object(app, "fetch_price", return_value={"status": "price_error"}),
            patch.object(app, "compute_position_variations", return_value={}),
        ):
            priced = app.enrich_positions(positions, {}, refresh=False)
        distribution = app.calculate_distribution(priced["positions"], {})

        self.assertEqual(priced["positions"][0]["pricing_status"], "crypto_wallet")
        self.assertEqual(priced["positions"][0]["market_value_eur"], 19.27)
        self.assertTrue(any(row["asset_class"] == "Crypto" for row in distribution["asset_classes"]))

    def test_missing_assets_and_other_remainders_keep_context(self) -> None:
        positions = [
            {"asset": "MSCI Emerging Markets EUR (Acc)", "isin": "LU1681045370", "is_open": True, "market_value_eur": 100, "symbol": ""},
            {"asset": "Vanguard ETF", "isin": "IE00BK5BQT80", "is_open": True, "market_value_eur": 100, "symbol": ""},
        ]
        exposures = {
            app.exposure_key("Vanguard ETF", "IE00BK5BQT80"): [
                {
                    "holding_name": "Other issuer holdings",
                    "holding_ticker": "",
                    "weight_pct": Decimal("100"),
                    "sector": "Unknown from issuer data",
                    "geo": "Unknown from issuer data",
                    "asset_class": "ETF underlying",
                }
            ]
        }

        distribution = app.calculate_distribution(positions, exposures)
        labels = {row["holding"] for row in distribution["underlying"]}

        self.assertIn("MSCI Emerging Markets EUR (Acc)", labels)
        self.assertIn("Other issuer holdings - Vanguard ETF", labels)

    def test_berkshire_mode_switches_between_stock_and_13f_lookthrough(self) -> None:
        positions = [
            {
                "asset": "Berkshire Hathaway (B)",
                "isin": app.BERKSHIRE_ISIN,
                "is_open": True,
                "market_value_eur": 100,
                "symbol": "BRK-B",
            }
        ]
        stock_distribution = app.calculate_distribution(
            positions,
            app.read_exposures(berkshire_mode="stock"),
            berkshire_mode="stock",
        )
        lookthrough_rows = app.read_exposures(berkshire_mode="lookthrough")[
            app.exposure_key("Berkshire Hathaway (B)", app.BERKSHIRE_ISIN)
        ]

        self.assertGreater(len(lookthrough_rows), 1)
        self.assertEqual(len(stock_distribution["underlying"]), 1)
        self.assertTrue(stock_distribution["underlying"][0]["holding"].startswith("Berkshire Hathaway"))
        self.assertTrue(any(row["holding_name"] == "APPLE INC" for row in lookthrough_rows))

    def test_public_exposures_do_not_require_private_exposure_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, patch.object(
            app, "EXPOSURES_CSV", Path(temporary) / "missing.csv"
        ):
            exposures = app.read_exposures(proxy_mode="on")

        self.assertIn(app.exposure_key("FTSE All-World USD (Acc)", "IE00BK5BQT80"), exposures)

    def test_berkshire_lookthrough_distribution_uses_sec_source_metadata(self) -> None:
        positions = [
            {
                "asset": "Berkshire Hathaway (B)",
                "isin": app.BERKSHIRE_ISIN,
                "is_open": True,
                "market_value_eur": 100,
                "symbol": "BRK-B",
            }
        ]
        distribution = app.calculate_distribution(
            positions,
            app.read_exposures(berkshire_mode="lookthrough"),
            berkshire_mode="lookthrough",
        )

        self.assertEqual(distribution["composition_source_coverage"], {"resolved": 1, "total": 1})
        self.assertEqual(distribution["composition_sources"][0]["status"], "official_sec_13f")
        self.assertTrue(any(row["holding"] == "Apple" for row in distribution["underlying"]))
        
        sectors = {row["sector"] for row in distribution["sectors"]}
        self.assertIn("Information Technology", sectors)
        self.assertIn("Financials", sectors)
        self.assertNotIn("Unclassified", sectors)

    def test_proxy_mode_adds_requested_gap_compositions(self) -> None:
        proxy_exposures = app.read_exposures(proxy_mode="on")
        official_exposures = app.read_exposures(proxy_mode="off")

        for asset, isin, expected_rows in [
            ("FTSE All-World USD (Acc)", "IE00BK5BQT80", 1500),
            ("MSCI Emerging Markets EUR (Acc)", "LU1681045370", 1768),
            ("VE ETFS MDMDLUE", "NL0011683594", 101),
        ]:
            with self.subTest(isin=isin):
                rows = proxy_exposures[app.exposure_key(asset, isin)]
                self.assertEqual(len(rows), expected_rows)
                self.assertEqual(sum((row["weight_pct"] for row in rows), Decimal("0")).quantize(Decimal("0.000001")), Decimal("100.000000"))
                self.assertFalse(any(row["holding_name"].startswith("Other proxy holdings") for row in rows))

        self.assertNotIn(app.exposure_key("MSCI Emerging Markets EUR (Acc)", "LU1681045370"), official_exposures)
        self.assertNotIn(app.exposure_key("VE ETFS MDMDLUE", "NL0011683594"), official_exposures)

    def test_proxy_mode_does_not_replace_full_official_compositions(self) -> None:
        official_key = app.exposure_key("Core MSCI EM IMI USD (Acc)", "IE00BKM4GZ66")
        proxy_row = {
            "asset_name": "Core MSCI EM IMI USD (Acc)",
            "isin": "IE00BKM4GZ66",
            "holding_name": "Proxy Holding",
            "holding_ticker": "PROXY",
            "weight_pct": Decimal("100"),
            "sector": "Unclassified",
            "geo": "Unclassified",
            "asset_class": "ETF underlying",
        }
        with tempfile.TemporaryDirectory() as temporary:
            private_exposures = Path(temporary) / "asset_exposures.csv"
            private_exposures.write_text(
                "asset_name,isin,holding_name,holding_ticker,weight_pct,sector,geo,asset_class\n"
                "Core MSCI EM IMI USD (Acc),IE00BKM4GZ66,Official Holding,OFFICIAL,100,Technology,Global,ETF underlying\n",
                encoding="utf-8",
            )
            with (
                patch.object(app, "EXPOSURES_CSV", private_exposures),
                patch.object(app, "read_etf_documents", return_value={"IE00BKM4GZ66": {"status": "ok"}}),
                patch.object(app, "load_proxy_exposure_rows", return_value={"IE00BKM4GZ66": [proxy_row]}),
            ):
                proxy_exposures = app.read_exposures(proxy_mode="on")
                official_exposures = app.read_exposures(proxy_mode="off")

        self.assertIn(official_key, official_exposures)
        self.assertEqual(len(proxy_exposures[official_key]), len(official_exposures[official_key]))
        self.assertEqual(proxy_exposures[official_key][0]["holding_name"], "Official Holding")

        positions = [
            {
                "asset": "Core MSCI EM IMI USD (Acc)",
                "isin": "IE00BKM4GZ66",
                "is_open": True,
                "market_value_eur": 100,
                "symbol": "",
            }
        ]
        with patch.object(
            app,
            "read_etf_documents",
            return_value={"IE00BKM4GZ66": {"status": "ok", "rows": 1, "weight_sum": "100"}},
        ):
            distribution = app.calculate_distribution(
                positions,
                proxy_exposures,
                proxy_mode="on",
            )

        self.assertEqual(distribution["composition_sources"][0]["status"], "ok")
        self.assertEqual(distribution["composition_sources"][0]["rows"], len(official_exposures[official_key]))

    def test_proxy_distribution_uses_explicit_proxy_source_metadata(self) -> None:
        positions = [
            {
                "asset": "MSCI Emerging Markets EUR (Acc)",
                "isin": "LU1681045370",
                "is_open": True,
                "market_value_eur": 100,
                "symbol": "",
            }
        ]
        distribution = app.calculate_distribution(
            positions,
            app.read_exposures(proxy_mode="on"),
            proxy_mode="on",
        )

        self.assertEqual(distribution["composition_source_coverage"], {"resolved": 1, "total": 1})
        self.assertEqual(distribution["composition_sources"][0]["status"], "proxy_exposure")
        self.assertFalse(distribution["missing"])

    def test_vanguard_proxy_distribution_has_no_aggregate_other_row(self) -> None:
        positions = [
            {
                "asset": "FTSE All-World USD (Acc)",
                "isin": "IE00BK5BQT80",
                "is_open": True,
                "market_value_eur": 100,
                "symbol": "",
            }
        ]
        distribution = app.calculate_distribution(
            positions,
            app.read_exposures(proxy_mode="on"),
            proxy_mode="on",
        )
        labels = [row["holding"] for row in distribution["underlying"]]

        self.assertEqual(distribution["composition_sources"][0]["rows"], 1500)
        self.assertFalse(any(label.startswith("Other proxy holdings") for label in labels))
        self.assertTrue(any(label == "NVIDIA" for label in labels))

    def test_mediolanum_proxy_exposures(self) -> None:
        if not app.EXPOSURES_CSV.exists():
            self.skipTest("optional private exposure catalog is not installed")
        positions = [
            {
                "asset": "SMFI - Mediolanum Flessibile Futuro Italia LA PIR Acc EUR",
                "isin": "IT0001019329",
                "is_open": True,
                "market_value_eur": 100,
                "symbol": "0P00000U91.F",
            },
            {
                "asset": "MBB Mediolanum Morgan Stanley Global Selection LHA EUR",
                "isin": "IE00B2NLMV86",
                "is_open": True,
                "market_value_eur": 100,
                "symbol": "0P0000CNA3.F",
            },
            {
                "asset": "MBB Dynamic International Value Opportunity LA EUR",
                "isin": "IE00BYZ2Y955",
                "is_open": True,
                "market_value_eur": 100,
                "symbol": "0P00018DRL.F",
            }
        ]
        distribution = app.calculate_distribution(
            positions,
            app.read_exposures(proxy_mode="on"),
            proxy_mode="on",
        )
        self.assertEqual(distribution["composition_source_coverage"], {"resolved": 3, "total": 3})
        sources = {src["isin"]: src for src in distribution["composition_sources"]}
        
        # SMFI PIR Fund assertions
        self.assertIn("IT0001019329", sources)
        self.assertEqual(sources["IT0001019329"]["status"], "proxy_exposure")
        self.assertEqual(sources["IT0001019329"]["rows"], 7)
        self.assertEqual(Decimal(sources["IT0001019329"]["weight_sum"]), Decimal("100"))
        
        # Dynamic International Value assertions
        self.assertIn("IE00BYZ2Y955", sources)
        self.assertEqual(sources["IE00BYZ2Y955"]["status"], "proxy_exposure")
        self.assertEqual(sources["IE00BYZ2Y955"]["rows"], 101)
        self.assertEqual(Decimal(sources["IE00BYZ2Y955"]["weight_sum"]), Decimal("100"))
        
        # Morgan Stanley Selection assertions
        self.assertIn("IE00B2NLMV86", sources)
        self.assertEqual(sources["IE00B2NLMV86"]["status"], "proxy_exposure")
        self.assertTrue(sources["IE00B2NLMV86"]["rows"] > 1000)

    def test_eurizon_proxy_exposures(self) -> None:
        if not app.EXPOSURES_CSV.exists():
            self.skipTest("optional private exposure catalog is not installed")
        positions = [
            {
                "asset": "Eurizon Obbligazioni Euro High Yield",
                "isin": "IT0001280541",
                "is_open": True,
                "market_value_eur": 100,
                "symbol": "",
            },
            {
                "asset": "Eurizon Profilo Flessibile Difesa II",
                "isin": "IT0005285157",
                "is_open": True,
                "market_value_eur": 100,
                "symbol": "",
            },
            {
                "asset": "Eurizon Riserva 2 Anni Classe A",
                "isin": "IT0005104424",
                "is_open": True,
                "market_value_eur": 100,
                "symbol": "",
            },
            {
                "asset": "Eurizon Flexible Equity Strategy R EUR",
                "isin": "LU0497415702",
                "is_open": True,
                "market_value_eur": 100,
                "symbol": "",
            }
        ]
        distribution = app.calculate_distribution(
            positions,
            app.read_exposures(proxy_mode="on"),
            proxy_mode="on",
        )
        self.assertEqual(distribution["composition_source_coverage"], {"resolved": 4, "total": 4})
        sources = {src["isin"]: src for src in distribution["composition_sources"]}
        
        # High Yield
        self.assertIn("IT0001280541", sources)
        self.assertEqual(sources["IT0001280541"]["status"], "proxy_exposure")
        self.assertEqual(sources["IT0001280541"]["rows"], 4)
        self.assertEqual(Decimal(sources["IT0001280541"]["weight_sum"]), Decimal("100"))
        
        # Profilo Flessibile Difesa II
        self.assertIn("IT0005285157", sources)
        self.assertEqual(sources["IT0005285157"]["status"], "proxy_exposure")
        self.assertTrue(sources["IT0005285157"]["rows"] > 1000)
        self.assertEqual(Decimal(sources["IT0005285157"]["weight_sum"]), Decimal("100"))
        
        # Riserva 2 Anni
        self.assertIn("IT0005104424", sources)
        self.assertEqual(sources["IT0005104424"]["status"], "proxy_exposure")
        self.assertEqual(sources["IT0005104424"]["rows"], 2)
        self.assertEqual(Decimal(sources["IT0005104424"]["weight_sum"]), Decimal("100"))

        # Flexible Equity Strategy
        self.assertIn("LU0497415702", sources)
        self.assertEqual(sources["LU0497415702"]["status"], "proxy_exposure")
        self.assertTrue(sources["LU0497415702"]["rows"] > 1000)
        self.assertEqual(Decimal(sources["LU0497415702"]["weight_sum"]), Decimal("100"))

    def test_configured_fund_proxy_exposures(self) -> None:
        if not app.EXPOSURES_CSV.exists():
            self.skipTest("optional private exposure catalog is not installed")
        positions = [
            {
                "asset": "Anima Fondo Trading F",
                "isin": "IT0004896715",
                "is_open": True,
                "market_value_eur": 100,
                "symbol": "",
            },
            {
                "asset": "JPM Europe Equity I acc EUR",
                "isin": "LU2146152231",
                "is_open": True,
                "market_value_eur": 100,
                "symbol": "",
            },
            {
                "asset": "JPM Europe Equity C acc EUR",
                "isin": "LU0129441100",
                "is_open": True,
                "market_value_eur": 100,
                "symbol": "",
            },
            {
                "asset": "Franklin Biotechnology Discv A acc USD",
                "isin": "LU0109394709",
                "is_open": True,
                "market_value_eur": 100,
                "symbol": "",
            },
            {
                "asset": "Templeton Global Bond I acc EUR",
                "isin": "LU0195953079",
                "is_open": True,
                "market_value_eur": 100,
                "symbol": "",
            },
            {
                "asset": "Fidelity America Y acc Eur",
                "isin": "LU0755218046",
                "is_open": True,
                "market_value_eur": 100,
                "symbol": "",
            },
            {
                "asset": "Schroder ISF Italian Equity C acc Eur",
                "isin": "LU0106239527",
                "is_open": True,
                "market_value_eur": 100,
                "symbol": "",
            }
        ]
        distribution = app.calculate_distribution(
            positions,
            app.read_exposures(proxy_mode="on"),
            proxy_mode="on",
        )
        self.assertEqual(distribution["composition_source_coverage"], {"resolved": 7, "total": 7})
        sources = {src["isin"]: src for src in distribution["composition_sources"]}

        # Anima Fondo Trading F
        self.assertIn("IT0004896715", sources)
        self.assertEqual(sources["IT0004896715"]["status"], "proxy_exposure")
        self.assertTrue(sources["IT0004896715"]["rows"] > 1000)
        self.assertEqual(Decimal(sources["IT0004896715"]["weight_sum"]), Decimal("100"))

        # JPM Europe Equity I
        self.assertIn("LU2146152231", sources)
        self.assertEqual(sources["LU2146152231"]["status"], "proxy_exposure")
        self.assertEqual(sources["LU2146152231"]["rows"], 9)
        self.assertEqual(Decimal(sources["LU2146152231"]["weight_sum"]), Decimal("100"))

        # JPM Europe Equity C
        self.assertIn("LU0129441100", sources)
        self.assertEqual(sources["LU0129441100"]["status"], "proxy_exposure")
        self.assertEqual(sources["LU0129441100"]["rows"], 9)
        self.assertEqual(Decimal(sources["LU0129441100"]["weight_sum"]), Decimal("100"))

        # Franklin Biotechnology Discv
        self.assertIn("LU0109394709", sources)
        self.assertEqual(sources["LU0109394709"]["status"], "proxy_exposure")
        self.assertEqual(sources["LU0109394709"]["rows"], 5)
        self.assertEqual(Decimal(sources["LU0109394709"]["weight_sum"]), Decimal("100"))

        # Templeton Global Bond I
        self.assertIn("LU0195953079", sources)
        self.assertEqual(sources["LU0195953079"]["status"], "proxy_exposure")
        self.assertEqual(sources["LU0195953079"]["rows"], 3)
        self.assertEqual(Decimal(sources["LU0195953079"]["weight_sum"]), Decimal("100"))

        # Fidelity America Y
        self.assertIn("LU0755218046", sources)
        self.assertEqual(sources["LU0755218046"]["status"], "proxy_exposure")
        self.assertTrue(sources["LU0755218046"]["rows"] > 500)
        self.assertEqual(Decimal(sources["LU0755218046"]["weight_sum"]), Decimal("100"))

        # Schroder ISF Italian Equity C
        self.assertIn("LU0106239527", sources)
        self.assertEqual(sources["LU0106239527"]["status"], "proxy_exposure")
        self.assertEqual(sources["LU0106239527"]["rows"], 6)
        self.assertEqual(Decimal(sources["LU0106239527"]["weight_sum"]), Decimal("100"))

    def test_live_only_filter(self) -> None:
        from pathlib import Path

        from src.portfolio_dashboard.config import PortfolioProfile

        history_error = {"status": "history_error", "prices": {}}
        snapshot = {
            "path": Path("synthetic-snapshot.csv"),
            "person_name": "Secondary Portfolio",
            "first_date": app.date(2025, 1, 1),
            "latest_date": app.date(2025, 1, 1),
            "positions": [
                {
                    "asset": "Unpriced Fund A",
                    "broker": "Example Broker",
                    "isin": "",
                    "symbol": "",
                    "quantity": app.Decimal("1"),
                    "cost_price": app.Decimal("100"),
                    "cost_basis_eur": app.Decimal("100"),
                    "market_value_eur": app.Decimal("100"),
                    "price_currency": "EUR",
                },
                {
                    "asset": "Unpriced Fund B",
                    "broker": "Example Broker",
                    "isin": "",
                    "symbol": "",
                    "quantity": app.Decimal("1"),
                    "cost_price": app.Decimal("200"),
                    "cost_basis_eur": app.Decimal("200"),
                    "market_value_eur": app.Decimal("200"),
                    "price_currency": "EUR",
                },
            ],
        }
        with (
            patch.dict(
                app.SETTINGS.portfolios,
                {"secondary": PortfolioProfile(display_name="Secondary Portfolio", snapshot_pattern="missing/*.csv")},
            ),
            patch.object(app, "read_family_snapshot", return_value=snapshot),
            patch.object(app, "resolve_isin", return_value={}),
            patch.object(app, "fetch_history", return_value=history_error),
            patch.object(app, "fetch_price", return_value={"status": "price_error"}),
            patch.object(app, "fetch_eurostat_cpi", return_value={}),
        ):
            payload_all = app.family_dashboard_payload("secondary", live_only="off")
            payload_live = app.family_dashboard_payload("secondary", live_only="on")
        
        all_assets = {pos["asset"] for pos in payload_all["positions"]}
        live_assets = {pos["asset"] for pos in payload_live["positions"]}
        
        self.assertIn("Unpriced Fund A", all_assets)
        self.assertIn("Unpriced Fund B", all_assets)
        
        self.assertNotIn("Unpriced Fund A", live_assets)
        self.assertNotIn("Unpriced Fund B", live_assets)
        
        self.assertTrue(len(payload_live["positions"]) < len(payload_all["positions"]))

    def test_calculate_valuation_series_includes_dividends_and_interest(self) -> None:
        trades = [self.sample_trade()]
        history_error = {"status": "history_error", "prices": {}}
        with (
            patch.object(app, "resolve_isin", return_value={}),
            patch.object(app, "fetch_history", return_value=history_error),
            patch.object(app, "fetch_eurostat_cpi", return_value={}),
            patch.object(app, "read_portfolio_dividends", return_value=[]),
            patch.object(app, "read_cash_interests", return_value=[]),
            patch.object(app, "load_cash_histories", return_value=([], [], [])),
        ):
            valuation = app.calculate_valuation_series(trades, {}, refresh=False, person=app.PRIMARY_PORTFOLIO_ID)
        self.assertIn("series", valuation)
        if valuation["series"]:
            first_point = valuation["series"][0]
            self.assertIn("total_market_value", first_point)
            self.assertIn("total_profit", first_point)
            self.assertIn("total_return_pct", first_point)

    def test_calculate_valuation_series_includes_cash_balances(self) -> None:
        trades = [self.sample_trade()]
        history_error = {"status": "history_error", "prices": {}}
        cash_date = trades[0].date
        with (
            patch.object(app, "resolve_isin", return_value={}),
            patch.object(app, "fetch_history", return_value=history_error),
            patch.object(app, "fetch_eurostat_cpi", return_value={}),
            patch.object(app, "read_portfolio_dividends", return_value=[]),
            patch.object(app, "read_cash_interests", return_value=[]),
            patch.object(
                app,
                "load_cash_histories",
                return_value=([(cash_date, Decimal("100"), Decimal("100"))], [], []),
            ),
        ):
            valuation = app.calculate_valuation_series(trades, {}, refresh=False, person=app.PRIMARY_PORTFOLIO_ID, broker="all")
        self.assertIn("series", valuation)
        if valuation["series"]:
            first_point = valuation["series"][0]
            self.assertIn("total_net_contributions", first_point)
            last_point = valuation["series"][-1]
            self.assertIn("total_net_contributions", last_point)
            self.assertTrue(last_point["total_net_contributions"] >= 0)


if __name__ == "__main__":
    unittest.main()
