"""SQLite-backed import manifest and normalized financial movement ledger."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from collections.abc import Iterable, Mapping, Sequence
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 2


@dataclass(frozen=True)
class ImportRecord:
    id: int
    portfolio_id: str
    sha256: str
    source_kind: str
    original_name: str
    stored_path: str
    parser_version: str
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

    def __init__(self, path: Path, default_portfolio_id: str = "primary") -> None:
        self.path = path
        self.default_portfolio_id = self._portfolio_id(default_portfolio_id)
        self._initialized = False
        self._initialize_lock = threading.Lock()

    @staticmethod
    def _portfolio_id(value: str | None) -> str:
        portfolio_id = (value or "primary").strip().lower()
        if not portfolio_id:
            raise ValueError("A portfolio id is required")
        return portfolio_id

    def initialize(self) -> None:
        if self._initialized:
            return
        with self._initialize_lock:
            if self._initialized:
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with closing(self._connect()) as connection:
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS schema_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
                )
                imports_exists = connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'imports'"
                ).fetchone()
                if not imports_exists:
                    self._create_schema(connection)
                else:
                    import_columns = {
                        row[1] for row in connection.execute("PRAGMA table_info(imports)")
                    }
                    if "portfolio_id" not in import_columns:
                        self._migrate_v1(connection)
                    else:
                        self._create_schema(connection)
                connection.execute(
                    "INSERT OR REPLACE INTO schema_metadata(key, value) VALUES ('schema_version', ?)",
                    (str(SCHEMA_VERSION),),
                )
                connection.commit()
            self._initialized = True

    @staticmethod
    def _create_schema(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS imports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                portfolio_id TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                source_kind TEXT NOT NULL,
                original_name TEXT NOT NULL,
                stored_path TEXT NOT NULL,
                parser_version TEXT NOT NULL,
                imported_at TEXT NOT NULL,
                movement_count INTEGER NOT NULL DEFAULT 0,
                duplicate_count INTEGER NOT NULL DEFAULT 0,
                UNIQUE(portfolio_id, sha256)
            );
            CREATE TABLE IF NOT EXISTS movements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                portfolio_id TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
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
                metadata_json TEXT NOT NULL DEFAULT '{}',
                UNIQUE(portfolio_id, fingerprint)
            );
            CREATE INDEX IF NOT EXISTS movements_portfolio_date_idx
                ON movements(portfolio_id, occurred_on);
            CREATE INDEX IF NOT EXISTS movements_portfolio_type_idx
                ON movements(portfolio_id, event_type);
            CREATE INDEX IF NOT EXISTS movements_source_kind_idx ON movements(source_kind);
            """
        )

    def _migrate_v1(self, connection: sqlite3.Connection) -> None:
        """Assign the former single-user ledger to the configured primary portfolio."""

        connection.commit()
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.executescript(
            """
            BEGIN;
            ALTER TABLE imports RENAME TO imports_v1;
            ALTER TABLE movements RENAME TO movements_v1;
            COMMIT;
            """
        )
        self._create_schema(connection)
        connection.execute(
            """
            INSERT INTO imports(
                id, portfolio_id, sha256, source_kind, original_name, stored_path,
                parser_version, imported_at, movement_count, duplicate_count
            )
            SELECT id, ?, sha256, source_kind, original_name, stored_path,
                   parser_version, imported_at, movement_count, duplicate_count
            FROM imports_v1
            """,
            (self.default_portfolio_id,),
        )
        connection.execute(
            """
            INSERT INTO movements(
                id, portfolio_id, fingerprint, import_id, occurred_on, event_type,
                source_kind, account, asset, isin, description, currency, amount,
                quantity, price, fees, tax, metadata_json
            )
            SELECT id, ?, fingerprint, import_id, occurred_on, event_type,
                   source_kind, account, asset, isin, description, currency, amount,
                   quantity, price, fees, tax, metadata_json
            FROM movements_v1
            """,
            (self.default_portfolio_id,),
        )
        connection.executescript(
            """
            DROP TABLE movements_v1;
            DROP TABLE imports_v1;
            """
        )
        self._create_schema(connection)
        connection.commit()
        connection.execute("PRAGMA foreign_keys = ON")

    def import_by_hash(self, sha256: str, portfolio_id: str | None = None) -> ImportRecord | None:
        self.initialize()
        owner = self._portfolio_id(portfolio_id or self.default_portfolio_id)
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT id, portfolio_id, sha256, source_kind, original_name, stored_path, "
                "parser_version, movement_count, duplicate_count, imported_at "
                "FROM imports WHERE portfolio_id = ? AND sha256 = ?",
                (owner, sha256),
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
        portfolio_id: str | None = None,
    ) -> ImportRecord:
        self.initialize()
        owner = self._portfolio_id(portfolio_id or self.default_portfolio_id)
        imported_at = datetime.now(UTC).isoformat(timespec="seconds")
        inserted = 0
        duplicates = 0
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                "INSERT INTO imports(portfolio_id, sha256, source_kind, original_name, stored_path, parser_version, imported_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (owner, sha256, source_kind, original_name, stored_path, parser_version, imported_at),
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
                        portfolio_id, fingerprint, import_id, occurred_on, event_type,
                        source_kind, account, asset, isin, description, currency, amount,
                        quantity, price, fees, tax, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        owner,
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
        return ImportRecord(
            import_id,
            owner,
            sha256,
            source_kind,
            original_name,
            stored_path,
            parser_version,
            inserted,
            duplicates,
            imported_at,
        )

    def enrich_import(
        self,
        record: ImportRecord,
        *,
        parser_version: str,
        movements: Iterable[Mapping[str, Any]],
    ) -> tuple[int, int]:
        """Merge movements produced by a newer parser into an existing file import."""

        self.initialize()
        inserted = 0
        duplicates = 0
        with closing(self._connect()) as connection, connection:
            for movement in movements:
                canonical = self._canonical_movement(record.source_kind, movement)
                fingerprint_fields = {key: value for key, value in canonical.items() if key != "metadata_json"}
                fingerprint = hashlib.sha256(
                    json.dumps(fingerprint_fields, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
                ).hexdigest()
                result = connection.execute(
                    """
                    INSERT OR IGNORE INTO movements(
                        portfolio_id, fingerprint, import_id, occurred_on, event_type,
                        source_kind, account, asset, isin, description, currency, amount,
                        quantity, price, fees, tax, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.portfolio_id,
                        fingerprint,
                        record.id,
                        canonical["occurred_on"],
                        canonical["event_type"],
                        record.source_kind,
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
                """
                UPDATE imports
                SET parser_version = ?, movement_count = movement_count + ?
                WHERE id = ? AND portfolio_id = ?
                """,
                (parser_version, inserted, record.id, record.portfolio_id),
            )
        return inserted, duplicates

    def movements(
        self,
        portfolio_id: str | None = None,
        event_types: Sequence[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return canonical rows for one portfolio in deterministic date/id order."""

        self.initialize()
        owner = self._portfolio_id(portfolio_id or self.default_portfolio_id)
        parameters: list[Any] = [owner]
        where = "WHERE portfolio_id = ?"
        if event_types:
            placeholders = ", ".join("?" for _ in event_types)
            where += f" AND event_type IN ({placeholders})"
            parameters.extend(event_types)
        with closing(self._connect()) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                f"""
                SELECT id, portfolio_id, import_id, occurred_on, event_type, source_kind,
                       account, asset, isin, description, currency, amount, quantity,
                       price, fees, tax, metadata_json
                FROM movements {where} ORDER BY occurred_on, id
                """,
                parameters,
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            try:
                item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
            except json.JSONDecodeError:
                item["metadata"] = {}
            result.append(item)
        return result

    def summary(self, portfolio_id: str | None = None) -> dict[str, Any]:
        self.initialize()
        where = ""
        parameters: tuple[Any, ...] = ()
        if portfolio_id is not None:
            where = "WHERE i.portfolio_id = ?"
            parameters = (self._portfolio_id(portfolio_id),)
        with closing(self._connect()) as connection:
            imports = int(connection.execute(f"SELECT COUNT(*) FROM imports i {where}", parameters).fetchone()[0])
            movement_where = where.replace("i.portfolio_id", "m.portfolio_id")
            movements = int(connection.execute(f"SELECT COUNT(*) FROM movements m {movement_where}", parameters).fetchone()[0])
            sources = [
                {"source": row[0], "imports": int(row[1]), "movements": int(row[2] or 0)}
                for row in connection.execute(
                    f"""
                    SELECT i.source_kind, COUNT(DISTINCT i.id), COUNT(m.id)
                    FROM imports i LEFT JOIN movements m ON m.import_id = i.id
                    {where}
                    GROUP BY i.source_kind ORDER BY i.source_kind
                    """,
                    parameters,
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
