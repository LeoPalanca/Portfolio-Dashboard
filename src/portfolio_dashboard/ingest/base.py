"""Extensible broker adapter contract."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ..domain import Trade


class BrokerAdapter(Protocol):
    """Discover and parse the latest export for one broker."""

    name: str

    def discover(self) -> Path | None: ...

    def parse(self, path: Path) -> list[Trade]: ...


@dataclass(frozen=True)
class FunctionBrokerAdapter:
    """Adapter wrapper used while legacy parser functions are extracted."""

    name: str
    discover_export: Callable[[], Path | None]
    parse_export: Callable[[Path], list[Trade]]

    def discover(self) -> Path | None:
        return self.discover_export()

    def parse(self, path: Path) -> list[Trade]:
        return self.parse_export(path)

