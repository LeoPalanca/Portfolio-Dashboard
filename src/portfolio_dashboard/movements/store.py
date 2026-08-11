"""SQLite-backed import manifest and normalized financial movement ledger."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterable, Mapping
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ImportRecord:
    id: int
    sha256: str
    source_kind: str
    original_name: str
    stored_path: str
    movement_count: int
    duplicate_count: int
    imported_at: str


def _json_default(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"Unsupported movement value: {type(value).__name__}")


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


class MovementStore:
    """Persist imports and deduplicated normalized movements in one local database."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection, connection:
            connection.executescript(
                """
                PRAGMA foreign_keys = ON;
                CREATE TABLE IF NOT EXISTS schema_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS imports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sha256 TEXT NOT NULL UNIQUE,
                    source_kind TEXT NOT NULL,
                    original_name TEXT NOT NULL,
                    stored_path TEXT NOT NULL,
                    parser_version TEXT NOT NULL,
                    imported_at TEXT NOT NULL,
                    movement_count INTEGER NOT NULL DEFAULT 0,
                    duplicate_count INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS movements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fingerprint TEXT NOT NULL UNIQUE,
                    import_id INTEGER NOT NULL REFERENCES imports(id) ON DELETE RESTRICT,
                    occurred_on TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    source_kind TEXT NOT NULL,
                    account TEXT NOT NULL DEFAULT '',
                    asset TEXT NOT NULL DEFAULT '',
                    isin TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    currency TEXT NOT NULL DEFAULT '',
                    amount TEXT NOT NULL DEFAULT '',
                    quantity TEXT NOT NULL DEFAULT '',
                    price TEXT NOT NULL DEFAULT '',
                    fees TEXT NOT NULL DEFAULT '',
                    tax TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS movements_occurred_on_idx ON movements(occurred_on);
                CREATE INDEX IF NOT EXISTS movements_source_kind_idx ON movements(source_kind);
                """
            )
            connection.execute(
                "INSERT OR REPLACE INTO schema_metadata(key, value) VALUES ('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )

    def import_by_hash(self, sha256: str) -> ImportRecord | None:
        self.initialize()
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT id, sha256, source_kind, original_name, stored_path, movement_count, duplicate_count, imported_at "
                "FROM imports WHERE sha256 = ?",
                (sha256,),
            ).fetchone()
        return ImportRecord(*row) if row else None

    def record_import(
        self,
        *,
        sha256: str,
        source_kind: str,
        original_name: str,
        stored_path: str,
        parser_version: str,
        movements: Iterable[Mapping[str, Any]],
    ) -> ImportRecord:
        self.initialize()
        imported_at = datetime.now(UTC).isoformat(timespec="seconds")
        inserted = 0
        duplicates = 0
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                "INSERT INTO imports(sha256, source_kind, original_name, stored_path, parser_version, imported_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (sha256, source_kind, original_name, stored_path, parser_version, imported_at),
            )
            if cursor.lastrowid is None:  # pragma: no cover - SQLite always supplies this value
                raise RuntimeError("SQLite did not return an import id")
            import_id = cursor.lastrowid
            for movement in movements:
                canonical = self._canonical_movement(source_kind, movement)
                fingerprint_fields = {key: value for key, value in canonical.items() if key != "metadata_json"}
                fingerprint = hashlib.sha256(
                    json.dumps(fingerprint_fields, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
                ).hexdigest()
                result = connection.execute(
                    """
                    INSERT OR IGNORE INTO movements(
                        fingerprint, import_id, occurred_on, event_type, source_kind,
                        account, asset, isin, description, currency, amount, quantity,
                        price, fees, tax, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        fingerprint,
                        import_id,
                        canonical["occurred_on"],
                        canonical["event_type"],
                        source_kind,
                        canonical["account"],
                        canonical["asset"],
                        canonical["isin"],
                        canonical["description"],
                        canonical["currency"],
                        canonical["amount"],
                        canonical["quantity"],
                        canonical["price"],
                        canonical["fees"],
                        canonical["tax"],
                        canonical["metadata_json"],
                    ),
                )
                if result.rowcount:
                    inserted += 1
                else:
                    duplicates += 1
            connection.execute(
                "UPDATE imports SET movement_count = ?, duplicate_count = ? WHERE id = ?",
                (inserted, duplicates, import_id),
            )
        return ImportRecord(import_id, sha256, source_kind, original_name, stored_path, inserted, duplicates, imported_at)

    def summary(self) -> dict[str, Any]:
        self.initialize()
        with closing(self._connect()) as connection:
            imports = int(connection.execute("SELECT COUNT(*) FROM imports").fetchone()[0])
            movements = int(connection.execute("SELECT COUNT(*) FROM movements").fetchone()[0])
            sources = [
                {"source": row[0], "imports": int(row[1]), "movements": int(row[2] or 0)}
                for row in connection.execute(
                    """
                    SELECT i.source_kind, COUNT(DISTINCT i.id), COUNT(m.id)
                    FROM imports i LEFT JOIN movements m ON m.import_id = i.id
                    GROUP BY i.source_kind ORDER BY i.source_kind
                    """
                )
            ]
        return {"imports": imports, "movements": movements, "sources": sources}

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _canonical_movement(source_kind: str, movement: Mapping[str, Any]) -> dict[str, str]:
        occurred_on = _text(movement.get("occurred_on") or movement.get("date") or movement.get("datetime"))
        if not occurred_on:
            raise ValueError("Every normalized movement requires a date")
        metadata = movement.get("metadata") or {}
        return {
            "occurred_on": occurred_on,
            "event_type": _text(movement.get("event_type") or "movement"),
            "source_kind": source_kind,
            "account": _text(movement.get("account") or movement.get("broker")),
            "asset": _text(movement.get("asset")),
            "isin": _text(movement.get("isin")),
            "description": _text(movement.get("description") or movement.get("merchant")),
            "currency": _text(movement.get("currency") or movement.get("cash_currency")),
            "amount": _text(movement.get("amount") or movement.get("amount_eur") or movement.get("grand_total")),
            "quantity": _text(movement.get("quantity")),
            "price": _text(movement.get("price")),
            "fees": _text(movement.get("fees")),
            "tax": _text(movement.get("tax") or movement.get("tax_eur")),
            "metadata_json": json.dumps(metadata, ensure_ascii=False, sort_keys=True, default=_json_default),
        }
