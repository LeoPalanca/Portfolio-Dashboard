"""Typed application settings and filesystem boundaries."""

from __future__ import annotations

import os
from datetime import date as Date
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)


PROJECT_DIR = Path(__file__).resolve().parents[2]


def _xdg_path(variable: str, fallback: Path, suffix: str) -> Path:
    root = Path(os.environ.get(variable, fallback)).expanduser()
    return root / suffix


class PortfolioProfile(BaseModel):
    """A configured portfolio shown by the dashboard."""

    display_name: str
    snapshot_pattern: str | None = None
    trade_republic_name: str | None = None
    history_start: Date | None = None
    features: set[str] = Field(default_factory=set)
    position_quantity_overrides: dict[str, Decimal] = Field(default_factory=dict)
    extra_trades: list[ConfiguredTrade] = Field(default_factory=list)
    extra_frictions: list[ConfiguredFriction] = Field(default_factory=list)
    tax_losses: list[TaxLoss] = Field(default_factory=list)
    todo_items: list[str] = Field(default_factory=list)


class ConfiguredTrade(BaseModel):
    """A local adjustment used when a snapshot lacks a complete transaction ledger."""

    asset: str
    isin: str = ""
    broker: str
    action: str
    date: Date | None = None
    use_history_start: bool = False
    price: Decimal
    quantity: Decimal
    total: Decimal | None = None
    fees: Decimal = Decimal("0")
    tax: Decimal = Decimal("0")
    currency: str = "EUR"
    source: str = "configured_adjustment"


class ConfiguredFriction(BaseModel):
    broker: str
    event_type: str
    date: Date
    amount_eur: Decimal
    description: str


class TaxLoss(BaseModel):
    year: int
    amount_eur: Decimal
    expires_year: int
    broker: str


class Settings(BaseSettings):
    """Configuration loaded from environment variables, ``.env``, or TOML."""

    model_config = SettingsConfigDict(
        env_prefix="PORTFOLIO_",
        env_file=PROJECT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        toml_file=PROJECT_DIR / "config.toml",
    )

    project_dir: Path = PROJECT_DIR
    source_dir: Path = PROJECT_DIR.parent
    data_dir: Path = _xdg_path("XDG_DATA_HOME", Path.home() / ".local" / "share", "portfolio-dashboard")
    cache_dir: Path = _xdg_path("XDG_CACHE_HOME", Path.home() / ".cache", "portfolio-dashboard")

    primary_portfolio_id: str = "primary"
    primary_portfolio_name: str = "Primary Portfolio"
    portfolios: dict[str, PortfolioProfile] = Field(default_factory=dict)
    self_transfer_names: tuple[str, ...] = ()

    manual_trades_file: str = "Spreadsheet - Trades.csv"
    trade_republic_pattern: str = "broker_exports/*/*trade_republic*.csv"
    fineco_pattern: str = "broker_exports/*/*fineco*.xlsx"
    interactive_brokers_pattern: str = "broker_exports/*/*interactive_brokers*.pdf"
    etoro_pattern: str = "broker_exports/*/*etoro*.xlsx"
    revolut_pattern: str = "cash_exports/*/*account-statement*.csv"
    revolut_downloads_pattern: str = "account-statement*.csv"
    intesa_pattern: str = "cash_exports/*/*account_operations*.xlsx"
    intesa_downloads_pattern: str = "account_operations*.xlsx"
    bbva_pattern: str = "cash_exports/*/*bbva*.xls"

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            TomlConfigSettingsSource(settings_cls),
            file_secret_settings,
        )

    @property
    def public_data_dir(self) -> Path:
        return self.project_dir / "data"

    @property
    def family_portfolios(self) -> dict[str, dict[str, str]]:
        return {
            portfolio_id: {
                "name": profile.display_name,
                "pattern": profile.snapshot_pattern or "",
            }
            for portfolio_id, profile in self.portfolios.items()
            if portfolio_id != self.primary_portfolio_id and profile.snapshot_pattern
        }

    def data_path(self, filename: str) -> Path:
        return self.data_dir / filename

    def cache_path(self, filename: str) -> Path:
        return self.cache_dir / filename


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide immutable settings snapshot."""

    return Settings()
