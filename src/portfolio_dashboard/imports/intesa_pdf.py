"""Read Intesa Sanpaolo quarterly current-account statements from their PDF text.

``pdftotext -layout`` keeps the statement's columns. The movement table opens with
"Saldo iniziale al dd.mm.yyyy" and closes with "Saldo finale al dd.mm.yyyy"; each
movement starts with its operation and value dates, its description may wrap onto
the following lines (and onto the next page, under a repeated header), and its
amount sits under either the "Addebiti" (debits) or the "Accrediti" (credits)
heading. Amounts use a decimal comma and space-separated thousands ("1 234, 56").
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

# pdftotext writes the thousands gap as a space, or as the control character U+0019
# followed by a space ("1\x19 234, 56").
THOUSANDS = " .\x19\xa0\u202f"
AMOUNT_PATTERN = r"[+-]?\d{1,3}(?:\x19?[ .\xa0\u202f]\d{3}|\x19\d{3})*, ?\d{2}"
# An amount column is separated from the text before it by at least two spaces.
TRAILING_AMOUNT = re.compile(rf"(?:(?<=\s\s)|^\s*)(?P<amount>{AMOUNT_PATTERN})\s*€?\s*$")
ANY_AMOUNT = re.compile(rf"(?<!\S)(?P<amount>{AMOUNT_PATTERN})(?=\s|€|$)")
ROW = re.compile(r"^\s*(?P<operation>\d{2}\.\d{2}\.\d{4})\s+(?P<value>\d{2}\.\d{2}\.\d{4})(?:\s+(?P<rest>\S.*))?$")
HEADER = re.compile(r"Data\s+Operazione\s+Data\s+Valuta\s+(?P<description>Descrizione)\s+(?P<debit>Addebiti)\s+(?P<credit>Accred\w*)")
OPENING = re.compile(r"Saldo iniziale al (\d{2}\.\d{2}\.\d{4})", re.IGNORECASE)
CLOSING = re.compile(r"Saldo finale al (\d{2}\.\d{2}\.\d{4})", re.IGNORECASE)
# Page furniture repeated around a table that continues on the next page.
PAGE_NOISE = re.compile(
    r"Pagina\s+\d+\s+di\s+\d+|^\s*ESTRATTO CONTO N\.|^\s*AL \d{2}\.\d{2}\.\d{4}\s*$|^\s*C/C N\.|^\s*Ci segua anche su",
    re.IGNORECASE,
)
BRAND_MARKERS = ("intesa sanpaolo", "intesasanpaolo")
STATEMENT_MARKERS = (
    "estratto conto n.",
    "saldo iniziale al",
    "dettaglio movimenti del conto corrente",
    "xme conto",
    "allegato all'estratto conto",
)
UNREADABLE = (
    "This Intesa Sanpaolo statement has no readable movement amounts: the PDF draws them "
    "with fonts that carry no text. Import the XLSX movement list for this period instead."
)


class IntesaStatementError(ValueError):
    """The PDF is an Intesa statement, but its movements cannot be read reliably."""


@dataclass
class IntesaStatementRow:
    operation_date: date
    value_date: date
    lines: list[str] = field(default_factory=list)
    amount: Decimal | None = None

    @property
    def description(self) -> str:
        return " ".join(" ".join(line.split()) for line in self.lines if line.strip())


@dataclass(frozen=True)
class IntesaStatement:
    opening_date: date
    opening_balance: Decimal
    closing_date: date
    closing_balance: Decimal
    rows: tuple[IntesaStatementRow, ...]

    @property
    def opening_checkpoint_date(self) -> date:
        """The day whose closing balance equals the statement's opening balance.

        A statement normally opens at the previous period's end. The first statement
        of a new account opens on the day of its first movement instead, before that
        movement, so its balance is the one at the end of the day before.
        """

        earliest = min((row.operation_date for row in self.rows), default=self.opening_date)
        return min(self.opening_date, earliest - timedelta(days=1))


def pdf_layout_text(path: Path) -> str:
    result = subprocess.run(["pdftotext", "-layout", str(path), "-"], check=True, capture_output=True, text=True)
    return result.stdout


def is_intesa_statement_text(text: str) -> bool:
    folded = text.casefold()
    if "interactive brokers" in folded:
        return False
    return any(marker in folded for marker in BRAND_MARKERS) and any(marker in folded for marker in STATEMENT_MARKERS)


def looks_like_intesa_statement(path: Path) -> bool:
    try:
        return is_intesa_statement_text(pdf_layout_text(path))
    except (OSError, subprocess.SubprocessError, UnicodeDecodeError):
        return False


def statement_decimal(raw: str) -> Decimal:
    text = re.sub(f"[€\\s{THOUSANDS}]", "", raw)
    sign = -1 if text.startswith("-") else 1
    digits = text.lstrip("+-").replace(",", ".")
    return Decimal(digits) * sign


def _statement_date(raw: str) -> date:
    day, month, year = (int(part) for part in raw.split("."))
    return date(year, month, day)


def _balance(line: str) -> Decimal | None:
    match = TRAILING_AMOUNT.search(line.rstrip())
    if match is None:
        return None
    value = statement_decimal(match.group("amount"))
    if "debito" in line.casefold() and not match.group("amount").lstrip().startswith(("+", "-")):
        value = -value
    return value


@dataclass(frozen=True)
class _Columns:
    description: int
    debit_end: int
    credit_end: int

    def signed(self, amount: Decimal, end: int) -> Decimal:
        debit = abs(end - self.debit_end) <= abs(end - self.credit_end)
        return -abs(amount) if debit else abs(amount)


def parse_intesa_statement_text(text: str) -> IntesaStatement:
    """Movements and opening/closing balances of one statement; raises if they do not add up."""

    opening: tuple[date, Decimal] | None = None
    summary_closing: tuple[date, Decimal] | None = None
    closing: tuple[date, Decimal] | None = None
    totals: list[Decimal] = []
    rows: list[IntesaStatementRow] = []
    columns: _Columns | None = None
    current: IntesaStatementRow | None = None
    in_table = False
    for raw in text.replace("\f", "\n").splitlines():
        line = raw.rstrip()
        if not line.strip() or PAGE_NOISE.search(line):
            continue
        header = HEADER.search(line)
        if header:
            columns = _Columns(header.start("description"), header.end("debit"), header.end("credit"))
            in_table = True
            continue
        opening_match = OPENING.search(line)
        if opening_match:
            if not rows:
                balance = _balance(line)
                if balance is None:
                    raise IntesaStatementError(UNREADABLE)
                opening = (_statement_date(opening_match.group(1)), balance)
            continue
        closing_match = CLOSING.search(line)
        if closing_match:
            balance = _balance(line)
            if balance is None:
                raise IntesaStatementError(UNREADABLE)
            if in_table:
                closing = (_statement_date(closing_match.group(1)), balance)
                break
            summary_closing = summary_closing or (_statement_date(closing_match.group(1)), balance)
            continue
        if not in_table or columns is None:
            continue
        row = ROW.match(line)
        if row:
            current = IntesaStatementRow(_statement_date(row.group("operation")), _statement_date(row.group("value")))
            rows.append(current)
            _take_text(current, line, row.start("rest") if row.group("rest") else len(line), columns)
            continue
        if line.strip().startswith("Totali"):
            totals = [statement_decimal(match.group("amount")) for match in ANY_AMOUNT.finditer(line)]
            current = None
            continue
        indent = len(line) - len(line.lstrip())
        if current is not None and indent >= columns.description - 2:
            _take_text(current, line, indent, columns)

    closing = closing or summary_closing
    if opening is None or closing is None:
        raise IntesaStatementError(UNREADABLE)
    if any(row.amount is None for row in rows):
        raise IntesaStatementError(UNREADABLE)
    amounts = [row.amount for row in rows if row.amount is not None]
    if len(totals) == 2 and (
        sum((-value for value in amounts if value < 0), Decimal(0)) != totals[0]
        or sum((value for value in amounts if value > 0), Decimal(0)) != totals[1]
    ):
        raise IntesaStatementError("The Intesa statement's movements do not add up to its debit and credit totals")
    if abs(opening[1] + sum(amounts, Decimal(0)) - closing[1]) > Decimal("0.005"):
        raise IntesaStatementError("The Intesa statement's opening balance plus its movements does not equal its closing balance")
    return IntesaStatement(opening[0], opening[1], closing[0], closing[1], tuple(rows))


def _take_text(row: IntesaStatementRow, line: str, start: int, columns: _Columns) -> None:
    text = line[start:]
    match = TRAILING_AMOUNT.search(line)
    if match and match.start() >= start:
        if row.amount is None:
            row.amount = columns.signed(statement_decimal(match.group("amount")), match.end("amount"))
        text = line[start : match.start()]
    if text.strip():
        row.lines.append(text.strip())


# Securities and fund operations: subscriptions, purchases, sales and redemptions.
# They move money into or out of an investment, never a refund ("rimborso titoli").
INVESTMENT_OPERATION = re.compile(
    r"rimborso\s+(?:di\s+)?(?:titol|quot|fond)|\bredemption\b|disinvestiment"
    r"|sottoscrizion\w*\s+(?:di\s+)?(?:titol|quot|fond|azion|obbligaz)"
    r"|(?:compravendita|vendita|acquisto)\s+(?:di\s+)?(?:titol|quot|fond)",
    re.IGNORECASE,
)
INVESTMENT_CATEGORY = "Investimenti titoli e fondi"
BENEFICIARY = re.compile(r"\b(?i:BENEF(?:ICIARIO)?)\b\.?\s*:?\s*(?P<name>.*?)\s*(?=\b[A-Z][A-Z/]{1,}\.?\s*:|$)")


def detail_beneficiary(text: str) -> str:
    """The name after a "BENEF.:" label in a movement's details ("" when there is none)."""

    match = BENEFICIARY.search(" ".join(str(text or "").split()))
    name = match.group("name").strip(" -.:;") if match else ""
    return "" if NOT_A_NAME.match(name or "-") else name


def statement_row_beneficiary(row: IntesaStatementRow) -> str:
    """The beneficiary a statement row's details name on their "BENEF.:" line."""

    for line in row.lines[1:]:
        if re.match(r"\s*BENEF", line, re.IGNORECASE):
            return detail_beneficiary(line)
    return ""


SOURCE_CATEGORIES = (
    (r"giroconto", None),
    (r"bonifico.*(?:a vostro favore|ricevut)", "Bonifici ricevuti"),
    (r"bonifico.*(?:da voi disposto|a favore di)|disposizione di bonifico", "Bonifici in uscita"),
    (r"stipendi|emolument|pension", "Stipendi e pensioni"),
    (r"storno|rimbors", "Rimborsi spese e storni"),
    (r"preliev", "Prelievi"),
    (r"versam", "Versamenti"),
    (r"commission|canone|impost|bollo|spese|interessi debitori", "Imposte, bolli e commissioni"),
)
NOT_A_NAME = re.compile(r"^(?:-|\d{6,}.*|NOTPROVIDED.*|BS\d.*|COD\. ?DISP.*|BIC\b.*|BENEF\b.*|EFFETTUATO\b.*|MEDIANTE\b.*)$", re.IGNORECASE)


def statement_row_fields(row: IntesaStatementRow) -> tuple[str, str, str]:
    """``(source_category, merchant, description)`` shaped like the XLSX export's columns.

    The PDF has no Intesa category column, so the operation line stands in for it,
    mapped onto the XLSX category names the shared flow rules already understand.
    The merchant is the counterparty: the sender of a received transfer, the
    beneficiary of a sent one, the shop of a card payment.
    """

    kind = row.lines[0] if row.lines else ""
    folded = kind.casefold()
    amount = row.amount or Decimal(0)
    category = kind
    if "giroconto" not in folded and INVESTMENT_OPERATION.search(" ".join(row.lines)):
        category = INVESTMENT_CATEGORY
    else:
        for pattern, mapped in SOURCE_CATEGORIES:
            if re.search(pattern, folded):
                category = mapped or ("Giroconto in entrata" if amount > 0 else "Giroconto in uscita")
                break
        else:
            if amount > 0 and "pagamento" in folded:
                category = "Rimborsi spese e storni"
    details = row.lines[1:]
    merchant = ""
    for line in details:
        labelled = re.match(r"(?:MITT|PRESSO|ORDINANTE|A FAVORE DI)\.?:?\s+(.+)", line, re.IGNORECASE)
        if labelled:
            merchant = labelled.group(1).strip(" -")
            break
    if not merchant and category == "Bonifici in uscita":
        merchant = next((line for line in details if not NOT_A_NAME.match(line.strip())), "")
    if not merchant:
        merchant = {"Bonifici ricevuti": "Bonifico ricevuto", "Bonifici in uscita": "Bonifico disposto"}.get(category, kind)
    return category, " ".join(merchant.split()) or "Intesa", row.description or kind
