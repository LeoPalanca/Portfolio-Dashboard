"""Compact, per-symbol historical price storage."""

from __future__ import annotations

import json
import os
import threading
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import quote


class HistoryStore:
    """Store one merged date-to-price series per logical symbol."""

    VERSION = 1

    def __init__(self, directory: Path, legacy_file: Path | None = None) -> None:
        self.directory = directory
        self.legacy_file = legacy_file
        self._memory: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._migration_checked = False

    def get_range(self, cache_key: str, start: date, end: date, now: int, ttl_seconds: int) -> dict[str, Any] | None:
        with self._lock:
            record = self._read(cache_key)
            if record.get("status") != "priced":
                return None
            for coverage in record.get("ranges", []):
                try:
                    covered_start = date.fromisoformat(str(coverage["start"]))
                    covered_end = date.fromisoformat(str(coverage["end"]))
                    fetched_at = int(coverage["fetched_at"])
                except (KeyError, TypeError, ValueError):
                    continue
                if covered_start <= start and covered_end >= end and now - fetched_at < ttl_seconds:
                    return self._payload(record, start, end, fetched_at)
        return None

    def merge(self, cache_key: str, payload: dict[str, Any], start: date, end: date) -> dict[str, Any]:
        if payload.get("status") != "priced":
            return payload
        fetched_at = int(payload.get("fetched_at", 0))
        with self._lock:
            existing = self._read(cache_key)
            prices = dict(existing.get("prices", {}))
            prices.update(
                {
                    str(price_date): float(price)
                    for price_date, price in payload.get("prices", {}).items()
                    if price is not None
                }
            )
            ranges = list(existing.get("ranges", []))
            ranges.append({"start": start.isoformat(), "end": end.isoformat(), "fetched_at": fetched_at})
            record = {
                "version": self.VERSION,
                "cache_key": cache_key,
                "symbol": payload.get("symbol") or existing.get("symbol") or cache_key,
                "currency": payload.get("currency") or existing.get("currency") or "",
                "status": "priced",
                "prices": prices,
                "ranges": self._compact_ranges(ranges),
                "updated_at": max(fetched_at, int(existing.get("updated_at", 0))),
            }
            self._write(cache_key, record)
            return self._payload(record, start, end, fetched_at)

    def latest_price(self, cache_key: str) -> dict[str, Any] | None:
        with self._lock:
            record = self._read(cache_key)
            prices = record.get("prices", {})
            if record.get("status") != "priced" or not prices:
                return None
            latest_date = max(prices)
            return {
                "symbol": record.get("symbol") or cache_key,
                "currency": record.get("currency") or "",
                "price": float(prices[latest_date]),
                "price_date": latest_date,
            }

    def clear_memory(self) -> None:
        with self._lock:
            self._memory.clear()

    def _payload(self, record: dict[str, Any], start: date, end: date, fetched_at: int) -> dict[str, Any]:
        return {
            "symbol": record.get("symbol"),
            "currency": record.get("currency"),
            "prices": record.get("prices", {}),
            "status": "priced",
            "fetched_at": fetched_at,
            "range_start": start.isoformat(),
            "range_end": end.isoformat(),
        }

    def _path(self, cache_key: str) -> Path:
        return self.directory / f"{quote(cache_key, safe='')}.json"

    def _read(self, cache_key: str) -> dict[str, Any]:
        self._migrate_legacy()
        cached = self._memory.get(cache_key)
        if cached is not None:
            return cached
        path = self._path(cache_key)
        if not path.exists():
            record: dict[str, Any] = {}
        else:
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                record = value if isinstance(value, dict) else {}
            except (OSError, json.JSONDecodeError):
                record = {}
        self._memory[cache_key] = record
        return record

    def _write(self, cache_key: str, record: dict[str, Any]) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self._path(cache_key)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        try:
            temporary.write_text(
                json.dumps(record, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
            temporary.replace(path)
            self._memory[cache_key] = record
        finally:
            if temporary.exists():
                temporary.unlink(missing_ok=True)

    @staticmethod
    def _compact_ranges(ranges: list[dict[str, Any]]) -> list[dict[str, Any]]:
        valid: list[dict[str, Any]] = []
        for item in ranges:
            try:
                start = date.fromisoformat(str(item["start"]))
                end = date.fromisoformat(str(item["end"]))
                fetched_at = int(item["fetched_at"])
            except (KeyError, TypeError, ValueError):
                continue
            if end < start:
                continue
            valid.append({"start": start.isoformat(), "end": end.isoformat(), "fetched_at": fetched_at})

        retained: list[dict[str, Any]] = []
        for candidate in sorted(valid, key=lambda item: int(item["fetched_at"]), reverse=True):
            candidate_start = date.fromisoformat(candidate["start"])
            candidate_end = date.fromisoformat(candidate["end"])
            if any(
                date.fromisoformat(item["start"]) <= candidate_start
                and date.fromisoformat(item["end"]) >= candidate_end
                for item in retained
            ):
                continue
            retained.append(candidate)
        return sorted(retained, key=lambda item: (item["start"], item["end"], item["fetched_at"]))

    def _migrate_legacy(self) -> None:
        if self._migration_checked:
            return
        self._migration_checked = True
        marker = self.directory / ".migrated-v1"
        if marker.exists() or self.legacy_file is None or not self.legacy_file.exists():
            return

        try:
            legacy_value = json.loads(self.legacy_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(legacy_value, dict):
            return

        grouped: dict[str, list[tuple[str, dict[str, Any]]]] = {}
        for legacy_key, payload in legacy_value.items():
            if not isinstance(payload, dict) or payload.get("status") != "priced":
                continue
            parts = str(legacy_key).split("|")
            if len(parts) != 3:
                continue
            grouped.setdefault(parts[0], []).append((str(legacy_key), payload))

        for cache_key, entries in grouped.items():
            prices: dict[str, float] = {}
            ranges: list[dict[str, Any]] = []
            symbol = cache_key
            currency = ""
            updated_at = 0
            for legacy_key, payload in sorted(entries, key=lambda item: int(item[1].get("fetched_at", 0))):
                _, range_start, range_end = legacy_key.split("|")
                fetched_at = int(payload.get("fetched_at", 0))
                prices.update(
                    {
                        str(price_date): float(price)
                        for price_date, price in payload.get("prices", {}).items()
                        if price is not None
                    }
                )
                ranges.append({"start": range_start, "end": range_end, "fetched_at": fetched_at})
                symbol = str(payload.get("symbol") or symbol)
                currency = str(payload.get("currency") or currency)
                updated_at = max(updated_at, fetched_at)
            record = {
                "version": self.VERSION,
                "cache_key": cache_key,
                "symbol": symbol,
                "currency": currency,
                "status": "priced",
                "prices": prices,
                "ranges": self._compact_ranges(ranges),
                "updated_at": updated_at,
            }
            self._write(cache_key, record)

        self.directory.mkdir(parents=True, exist_ok=True)
        marker.write_text("1\n", encoding="utf-8")
        archive_directory = self.legacy_file.parent / "legacy"
        archive_directory.mkdir(parents=True, exist_ok=True)
        archive_path = archive_directory / "history-monolithic-v1.json"
        if not archive_path.exists():
            self.legacy_file.replace(archive_path)

