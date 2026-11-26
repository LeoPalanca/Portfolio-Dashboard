"""Normalize regular and consolidated Revolut CSV statements.

The consolidated statement ("Conti correnti Riepiloghi" …) lists every sub-account
of one customer: the personal account in each currency, the Pro account, a joint
account, every pocket or vault, the savings deposit and Investment Services. Each
sub-account opens with a title such as ``Vacanze (EUR)``; its transaction table
keeps a running balance ("Saldo"). Every row read from it carries the sub-account
it belongs to, its kind, its running balance and, when the row moves money between
two of the customer's own sub-accounts, which kind of own-account transfer it is.
"""

from __future__ import annotations

import csv
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from ..domain.money import parse_decimal

MONTHS = dict(zip(["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"], range(1, 13)))

# Kinds of sub-account. Only "joint" belongs to a profile other than the holder's own.
PERSONAL, POCKET, DEPOSIT, JOINT, PRO, INVESTMENT = "personal", "pocket", "deposit", "joint", "pro", "investment"
# Values of the "Trasferimento" field: money moving between two sub-accounts of the
# same side (the holder's own, or the joint account's), or across the two sides.
INTERNAL_TRANSFER = "interno"
JOINT_TRANSFER = "cointestato"

PART = re.compile(r"^(?P<group>Conti correnti|Conti deposito|Investment Services) (?:Riepiloghi|Estratti conto delle operazioni|Transaction Statements)$")
TITLE = re.compile(r"^(?P<name>.+?)\s*\((?P<currency>[A-Z]{3})\)$")
CURRENCY_SYMBOLS = {"€": "EUR", "$": "USD", "£": "GBP", "¥": "JPY"}
DEPOSIT_TRANSFER = re.compile(r"^(?:A|Da) (?P<currency>[A-Z]{3}) Conto deposito senza vincoli$")
POCKET_TRANSFER = re.compile(r"^Accredita [A-Z]{3} (?P<name>.+?) da [A-Z]{3}$")
TO_ACCOUNT = re.compile(r"^To (?P<currency>[A-Z]{3})(?: (?P<name>.+))?$")
COUNTERPARTY = re.compile(
    r"^(?:Pagamento (?:a favore di|da parte di|da)|Bonifico(?: SWIFT)? (?:a favore di|da)|To|From) (?P<who>.+)$",
    re.IGNORECASE,
)
DATE_TEXT = re.compile(r"\b\d{1,2} [a-z]{3} \d{4}\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b")
TRANSFER_CATEGORIES = {"", "Altri", "Ricarica", "Trasferimenti"}


def consolidated_date(value: str) -> date | None:
    try:
        if "/" in value:
            day, month, year = map(int, value.split("/"))
            return date(year if year >= 100 else 2000 + year, month, day)
        day_text, month_text, year_text = value.split()
        return date(int(year_text), MONTHS[month_text.lower()], int(day_text))
    except (ValueError, KeyError):
        return None


def amount(value: str) -> str:
    """Native amount of a consolidated-statement cell such as ``-1.234,56€`` or ``12,50 CHF``."""

    return str(parse_decimal(value)) if value.strip() else ""


@dataclass(frozen=True)
class SubAccount:
    """One sub-account of a consolidated statement."""

    name: str
    currency: str
    kind: str
    holders: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        return account_label(self.name, self.currency)

    @property
    def side(self) -> str:
        return JOINT if self.kind == JOINT else "own"


def account_label(name: str, currency: str) -> str:
    return f"Revolut · {name} ({currency})"


def cell_currency(text: str) -> str:
    for symbol, code in CURRENCY_SYMBOLS.items():
        if symbol in text:
            return code
    match = re.search(r"\b([A-Z]{3})\b", text)
    return match[1] if match else ""


def column_values(headers: list[str], cells: list[str], name: str, currency: str) -> tuple[str, str]:
    """``(native, eur)`` cells of column ``name``.

    Foreign-currency tables repeat each money column, once in the sub-account's
    currency and once as its EUR equivalent, in either order; each cell's currency
    sign tells them apart.
    """

    values = [cells[index] for index, header in enumerate(headers) if header == name and index < len(cells)]
    if not values:
        return "", ""
    native = next((value for value in values if cell_currency(value) == currency), None)
    if native is None:
        native = next((value for value in values if cell_currency(value) != "EUR"), values[0])
    eur = native if currency == "EUR" else next((value for value in values if cell_currency(value) == "EUR"), "")
    return native, eur


def _words(text: str) -> frozenset[str]:
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().casefold()
    return frozenset(re.findall(r"[a-z0-9]+", folded))


def _people(text: str) -> list[frozenset[str]]:
    return [words for words in (_words(part) for part in re.split(r"\s*(?:&|,|\be\b|\band\b)\s*", text, flags=re.IGNORECASE)) if words]


def _same_person(left: frozenset[str], right: frozenset[str]) -> bool:
    smaller, larger = sorted((left, right), key=len)
    return smaller == larger or (len(smaller) >= 2 and smaller <= larger)


def names_holders(text: str, holders: Iterable[str], everyone: bool) -> bool:
    """Whether ``text`` names the joint account's holders: all of them, or (``everyone=False``) only holders."""

    people = _people(text)
    remaining = [_words(holder) for holder in holders]
    if not people or not remaining:
        return False
    if not everyone:
        return all(any(_same_person(person, holder) for holder in remaining) for person in people)
    if len(people) != len(remaining):
        return False
    for person in people:
        match = next((holder for holder in remaining if _same_person(person, holder)), None)
        if match is None:
            return False
        remaining.remove(match)
    return True


def read_revolut_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.reader(handle))
    if not rows:
        return []
    if "Tipo" in rows[0]:
        return [
            dict(zip(rows[0], row)) for row in rows[1:] if any(row)
        ]
    return read_consolidated_rows(rows)


def read_consolidated_rows(rows: list[list[str]]) -> list[dict[str, str]]:
    return ConsolidatedStatement(rows).movements


def consolidated_period(rows: list[list[str]]) -> tuple[date, date] | None:
    """The period a consolidated statement states (a "Periodo …" row with two dates), if it does."""

    for row in rows:
        cells = [" ".join(cell.split()) for cell in row if cell.strip()]
        if not cells or not re.match(r"(?:statement\s+)?period", cells[0], re.IGNORECASE):
            continue
        days = [consolidated_date(text) for text in DATE_TEXT.findall(" ".join(cells))]
        found = sorted(day for day in days if day is not None)
        if len(found) == 2:
            return found[0], found[1]
    return None


class ConsolidatedStatement:
    """Rows of one consolidated statement, each tagged with its sub-account."""

    def __init__(self, rows: list[list[str]]) -> None:
        self.accounts: list[SubAccount] = []
        self.movements: list[dict[str, str]] = []
        self.period: tuple[date, date] | None = None
        start = next((index for index, row in enumerate(rows) if any(cell.strip() for cell in row)), 0)
        if not rows[start] or rows[start][0].strip() != "Conti correnti Riepiloghi":
            return
        self.period = consolidated_period(rows[start:])
        self._read(rows[start:])
        self._classify_transfers()
        self._mirror_deposit_transfers()

    def _read(self, rows: list[list[str]]) -> None:
        group = "Conti correnti"
        phase = "summary"
        summaries: dict[tuple[str, str, str, int], dict[str, list[str]]] = {}
        seen: dict[tuple[str, str, str, str], int] = {}
        tables: list[tuple[tuple[str, str, str, int], list[str], list[str], date]] = []
        interest_only: set[tuple[str, str, str, int]] = set()
        current: tuple[str, str, str, int] | None = None
        headers: list[str] = []
        for row in rows:
            cells = [cell.strip() for cell in row]
            filled = [cell for cell in cells if cell]
            if not filled:
                headers = []
                continue
            label = " ".join(cells[0].split())
            part = PART.fullmatch(label)
            if part and len(filled) == 1:
                group, phase, current, headers = part["group"], "statement" if "Riepiloghi" not in label else "summary", None, []
                continue
            title = TITLE.fullmatch(label)
            if title and len(filled) == 1:
                name, currency = " ".join(title["name"].split()), title["currency"]
                key = (phase, group, name, currency)
                seen[key] = seen.get(key, 0) + 1
                current, headers = (group, name, currency, seen[key]), []
                continue
            if current is None:
                continue
            if label == "Data" and "Descrizione" in cells:
                headers = cells
                if "Net interest" in cells:
                    interest_only.add(current)
                continue
            day = consolidated_date(label)
            if headers and day is not None:
                tables.append((current, headers, cells, day))
                continue
            info = summaries.setdefault(current, {})
            for index, cell in enumerate(cells[:-1]):
                if cell in {"Titolarità", "Scopo del conto", "Co-titolare"} and cells[index + 1]:
                    info.setdefault(cell, []).append(cells[index + 1])

        accounts: dict[tuple[str, str, str, int], SubAccount] = {}

        def account_for(key: tuple[str, str, str, int]) -> SubAccount:
            if key not in accounts:
                group_name, name, currency, occurrence = key
                info = summaries.get(key, {})
                kind = sub_account_kind(group_name, name, info, key in interest_only)
                display = name if occurrence == 1 else f"{name} #{occurrence}"
                accounts[key] = SubAccount(display, currency, kind, tuple(info.get("Co-titolare", [])))
                self.accounts.append(accounts[key])
            return accounts[key]

        for key in summaries:
            account_for(key)
        for key, table_headers, cells, day in tables:
            movement = movement_row(account_for(key), table_headers, cells, day)
            if movement is not None:
                self.movements.append(movement)
        # A joint account's pockets have no holder list of their own.
        holders = next((account.holders for account in self.accounts if account.kind == JOINT and account.holders), ())
        self.accounts = [
            SubAccount(account.name, account.currency, account.kind, holders) if account.kind == JOINT and not account.holders else account
            for account in self.accounts
        ]

    def _classify_transfers(self) -> None:
        """Mark own-account transfers: ``interno`` within one side, ``cointestato`` across sides.

        Both legs of a pocket, vault, Pro or currency transfer are listed, each in its
        own sub-account, under the same description; pairing them by day, description
        and opposite amount tells which sub-account the money came from or went to.
        """

        accounts = {account.label: account for account in self.accounts}
        currencies = {account.currency for account in self.accounts}
        sides_by_name: dict[str, set[str]] = {}
        for account in self.accounts:
            sides_by_name.setdefault(re.sub(r" #\d+$", "", account.name).casefold(), set()).add(account.side)
        sides_by_name.setdefault("personal", set()).add("own")
        sides_by_name.setdefault("pro", set()).add("own")
        joint_holders = [account.holders for account in self.accounts if account.kind == JOINT and account.holders]
        legs: dict[tuple[str, str, Decimal], list[int]] = {}
        for index, movement in enumerate(self.movements):
            key = (movement["Data di completamento"], " ".join(movement["Descrizione"].split()), Decimal(movement["Importo"]))
            legs.setdefault(key, []).append(index)

        def pair(index: int, movement: dict[str, str]) -> bool:
            """Mark this leg and its opposite one in another sub-account, if the statement lists it."""

            key = (movement["Data di completamento"], " ".join(movement["Descrizione"].split()), -Decimal(movement["Importo"]))
            for other in legs.get(key, []):
                partner = self.movements[other]
                if other != index and not partner["Trasferimento"] and partner["Conto"] != movement["Conto"]:
                    same_side = accounts[partner["Conto"]].side == accounts[movement["Conto"]].side
                    movement["Trasferimento"] = partner["Trasferimento"] = INTERNAL_TRANSFER if same_side else JOINT_TRANSFER
                    return True
            return False

        def named_side(name: str | None, default: str) -> str | None:
            if name is None:
                return default
            sides = sides_by_name.get(" ".join(name.split()).casefold())
            if not sides:
                return None
            return next(iter(sides)) if len(sides) == 1 else default

        for index, movement in enumerate(self.movements):
            if movement["Trasferimento"]:
                continue
            account = accounts[movement["Conto"]]
            description = " ".join(movement["Descrizione"].split())
            other_side: str | None = None
            if movement["Tipo"] == "cambia valuta" or description.startswith("Conversione in ") or DEPOSIT_TRANSFER.fullmatch(description):
                other_side = account.side
            elif (pocket := POCKET_TRANSFER.fullmatch(description)) is not None:
                if pair(index, movement):
                    continue
                on_pocket = account.kind in {POCKET, JOINT} and re.sub(r" #\d+$", "", account.name) == pocket["name"]
                other_side = account.side if on_pocket else named_side(pocket["name"], account.side)
            elif description == "Prelievo da Pocket":
                if pair(index, movement):
                    continue
                other_side = account.side
            elif (target := TO_ACCOUNT.fullmatch(description)) is not None and target["currency"] in currencies:
                if pair(index, movement):
                    continue
                other_side = named_side(target["name"], account.side)
            if other_side is None and movement["Categoria"] in TRANSFER_CATEGORIES:
                who = COUNTERPARTY.fullmatch(description)
                if who and account.kind == JOINT and names_holders(who["who"], account.holders, everyone=False):
                    other_side = "own"
                elif who and account.kind != JOINT and any(names_holders(who["who"], holders, everyone=True) for holders in joint_holders):
                    other_side = JOINT
            if other_side is not None:
                movement["Trasferimento"] = INTERNAL_TRANSFER if other_side == account.side else JOINT_TRANSFER
        self._pair_unnamed_joint_transfers(accounts)

    def _pair_unnamed_joint_transfers(self, accounts: dict[str, SubAccount]) -> None:
        """Without a holder list, a joint account's transfer is told by its opposite leg on the same day."""

        if not any(account.kind == JOINT and not account.holders for account in self.accounts):
            return
        open_legs = [
            index for index, movement in enumerate(self.movements)
            if not movement["Trasferimento"] and movement["Categoria"] in TRANSFER_CATEGORIES
        ]
        used: set[int] = set()
        for index in open_legs:
            if index in used:
                continue
            movement = self.movements[index]
            side = accounts[movement["Conto"]].side
            for other in open_legs:
                candidate = self.movements[other]
                if (
                    other in used or other == index
                    or accounts[candidate["Conto"]].side == side
                    or candidate["Data di completamento"] != movement["Data di completamento"]
                    or candidate["Valuta"] != movement["Valuta"]
                    or Decimal(candidate["Importo"]) != -Decimal(movement["Importo"])
                ):
                    continue
                used.update({index, other})
                movement["Trasferimento"] = candidate["Trasferimento"] = JOINT_TRANSFER
                break

    def _mirror_deposit_transfers(self) -> None:
        """The savings deposit lists its interest only: give it the transfers the current account lists."""

        listed = {movement["Conto"] for movement in self.movements if movement["Tipo conto"] == DEPOSIT and movement["Tipo"] != "interessi"}
        result: list[dict[str, str]] = []
        for movement in self.movements:
            result.append(movement)
            match = DEPOSIT_TRANSFER.fullmatch(" ".join(movement["Descrizione"].split()))
            if match is None or movement["Tipo conto"] == DEPOSIT:
                continue
            deposit = next(
                (account for account in self.accounts if account.kind == DEPOSIT and account.currency == match["currency"]),
                None,
            )
            if deposit is None:
                deposit = SubAccount("Deposito senza vincoli", match["currency"], DEPOSIT)
                self.accounts.append(deposit)
            if deposit.label in listed:
                continue
            native = Decimal(movement["Importo"])
            eur = Decimal(movement["Importo EUR"]) if movement["Importo EUR"] else None
            result.append({
                **movement, "Importo": str(-native), "Importo EUR": "" if eur is None else str(-eur),
                "Conto": deposit.label, "Sottoconto": deposit.name, "Tipo conto": DEPOSIT, "Saldo": "", "Saldo EUR": "",
                "Trasferimento": INTERNAL_TRANSFER,
            })
        self.movements = result


def sub_account_kind(group: str, name: str, info: dict[str, list[str]], interest_only: bool) -> str:
    folded = name.casefold()
    if group == "Conti deposito" or folded.startswith("deposito senza vincoli") or interest_only:
        return DEPOSIT
    if group == "Investment Services":
        return INVESTMENT
    if any(value.casefold().startswith("cointestat") for value in info.get("Titolarità", [])) or folded.startswith("conto cointestato"):
        return JOINT
    if folded == "conto personale":
        return PERSONAL
    if folded == "pro" or any(value.casefold() == "professional" for value in info.get("Scopo del conto", [])):
        return PRO
    return POCKET


def movement_row(account: SubAccount, headers: list[str], cells: list[str], event_date: date) -> dict[str, str] | None:
    interest = "Net interest" in headers
    native_text, eur_text = column_values(headers, cells, "Net interest" if interest else "Denaro in entrata/uscita", account.currency)
    native = amount(native_text)
    if not native:
        return None
    description = " ".join(cells[headers.index("Descrizione")].split()) if "Descrizione" in headers and headers.index("Descrizione") < len(cells) else ""
    category = cells[headers.index("Categoria")] if "Categoria" in headers and headers.index("Categoria") < len(cells) else ""
    kind = "interessi" if interest else {
        "Esercente": "pagamento con carta", "Cambio valuta": "cambia valuta",
        "Ricarica": "ricarica", "Altri": "pagamento",
    }.get(category, category.lower())
    if kind == "pagamento" and Decimal(native) > 0:
        kind = "accredito consolidato"
    if description.lower().startswith("commissione"):
        kind = "commissione"
    balance, balance_eur = column_values(headers, cells, "Saldo", account.currency)
    return {
        "Tipo": kind, "Data di completamento": event_date.strftime("%Y-%m-%d %H:%M:%S"),
        "Descrizione": description, "Importo": native, "Costo": "0", "Valuta": account.currency,
        "State": "COMPLETATO", "Categoria": category,
        "Conto": account.label, "Sottoconto": account.name, "Tipo conto": account.kind,
        "Saldo": amount(balance), "Saldo EUR": amount(balance_eur), "Importo EUR": amount(eur_text),
        "Trasferimento": "",
    }


def statement_period(path: Path) -> tuple[date, date] | None:
    """The period a consolidated statement states, if any."""

    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.reader(handle))
    return ConsolidatedStatement(rows).period if rows and "Tipo" not in rows[0] else None
