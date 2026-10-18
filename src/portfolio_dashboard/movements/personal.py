"""User annotations and manual cash entries, separate from immutable bank imports."""

import sqlite3
import uuid
from collections.abc import Collection
from contextlib import closing
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path


def match_key(value: str) -> str:
    return " ".join(value.casefold().split())


class PersonalLedger:
    def __init__(self, path: Path):
        self.path = path

    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS expense_overrides (
                portfolio_id TEXT NOT NULL, movement_id INTEGER NOT NULL,
                category TEXT NOT NULL, subcategory TEXT NOT NULL,
                PRIMARY KEY (portfolio_id, movement_id)
            );
            CREATE TABLE IF NOT EXISTS personal_category_rules (
                portfolio_id TEXT NOT NULL, source TEXT NOT NULL, merchant TEXT NOT NULL,
                flow_kind TEXT NOT NULL, category TEXT NOT NULL, subcategory TEXT NOT NULL,
                after_id INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (portfolio_id, source, merchant, flow_kind)
            );
            CREATE TABLE IF NOT EXISTS manual_cash_entries (
                id TEXT PRIMARY KEY, portfolio_id TEXT NOT NULL, occurred_on TEXT NOT NULL,
                flow_kind TEXT NOT NULL, amount TEXT NOT NULL, merchant TEXT NOT NULL,
                description TEXT NOT NULL, category TEXT NOT NULL, subcategory TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS manual_cash_settings (
                portfolio_id TEXT PRIMARY KEY, opening_balance TEXT NOT NULL
            );
        """)
        columns = {row[1] for row in connection.execute("PRAGMA table_info(expense_overrides)")}
        if "flow_kind" not in columns:
            connection.execute("ALTER TABLE expense_overrides ADD COLUMN flow_kind TEXT NOT NULL DEFAULT ''")
            connection.commit()
        return connection

    def classify(self, owner: str, events: list[dict]) -> list[dict]:
        with closing(self.connect()) as connection:
            overrides = {
                row["movement_id"]: dict(row)
                for row in connection.execute("SELECT * FROM expense_overrides WHERE portfolio_id = ?", (owner,))
            }
            rules = {
                (row["source"], row["merchant"], row["flow_kind"]): dict(row)
                for row in connection.execute("SELECT * FROM personal_category_rules WHERE portfolio_id = ?", (owner,))
            }
        for event in events:
            rule = rules.get((match_key(event["source"]), match_key(event["merchant"]), event["flow_kind"]))
            selected = overrides.get(event["movement_id"])
            if selected is None and rule and event["movement_id"] > rule["after_id"]:
                selected = rule
            if selected:
                event.update(category=selected["category"], subcategory=selected["subcategory"])
                if selected.get("flow_kind"):
                    event["flow_kind"] = selected["flow_kind"]
        return events

    def set_category(
        self, owner: str, event: dict, category: str, subcategory: str, learn: bool = False, include_past: bool = True
    ) -> None:
        with closing(self.connect()) as connection, connection:
            connection.execute(
                "INSERT INTO expense_overrides(portfolio_id,movement_id,category,subcategory) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(portfolio_id,movement_id) DO UPDATE SET category=excluded.category,subcategory=excluded.subcategory",
                (owner, event["movement_id"], category, subcategory),
            )
            if learn:
                merchant = match_key(event["merchant"])
                if not merchant or merchant == "unknown":
                    raise ValueError("A known merchant is required to create a matching rule")
                after_id = (
                    0
                    if include_past
                    else connection.execute(
                        "SELECT COALESCE(MAX(id), 0) FROM movements WHERE portfolio_id = ?", (owner,)
                    ).fetchone()[0]
                )
                connection.execute(
                    "INSERT OR REPLACE INTO personal_category_rules VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (owner, match_key(event["source"]), merchant, event["flow_kind"], category, subcategory, after_id),
                )

    def rules(self, owner: str) -> list[dict]:
        with closing(self.connect()) as connection:
            return [
                dict(row)
                for row in connection.execute(
                    "SELECT source, merchant, flow_kind, category, subcategory, after_id "
                    "FROM personal_category_rules WHERE portfolio_id = ? ORDER BY source, merchant",
                    (owner,),
                )
            ]

    def set_direction(self, owner: str, movement_id: int, flow_kind: str) -> None:
        if flow_kind not in {"income", "spend", "credit", "personal_transfer", "investment", "cash_withdrawal", "fee"}:
            raise ValueError("Choose a supported transaction type")
        with closing(self.connect()) as connection, connection:
            connection.execute(
                "UPDATE expense_overrides SET flow_kind=? WHERE portfolio_id=? AND movement_id=?",
                (flow_kind, owner, movement_id),
            )

    def delete_rule(self, owner: str, source: str, merchant: str, flow_kind: str) -> None:
        with closing(self.connect()) as connection, connection:
            connection.execute(
                "DELETE FROM personal_category_rules WHERE portfolio_id = ? AND source = ? AND merchant = ? AND flow_kind = ?",
                (owner, source, merchant, flow_kind),
            )

    def save_cash(self, owner: str, payload: dict, categories: Collection[str]) -> str:
        try:
            occurred_on = date.fromisoformat(str(payload.get("date", "")))
            amount = Decimal(str(payload.get("amount", "")))
        except (ValueError, InvalidOperation):
            raise ValueError("Enter a valid date and EUR amount") from None
        if (
            not amount.is_finite()
            or amount <= 0
            or amount > Decimal(1000000000)
            or amount != amount.quantize(Decimal("0.01"))
        ):
            raise ValueError("Amount must be positive, with at most two decimal places")
        if occurred_on > date.today():  # noqa: DTZ011 - bank/cash dates use the server's local calendar
            raise ValueError("Future cash entries are not supported")
        kind = str(payload.get("flow_kind", "spend"))
        if kind not in {"income", "spend", "transfer_in", "transfer_out"}:
            raise ValueError("Choose income, expense or cash transfer")
        category = str(payload.get("category", "Uncategorized"))
        if category not in categories:
            raise ValueError("Choose a valid category")
        merchant = str(payload.get("merchant", "")).strip()
        description = str(payload.get("description", "")).strip()
        subcategory = str(payload.get("subcategory", "")).strip()
        if not merchant or any(len(value) > 500 for value in (merchant, description, subcategory)):
            raise ValueError("Enter a merchant/payee; text fields must be at most 500 characters")
        identifier = str(payload.get("id") or uuid.uuid4())
        with closing(self.connect()) as connection, connection:
            if payload.get("id"):
                changed = connection.execute(
                    "UPDATE manual_cash_entries SET occurred_on=?, flow_kind=?, amount=?, merchant=?, description=?, category=?, subcategory=? "
                    "WHERE id=? AND portfolio_id=?",
                    (
                        occurred_on.isoformat(),
                        kind,
                        str(amount),
                        merchant,
                        description,
                        category,
                        subcategory,
                        identifier,
                        owner,
                    ),
                ).rowcount
                if not changed:
                    raise ValueError("Cash entry not found")
            else:
                connection.execute(
                    "INSERT INTO manual_cash_entries VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        identifier,
                        owner,
                        occurred_on.isoformat(),
                        kind,
                        str(amount),
                        merchant,
                        description,
                        category,
                        subcategory,
                    ),
                )
        return identifier

    def delete_cash(self, owner: str, identifier: str) -> None:
        with closing(self.connect()) as connection, connection:
            if not connection.execute(
                "DELETE FROM manual_cash_entries WHERE portfolio_id=? AND id=?", (owner, identifier)
            ).rowcount:
                raise ValueError("Cash entry not found")

    def cash_events(self, owner: str) -> list[dict]:
        with closing(self.connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM manual_cash_entries WHERE portfolio_id=? ORDER BY occurred_on, id", (owner,)
            ).fetchall()
        return [
            {
                "date": date.fromisoformat(row["occurred_on"]),
                "source": "cash",
                "cash_id": row["id"],
                "merchant": row["merchant"],
                "description": row["description"],
                "flow_kind": "personal_transfer" if row["flow_kind"].startswith("transfer_") else row["flow_kind"],
                "cash_direction": row["flow_kind"],
                "category": row["category"],
                "subcategory": row["subcategory"],
                "amount_eur": Decimal(row["amount"]),
                "native_amount": Decimal(row["amount"]) * (1 if row["flow_kind"] in {"income", "transfer_in"} else -1),
                "currency": "EUR",
            }
            for row in rows
        ]

    def set_opening_balance(self, owner: str, value) -> None:
        try:
            amount = Decimal(str(value))
        except InvalidOperation:
            raise ValueError("Enter a valid opening balance") from None
        if (
            not amount.is_finite()
            or abs(amount) > Decimal(1000000000)
            or amount < 0
            or amount != amount.quantize(Decimal("0.01"))
        ):
            raise ValueError("Opening balance must be non-negative EUR with at most two decimals")
        with closing(self.connect()) as connection, connection:
            connection.execute("INSERT OR REPLACE INTO manual_cash_settings VALUES (?, ?)", (owner, str(amount)))

    def cash_balance(self, owner: str) -> dict:
        with closing(self.connect()) as connection:
            row = connection.execute(
                "SELECT opening_balance FROM manual_cash_settings WHERE portfolio_id=?", (owner,)
            ).fetchone()
        opening = Decimal(row[0]) if row else None
        change = sum((event["native_amount"] for event in self.cash_events(owner)), Decimal(0))
        return {
            "opening_balance": float(opening) if opening is not None else None,
            "balance": float(opening + change) if opening is not None else None,
            "change": float(change),
        }
