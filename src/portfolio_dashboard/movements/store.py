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
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 4


def _event_family(kind: str) -> str:
    return (
        "bank"
        if kind
        in {"income", "spend", "credit", "personal_transfer", "investment", "fee", "cash_withdrawal", "cash_movement", "top_up"}
        else kind
    )


def _movement_fingerprint(canonical: Mapping[str, str]) -> str:
    fields = {key: value for key, value in canonical.items() if key != "metadata_json"}
    metadata = json.loads(canonical.get("metadata_json") or "{}")
    transaction_id = str(metadata.get("transaction_id") or "").strip()
    if transaction_id:
        fields = {
            "source_kind": canonical.get("source_kind", ""),
            "account": canonical.get("account", ""),
            "event_family": _event_family(canonical.get("event_type", "")),
            "transaction_id": transaction_id,
        }
    elif int(metadata.get("source_occurrence") or 1) > 1:
        fields["source_occurrence"] = str(metadata["source_occurrence"])
    for key in ("amount", "quantity", "price", "fees", "tax"):
        value = fields.get(key, "")
        if value == "":
            continue
        try:
            number = Decimal(value)
        except InvalidOperation:
            continue
        if number.is_finite():
            text = format(number, "f")
            fields[key] = "0" if number == 0 else text.rstrip("0").rstrip(".") if "." in text else text
    return hashlib.sha256(
        json.dumps(fields, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _pairing_key(row: Mapping[str, Any]) -> tuple[str | bool, ...]:
    """What must stay the same for a re-parsed row to replace an earlier reading of it."""

    return (
        str(row.get("occurred_on") or "")[:10],
        _event_family(str(row.get("event_type") or "")),
        str(row.get("account") or ""),
        str(row.get("asset") or ""),
        str(row.get("isin") or ""),
        str(row.get("currency") or ""),
        str(row.get("amount") or "").lstrip().startswith("-"),
    )


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
                    schema = connection.execute(
                        "SELECT value FROM schema_metadata WHERE key='schema_version'"
                    ).fetchone()
                    if schema and int(schema[0]) == 3:
                        backup = self.path.with_name(f"{self.path.name}.pre-ledger-v4.bak")
                        if not backup.exists():
                            with (
                                closing(sqlite3.connect(self.path)) as source,
                                closing(sqlite3.connect(backup)) as target,
                            ):
                                source.backup(target)
                    import_columns = {row[1] for row in connection.execute("PRAGMA table_info(imports)")}
                    if "portfolio_id" not in import_columns:
                        self._migrate_v1(connection)
                    else:
                        self._create_schema(connection)
                connection.commit()
                self._migrate_numeric_fingerprints(connection)
                connection.execute(
                    "INSERT OR REPLACE INTO schema_metadata(key, value) VALUES ('schema_version', ?)",
                    (str(SCHEMA_VERSION),),
                )
                connection.commit()
            self._initialized = True

    def _migrate_numeric_fingerprints(self, connection: sqlite3.Connection) -> None:
        """Reconcile formatting-only duplicates atomically, preserving a SQLite backup."""

        connection.execute("BEGIN IMMEDIATE")
        version = connection.execute("SELECT value FROM schema_metadata WHERE key = 'schema_version'").fetchone()
        if version and int(version[0]) >= 3:
            return
        cursor = connection.execute("SELECT * FROM movements ORDER BY id")
        columns = [column[0] for column in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor]
        if not rows:
            return
        backup = self.path.with_name(
            f"{self.path.name}.pre-numeric-v3-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}.bak"
        )
        with closing(sqlite3.connect(self.path)) as source, closing(sqlite3.connect(backup)) as target:
            source.backup(target)
        seen: set[tuple[str, str]] = set()
        survivors: list[tuple[str, int]] = []
        for row in rows:
            canonical = {
                key: value
                for key, value in row.items()
                if key not in {"id", "portfolio_id", "import_id", "fingerprint"}
            }
            fingerprint = _movement_fingerprint(canonical)
            identity = (row["portfolio_id"], fingerprint)
            if identity in seen:
                connection.execute("DELETE FROM movements WHERE id = ?", (row["id"],))
                connection.execute(
                    "UPDATE imports SET movement_count = movement_count - 1, "
                    "duplicate_count = duplicate_count + 1 WHERE id = ?",
                    (row["import_id"],),
                )
            else:
                seen.add(identity)
                survivors.append((fingerprint, row["id"]))
        # Temporary unique keys prevent collisions while replacing legacy hashes.
        connection.execute("UPDATE movements SET fingerprint = 'numeric-v3:' || id")
        connection.executemany("UPDATE movements SET fingerprint = ? WHERE id = ?", survivors)

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
            CREATE TABLE IF NOT EXISTS movement_revisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT, movement_id INTEGER NOT NULL,
                changed_at TEXT NOT NULL, previous_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS removed_imports (
                portfolio_id TEXT NOT NULL, sha256 TEXT NOT NULL, source_kind TEXT NOT NULL,
                original_name TEXT NOT NULL, removed_at TEXT NOT NULL,
                PRIMARY KEY (portfolio_id, sha256)
            );
            CREATE TABLE IF NOT EXISTS import_coverage (
                import_id INTEGER NOT NULL REFERENCES imports(id) ON DELETE CASCADE,
                account TEXT NOT NULL, first_day TEXT NOT NULL, last_day TEXT NOT NULL,
                PRIMARY KEY (import_id, account, first_day, last_day)
            );
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
            claimed: set[int] = set()
            for canonical in self._canonical_batch(source_kind, movements):
                matched = self._reconcile_movement(connection, owner, source_kind, canonical, claimed)
                if matched:
                    claimed.add(matched)
                    duplicates += 1
                    continue
                if self._insert(connection, owner, import_id, source_kind, canonical):
                    claimed.add(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
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
    ) -> tuple[int, int, int]:
        """Replace one file's movements with what a newer parser reads from the same file.

        Rows the parser still produces are matched and corrected in place, keeping their
        ids and therefore the user's categories. A row of this import the parser now
        reads differently is updated in place when it pairs unambiguously with a changed
        row of the same day, kind and asset; rows it no longer produces are removed, with
        a revision kept. Re-parsing therefore never appends a second copy of a movement.
        Returns ``(inserted, matched, removed)``.
        """

        self.initialize()
        inserted = 0
        matched = 0
        removed = 0
        owner = record.portfolio_id
        with closing(self._connect()) as connection, connection:
            claimed: set[int] = set()
            pending: list[dict[str, str]] = []
            pending_fingerprints: set[str] = set()
            for canonical in self._canonical_batch(record.source_kind, movements):
                found = self._reconcile_movement(connection, owner, record.source_kind, canonical, claimed)
                fingerprint = _movement_fingerprint(canonical)
                if found:
                    claimed.add(found)
                    matched += 1
                elif fingerprint in pending_fingerprints:
                    matched += 1
                else:
                    pending_fingerprints.add(fingerprint)
                    pending.append(canonical)
            leftovers: dict[tuple[str | bool, ...], list[dict[str, Any]]] = {}
            for row in self._import_rows(connection, record.id):
                if row["id"] not in claimed:
                    leftovers.setdefault(_pairing_key(row), []).append(row)
            for key, group in self._group(pending).items():
                previous = leftovers.get(key, [])
                if len(previous) == len(group):
                    for old, canonical in zip(previous, group):
                        self._replace_row(connection, owner, old, canonical)
                    matched += len(group)
                    leftovers.pop(key, None)
                    continue
                for canonical in group:
                    if self._insert(connection, owner, record.id, record.source_kind, canonical):
                        inserted += 1
                    else:
                        matched += 1
            for group in leftovers.values():
                for row in group:
                    self._remove_row(connection, owner, row, f"reparsed import {record.id}")
                    removed += 1
            connection.execute(
                """
                UPDATE imports
                SET parser_version = ?,
                    movement_count = (SELECT COUNT(*) FROM movements WHERE import_id = imports.id)
                WHERE id = ? AND portfolio_id = ?
                """,
                (parser_version, record.id, owner),
            )
        return inserted, matched, removed

    def imports(self, portfolio_id: str | None = None) -> list[ImportRecord]:
        """Every import of one portfolio, oldest first, with its live movement count."""

        self.initialize()
        owner = self._portfolio_id(portfolio_id or self.default_portfolio_id)
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT i.id, i.portfolio_id, i.sha256, i.source_kind, i.original_name, i.stored_path, "
                "i.parser_version, (SELECT COUNT(*) FROM movements m WHERE m.import_id = i.id), "
                "i.duplicate_count, i.imported_at FROM imports i WHERE i.portfolio_id = ? ORDER BY i.id",
                (owner,),
            ).fetchall()
        return [ImportRecord(*row) for row in rows]

    def set_coverage(self, import_id: int, ranges: Iterable[tuple[str, date, date]]) -> None:
        """Record the days a file covers per account (inclusive), replacing what it recorded before.

        Rows a file shares with an earlier file are stored under that file only, so the
        stored rows understate what a later, overlapping file covers; the parser's full
        reading does not.
        """

        self.initialize()
        with closing(self._connect()) as connection, connection:
            connection.execute("DELETE FROM import_coverage WHERE import_id = ?", (import_id,))
            connection.executemany(
                "INSERT OR IGNORE INTO import_coverage(import_id, account, first_day, last_day) VALUES (?, ?, ?, ?)",
                [(import_id, account, first.isoformat(), last.isoformat()) for account, first, last in ranges],
            )

    def coverage(self, portfolio_id: str | None = None) -> list[tuple[int, str, date, date]]:
        """``(import_id, account, first_day, last_day)`` for every import of one portfolio that recorded its coverage."""

        self.initialize()
        owner = self._portfolio_id(portfolio_id or self.default_portfolio_id)
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT c.import_id, c.account, c.first_day, c.last_day FROM import_coverage c "
                "JOIN imports i ON i.id = c.import_id WHERE i.portfolio_id = ? ORDER BY c.first_day",
                (owner,),
            ).fetchall()
        return [(int(row[0]), str(row[1]), date.fromisoformat(row[2]), date.fromisoformat(row[3])) for row in rows]

    def delete_import(self, record: ImportRecord) -> int:
        """Remove an import and the movements it stored; remember the file so it is not re-imported."""

        self.initialize()
        owner = record.portfolio_id
        removed_at = datetime.now(UTC).isoformat(timespec="seconds")
        with closing(self._connect()) as connection, connection:
            rows = self._import_rows(connection, record.id)
            for row in rows:
                self._remove_row(connection, owner, row, f"deleted import {record.id}")
            connection.execute("DELETE FROM import_coverage WHERE import_id = ?", (record.id,))
            connection.execute("DELETE FROM imports WHERE id = ? AND portfolio_id = ?", (record.id, owner))
            connection.execute(
                "INSERT OR REPLACE INTO removed_imports(portfolio_id, sha256, source_kind, original_name, removed_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (owner, record.sha256, record.source_kind, record.original_name, removed_at),
            )
        return len(rows)

    def mark_for_reread(self, record: ImportRecord) -> None:
        """Make the next startup read this file again, e.g. after it could not be read now."""

        self.initialize()
        with closing(self._connect()) as connection, connection:
            connection.execute(
                "UPDATE imports SET parser_version = 'reread-pending' WHERE id = ? AND portfolio_id = ?",
                (record.id, record.portfolio_id),
            )

    def is_removed(self, sha256: str, portfolio_id: str | None = None) -> bool:
        self.initialize()
        owner = self._portfolio_id(portfolio_id or self.default_portfolio_id)
        with closing(self._connect()) as connection:
            return (
                connection.execute(
                    "SELECT 1 FROM removed_imports WHERE portfolio_id = ? AND sha256 = ?", (owner, sha256)
                ).fetchone()
                is not None
            )

    def forget_removed(self, sha256: str, portfolio_id: str | None = None) -> None:
        """An explicit upload brings a deleted file back."""

        self.initialize()
        owner = self._portfolio_id(portfolio_id or self.default_portfolio_id)
        with closing(self._connect()) as connection, connection:
            connection.execute("DELETE FROM removed_imports WHERE portfolio_id = ? AND sha256 = ?", (owner, sha256))

    @staticmethod
    def _import_rows(connection: sqlite3.Connection, import_id: int) -> list[dict[str, Any]]:
        cursor = connection.execute("SELECT * FROM movements WHERE import_id = ? ORDER BY id", (import_id,))
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row)) for row in cursor]

    @staticmethod
    def _group(items: list[dict[str, str]]) -> dict[tuple[str | bool, ...], list[dict[str, str]]]:
        groups: dict[tuple[str | bool, ...], list[dict[str, str]]] = {}
        for item in items:
            groups.setdefault(_pairing_key(item), []).append(item)
        return groups

    @staticmethod
    def _insert(connection: sqlite3.Connection, owner: str, import_id: int, source_kind: str, canonical: Mapping[str, str]) -> bool:
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
                _movement_fingerprint(canonical),
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
        return bool(result.rowcount)

    @staticmethod
    def _replace_row(connection: sqlite3.Connection, owner: str, previous: Mapping[str, Any], canonical: Mapping[str, str]) -> None:
        connection.execute(
            "INSERT INTO movement_revisions(movement_id, changed_at, previous_json) VALUES (?, ?, ?)",
            (previous["id"], datetime.now(UTC).isoformat(), json.dumps(dict(previous), ensure_ascii=False)),
        )
        keys = list(canonical)
        connection.execute(
            f"UPDATE movements SET {', '.join(key + '=?' for key in keys)}, fingerprint=? WHERE id=? AND portfolio_id=?",
            [canonical[key] for key in keys] + [_movement_fingerprint(canonical), previous["id"], owner],
        )

    @staticmethod
    def _remove_row(connection: sqlite3.Connection, owner: str, row: Mapping[str, Any], reason: str) -> None:
        connection.execute(
            "INSERT INTO movement_revisions(movement_id, changed_at, previous_json) VALUES (?, ?, ?)",
            (row["id"], datetime.now(UTC).isoformat(), json.dumps({**row, "removed": reason}, ensure_ascii=False)),
        )
        connection.execute("DELETE FROM movements WHERE id = ? AND portfolio_id = ?", (row["id"], owner))

    @staticmethod
    def _reconcile_movement(connection, owner, source, canonical, claimed) -> int:
        """Update one unambiguous source event in place; never append a reclassification."""
        fingerprint = _movement_fingerprint(canonical)
        cursor = connection.execute(
            "SELECT * FROM movements WHERE portfolio_id=? AND source_kind=? AND (occurred_on=? OR fingerprint=?)",
            (owner, source, canonical["occurred_on"], fingerprint),
        )
        columns = [column[0] for column in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor]
        metadata = json.loads(canonical["metadata_json"])
        external_id = str(metadata.get("transaction_id") or "")

        def legacy_key(item):
            fields = {key: item.get(key, "") for key in canonical if key != "metadata_json"}
            fields["event_type"] = _event_family(fields["event_type"])
            return _movement_fingerprint(fields)

        candidates = [row for row in rows if row["fingerprint"] == fingerprint]
        if not candidates:
            key = legacy_key(canonical)
            for row in rows:
                if row["id"] in claimed:
                    continue
                previous_id = str(json.loads(row["metadata_json"]).get("transaction_id") or "")
                if external_id and previous_id and external_id != previous_id:
                    continue
                if not external_id and int(metadata.get("source_occurrence") or 1) != int(
                    json.loads(row["metadata_json"]).get("source_occurrence") or 1
                ):
                    continue
                if legacy_key(row) == key:
                    candidates.append(row)
        if len(candidates) > 1:
            raise ValueError(
                "Ambiguous transaction identity; existing rows were preserved. Review the source transaction IDs."
            )
        if not candidates:
            return 0
        previous = candidates[0]
        previous_id = json.loads(previous["metadata_json"]).get("transaction_id")
        if previous_id and not external_id:
            metadata["transaction_id"] = previous_id
            canonical["metadata_json"] = json.dumps(metadata, ensure_ascii=False, sort_keys=True, default=_json_default)
            fingerprint = _movement_fingerprint(canonical)
        if all(previous[key] == value for key, value in canonical.items()) and previous["fingerprint"] == fingerprint:
            return previous["id"]
        connection.execute(
            "INSERT INTO movement_revisions(movement_id, changed_at, previous_json) VALUES (?, ?, ?)",
            (previous["id"], datetime.now(UTC).isoformat(), json.dumps(previous, ensure_ascii=False)),
        )
        keys = list(canonical)
        connection.execute(
            f"UPDATE movements SET {', '.join(key + '=?' for key in keys)}, fingerprint=? WHERE id=? AND portfolio_id=?",
            [canonical[key] for key in keys] + [fingerprint, previous["id"], owner],
        )
        return previous["id"]

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
            movements = int(
                connection.execute(f"SELECT COUNT(*) FROM movements m {movement_where}", parameters).fetchone()[0]
            )
            sources = [
                {
                    "source": row[0],
                    "imports": int(row[1]),
                    "movements": int(row[2] or 0),
                    "last_imported_at": row[3],
                }
                for row in connection.execute(
                    f"""
                    SELECT i.source_kind, COUNT(DISTINCT i.id), COUNT(m.id), MAX(i.imported_at)
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

    def revision(self) -> list[int]:
        """Financial changes only: manual cash/category writes must not rebuild prices."""
        if not self.path.exists():
            return [0, 0, 0]
        with closing(sqlite3.connect(self.path.absolute().as_uri() + "?mode=ro", uri=True)) as connection:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "movements" not in tables:
                return [0, 0, 0]
            count, maximum = connection.execute("SELECT COUNT(*), COALESCE(MAX(id),0) FROM movements").fetchone()
            revision = (
                connection.execute("SELECT COALESCE(MAX(id),0) FROM movement_revisions").fetchone()[0]
                if "movement_revisions" in tables
                else 0
            )
        return [count, maximum, revision]

    @staticmethod
    def _canonical_batch(source_kind, movements):
        counts = {}
        for movement in movements:
            canonical = MovementStore._canonical_movement(source_kind, movement)
            metadata = json.loads(canonical["metadata_json"])
            if not metadata.get("transaction_id"):
                metadata.pop("source_occurrence", None)
                canonical["metadata_json"] = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
                key = _movement_fingerprint(canonical)
                counts[key] = counts.get(key, 0) + 1
                metadata["source_occurrence"] = counts[key]
                canonical["metadata_json"] = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
            yield canonical

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
