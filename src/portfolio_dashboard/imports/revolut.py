"""Normalize regular and consolidated Revolut CSV statements."""
from __future__ import annotations

import csv
import re
from datetime import date
from decimal import Decimal
from pathlib import Path

MONTHS = dict(zip(["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"], range(1, 13)))


def consolidated_date(value: str) -> date | None:
    try:
        if "/" in value:
            day, month, year = map(int, value.split("/"))
            return date(2000 + year, month, day)
        day, month, year = value.split()
        return date(int(year), MONTHS[month.lower()], int(day))
    except (ValueError, KeyError):
        return None


def amount(value: str) -> str:
    return re.sub(r"[^0-9,.+-]", "", value).replace(".", "").replace(",", ".")


def read_revolut_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.reader(handle))
    if not rows:
        return []
    if "Tipo" in rows[0]:
        return [
            dict(zip(rows[0], row)) for row in rows[1:] if any(row)
        ]
    if rows[0][0].strip() != "Conti correnti Riepiloghi":
        return []
    currency = ""
    headers: list[str] = []
    result: list[dict[str, str]] = []
    for row in rows[1:]:
        if not row or not any(row):
            headers = []
            continue
        label = row[0].strip()
        account = re.fullmatch(r"(?:Conto personale|Deposito senza vincoli)\s*\(([A-Z]{3})\)", label)
        if account:
            currency = account[1]
            headers = []
            continue
        if label == "Data" and "Descrizione" in row:
            headers = row
            continue
        event_date = consolidated_date(label)
        if not headers or not currency or event_date is None:
            continue
        # Duplicate columns in foreign-currency tables contain EUR equivalents.
        # Keep the first (native currency) column for each name.
        values = {key: row[index] for index, key in reversed(list(enumerate(headers))) if key and index < len(row)}
        interest = "Net interest" in headers
        native = amount(values.get("Net interest" if interest else "Denaro in entrata/uscita", ""))
        if not native:
            continue
        description = values.get("Descrizione", "")
        category = values.get("Categoria", "")
        kind = "interessi" if interest else {
            "Esercente": "pagamento con carta", "Cambio valuta": "cambia valuta",
            "Ricarica": "ricarica", "Altri": "pagamento",
        }.get(category, category.lower())
        if kind == "pagamento" and Decimal(native) > 0:
            kind = "accredito consolidato"
        if description.lower().startswith("commissione"):
            kind = "commissione"
        result.append({
            "Tipo": kind, "Data di completamento": event_date.strftime("%Y-%m-%d %H:%M:%S"),
            "Descrizione": description, "Importo": native, "Costo": "0", "Valuta": currency,
            "State": "COMPLETATO",
        })
        # Savings tables list interest only. Mirror the explicitly listed current-
        # account transfers so moving money into savings preserves total cash.
        if re.match(r"^(A|Da) [A-Z]{3} Conto deposito senza vincoli$", description):
            result.append({**result[-1], "Importo": str(-Decimal(native))})
    return result
