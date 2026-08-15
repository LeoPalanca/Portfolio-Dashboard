from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from src.portfolio_dashboard.config import PortfolioProfile, Settings
from src.portfolio_dashboard.version import APP_VERSION, display_version


class SettingsTest(unittest.TestCase):
    def test_application_version_comes_from_project_metadata(self) -> None:
        self.assertRegex(APP_VERSION, r"^\d+\.\d+\.\d+")

    def test_private_edition_suffix_is_display_only(self) -> None:
        self.assertEqual(display_version("1.2.3", "L"), "1.2.3L")
        self.assertEqual(display_version("1.2.3"), "1.2.3")
        with self.assertRaises(ValueError):
            display_version("1.2.3", "+private")

    def test_paths_and_profiles_are_derived_from_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = Settings(
                project_dir=root / "project",
                source_dir=root / "sources",
                data_dir=root / "private",
                cache_dir=root / "cache",
                primary_portfolio_id="owner",
                portfolios={
                    "household_a": PortfolioProfile(
                        display_name="Household A",
                        snapshot_pattern="snapshots/*household_a*.csv",
                    )
                },
            )

        self.assertEqual(settings.data_path("positions.csv"), root / "private" / "positions.csv")
        self.assertEqual(settings.cache_path("prices.json"), root / "cache" / "prices.json")
        self.assertEqual(
            settings.family_portfolios["household_a"],
            {
                "name": "Household A",
                "pattern": "snapshots/*household_a*.csv",
            },
        )
