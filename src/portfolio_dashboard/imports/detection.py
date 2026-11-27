"""Detect supported statement formats without relying on their original filenames."""

from __future__ import annotations

import csv
import re
from datetime import UTC, datetime
from pathlib import Path

from openpyxl import load_workbook  # type: ignore[import-untyped]

from . import ibkr_csv, intesa_pdf
from .fineco import has_fineco_bank_headers

ALLOWED_EXTENSIONS = {".csv", ".xls", ".xlsx", ".pdf"}
SOURCE_LABELS = {
    "trade_republic": "Trade Republic",
    "fineco": "Fineco",
    "interactive_brokers": "Interactive Brokers",
    "etoro": "eToro",
    "revolut": "Revolut",
    "intesa": "Intesa Sanpaolo",
    "bbva": "BBVA",
    "manual": "Personal trades",
}
SOURCE_EXTENSIONS = {
    "trade_republic": (".csv",),
    "fineco": (".xlsx",),
    "interactive_brokers": (".pdf", ".csv"),
    "etoro": (".xlsx",),
    "revolut": (".csv",),
    "intesa": (".xlsx", ".pdf"),
    "bbva": (".xls",),
    "manual": (".csv", ".xlsx"),
}

PERSONAL_TRADE_REQUIRED_HEADERS = {"date", "action", "asset", "quantity", "price"}


def source_format_label(source: str) -> str:
    return "/".join(extension.removeprefix(".").upper() for extension in SOURCE_EXTENSIONS[source])


REVOLUT_CONSOLIDATED_SECTIONS = {"conti correnti riepiloghi", "riepilogo delle transazioni"}
REVOLUT_CONSOLIDATED_HEADERS = {"data", "descrizione", "categoria", "denaro in entrata/uscita", "saldo"}


def _normalized_rows(path: Path, limit: int = 40) -> list[set[str]]:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            with path.open(newline="", encoding=encoding) as handle:
                reader = csv.reader(handle)
                rows = [next(reader, None) for _ in range(limit)]
            return [
                {" ".join(str(value).split()).casefold() for value in row if str(value).strip()}
                for row in rows
                if row and any(str(value).strip() for value in row)
            ]
        except (OSError, UnicodeDecodeError, csv.Error):
            continue
    return []


def _normalized_headers(path: Path) -> set[str]:
    rows = _normalized_rows(path, 1)
    return rows[0] if rows else set()


def _is_revolut_consolidated(path: Path) -> bool:
    """The consolidated statement opens with section titles before any table header."""

    return any(row & REVOLUT_CONSOLIDATED_SECTIONS or REVOLUT_CONSOLIDATED_HEADERS <= row for row in _normalized_rows(path))


def detect_statement_source(path: Path, requested_source: str | None = "auto") -> str:
    """Return the configured source id or raise a user-facing validation error."""

    requested = (requested_source or "auto").strip().casefold().replace("-", "_").replace(" ", "_")
    suffix = path.suffix.casefold()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValueError("Supported statement formats are CSV, XLS, XLSX, and PDF")
    if requested and requested != "auto":
        if requested not in SOURCE_LABELS:
            raise ValueError(f"Unsupported source: {requested_source}")
        if suffix not in SOURCE_EXTENSIONS[requested]:
            required = source_format_label(requested)
            raise ValueError(f"{SOURCE_LABELS[requested]} imports require {required}; this file is {suffix[1:].upper()}")
        return requested

    if suffix == ".pdf":
        # Without pdftotext the text cannot be read; IBKR stays the PDF default.
        return "intesa" if intesa_pdf.looks_like_intesa_statement(path) else "interactive_brokers"
    if suffix == ".xls":
        return "bbva"
    if suffix == ".csv":
        if ibkr_csv.looks_like_activity_statement(path):
            return "interactive_brokers"
        headers = _normalized_headers(path)
        if {"type", "category", "shares", "amount"}.issubset(headers):
            return "trade_republic"
        if {"tipo", "data di completamento", "descrizione", "importo", "state"}.issubset(headers) or _is_revolut_consolidated(path):
            return "revolut"
        if PERSONAL_TRADE_REQUIRED_HEADERS.issubset(headers) or len(headers) >= 17:
            return "manual"
        raise ValueError("The CSV headers do not match a supported Trade Republic, Revolut, Interactive Brokers, or manual export")

    try:
        workbook = load_workbook(path, read_only=True, data_only=True)
    except Exception as exc:
        raise ValueError("The workbook could not be opened") from exc
    try:
        sheets = {name.casefold() for name in workbook.sheetnames}
        if "movimenti dossier titoli" in sheets:
            return "fineco"
        if "attività account" in sheets and "dividendi" in sheets:
            return "etoro"
        if "lista operazione" in sheets:
            return "intesa"
        for sheet in workbook.worksheets[:3]:
            for row in sheet.iter_rows(max_row=30, values_only=True):
                if has_fineco_bank_headers(row):
                    return "fineco"
                values = {str(value).strip().casefold() for value in row if value is not None}
                if PERSONAL_TRADE_REQUIRED_HEADERS.issubset(values):
                    return "manual"
                if {"data", "operazione", "importo"}.issubset(values):
                    return "intesa"
    finally:
        workbook.close()
    raise ValueError("The workbook sheets do not match a supported Fineco, eToro, Intesa, or Personal trades export")


def import_destination(source_dir: Path, source: str, digest: str, original_name: str) -> Path:
    """Choose a stable raw archive path that also matches legacy discovery patterns."""

    suffix = Path(original_name).suffix.casefold()
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    token = re.sub(r"[^a-z0-9]+", "-", source.casefold()).strip("-")
    if source == "revolut":
        filename = f"account-statement-{stamp}-{digest[:10]}{suffix}"
        return source_dir / "cash_exports" / source / filename
    if source == "intesa":
        stem = "intesa-statement" if suffix == ".pdf" else "account_operations"
        filename = f"{stem}-{stamp}-{digest[:10]}{suffix}"
        return source_dir / "cash_exports" / source / filename
    if source == "bbva":
        filename = f"bbva-{stamp}-{digest[:10]}{suffix}"
        return source_dir / "cash_exports" / source / filename
    if source == "manual":
        filename = f"personal-trades-{stamp}-{digest[:10]}{suffix}"
        return source_dir / "broker_exports" / source / filename
    filename = f"{token}-{stamp}-{digest[:10]}{suffix}"
    return source_dir / "broker_exports" / source / filename
