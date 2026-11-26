"""User annotations and manual cash entries, separate from immutable bank imports."""

import hashlib
import json
import re
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
    # Transaction types a user correction may set; "refund" is money back that lowers spending.
    SUPPORTED_KINDS = frozenset(
        {"income", "spend", "credit", "refund", "personal_transfer", "investment", "cash_withdrawal", "fee", "top_up"}
    )

    def __init__(self, path: Path):
        self.path = path

    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS personal_categories (
                portfolio_id TEXT NOT NULL, name TEXT NOT NULL,
                PRIMARY KEY (portfolio_id, name)
            );
            CREATE TABLE IF NOT EXISTS personal_income_policy (
                portfolio_id TEXT PRIMARY KEY, credit_payers TEXT NOT NULL
            );
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
            CREATE TABLE IF NOT EXISTS account_balances (
                id TEXT PRIMARY KEY, portfolio_id TEXT NOT NULL, account TEXT NOT NULL,
                occurred_on TEXT NOT NULL, balance TEXT NOT NULL,
                UNIQUE (portfolio_id, account, occurred_on)
            );
        """)
        columns = {row[1] for row in connection.execute("PRAGMA table_info(expense_overrides)")}
        if "flow_kind" not in columns:
            connection.execute("ALTER TABLE expense_overrides ADD COLUMN flow_kind TEXT NOT NULL DEFAULT ''")
            connection.commit()
        return connection

    def categories(self, owner: str, defaults: Collection[str]) -> list[str]:
        with closing(self.connect()) as connection:
            names = [row[0] for row in connection.execute(
                "SELECT name FROM personal_categories WHERE portfolio_id=?", (owner,))]
        return sorted(set(defaults) | set(names), key=str.casefold)

    def add_category(self, owner: str, name: str) -> None:
        name = " ".join(name.split())
        if not name or len(name) > 80:
            raise ValueError("Enter a category name between 1 and 80 characters")
        with closing(self.connect()) as connection, connection:
            connection.execute("INSERT OR IGNORE INTO personal_categories VALUES (?, ?)", (owner, name))

    def set_credit_payers(self, owner: str, names: list[str]) -> None:
        with closing(self.connect()) as connection, connection:
            connection.execute("INSERT OR REPLACE INTO personal_income_policy VALUES (?, ?)",
                               (owner, json.dumps(names)))

    def classify(self, owner: str, events: list[dict]) -> list[dict]:
        with closing(self.connect()) as connection:
            policy = connection.execute("SELECT credit_payers FROM personal_income_policy WHERE portfolio_id=?", (owner,)).fetchone()
            credit_payers = json.loads(policy[0]) if policy else None
            overrides = {
                row["movement_id"]: dict(row)
                for row in connection.execute("SELECT * FROM expense_overrides WHERE portfolio_id = ?", (owner,))
            }
            rules = {
                (row["source"], row["merchant"], row["flow_kind"]): dict(row)
                for row in connection.execute("SELECT * FROM personal_category_rules WHERE portfolio_id = ?", (owner,))
            }
        for event in events:
            if credit_payers is not None and event["flow_kind"] in {"income", "credit"}:
                text = match_key(f"{event.get('merchant', '')} {event.get('description', '')}")
                transfer = bool(re.search(r"\b(?:bonific\w*|transfer\w*)\b", text))
                matched = transfer and any(re.search(r"(?<!\w)" + re.escape(match_key(name)) + r"(?!\w)", text)
                                           for name in credit_payers)
                event["flow_kind"] = "credit" if matched else "income"
                if event.get("category") in {"Income", "Credits", "Uncategorized"}:
                    event["category"] = "Credits" if matched else "Income"
            rule = rules.get((match_key(event["source"]), match_key(event["merchant"]), event["flow_kind"]))
            selected = overrides.get(event["movement_id"])
            if selected is None and rule and event["movement_id"] > rule["after_id"]:
                selected = rule
            if selected:
                event.update(category=selected["category"], subcategory=selected["subcategory"])
                if selected.get("flow_kind"):
                    event["flow_kind"] = selected["flow_kind"]
                    # Only a correction of this row sets a type; a rule keeps the one it matched.
                    event["flow_kind_chosen"] = selected is not rule
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
        if flow_kind not in self.SUPPORTED_KINDS:
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

    @staticmethod
    def _cash_values(payload: dict, categories: Collection[str]) -> tuple[str, str, str, str, str, str, str]:
        """``(occurred_on, flow_kind, amount, merchant, description, category, subcategory)`` of a valid entry."""

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
        return occurred_on.isoformat(), kind, str(amount), merchant, description, category, subcategory

    def import_cash_entries(self, owner: str, payloads: list[dict], categories: Collection[str]) -> dict[str, int]:
        """Add cash entries in bulk, each with an id derived from its content.

        The n-th identical row of a file always gets the same id, so importing the
        same file (or an overlapping one) again adds nothing twice, while two equal
        purchases on one day in one file stay two entries.
        """

        rows = [self._cash_values(payload, categories) for payload in payloads]
        seen: dict[tuple[str, ...], int] = {}
        counts = {"added": 0, "unchanged": 0}
        with closing(self.connect()) as connection, connection:
            for values in rows:
                seen[values] = seen.get(values, 0) + 1
                digest = hashlib.sha256(json.dumps([owner, *values, seen[values]]).encode("utf-8")).hexdigest()
                inserted = connection.execute(
                    "INSERT OR IGNORE INTO manual_cash_entries VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (f"csv-{digest[:32]}", owner, *values),
                ).rowcount
                counts["added" if inserted else "unchanged"] += 1
        return counts

    def save_cash(self, owner: str, payload: dict, categories: Collection[str]) -> str:
        occurred_on, kind, amount, merchant, description, category, subcategory = self._cash_values(payload, categories)
        identifier = str(payload.get("id") or uuid.uuid4())
        with closing(self.connect()) as connection, connection:
            if payload.get("id"):
                changed = connection.execute(
                    "UPDATE manual_cash_entries SET occurred_on=?, flow_kind=?, amount=?, merchant=?, description=?, category=?, subcategory=? "
                    "WHERE id=? AND portfolio_id=?",
                    (occurred_on, kind, amount, merchant, description, category, subcategory, identifier, owner),
                ).rowcount
                if not changed:
                    raise ValueError("Cash entry not found")
            else:
                connection.execute(
                    "INSERT INTO manual_cash_entries VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (identifier, owner, occurred_on, kind, amount, merchant, description, category, subcategory),
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

    def account_balances(self, owner: str) -> list[dict]:
        """Current balances the user entered per account, oldest first."""

        with closing(self.connect()) as connection:
            rows = connection.execute(
                "SELECT id, account, occurred_on, balance FROM account_balances WHERE portfolio_id=? ORDER BY occurred_on, account",
                (owner,),
            ).fetchall()
        return [
            {"id": row["id"], "account": row["account"], "date": date.fromisoformat(row["occurred_on"]), "balance": Decimal(row["balance"])}
            for row in rows
        ]

    def save_account_balance(self, owner: str, payload: dict, accounts: Collection[str]) -> str:
        """Record an account's end-of-day balance, today unless ``payload["date"]`` says otherwise.

        One balance is kept per account and day: saving another for the same day
        replaces it. Editing an entry (``payload["id"]``) may move it to another day.
        """

        account = str(payload.get("account") or "").strip()
        if account not in accounts:
            raise ValueError("Choose an imported account")
        try:
            balance = Decimal(str(payload.get("amount", "")))
        except InvalidOperation:
            raise ValueError("Enter a valid EUR balance") from None
        if not balance.is_finite() or abs(balance) > Decimal(1000000000) or balance != balance.quantize(Decimal("0.01")):
            raise ValueError("The balance must be EUR with at most two decimal places")
        try:
            day = date.fromisoformat(str(payload["date"])) if payload.get("date") else date.today()  # noqa: DTZ011
        except ValueError:
            raise ValueError("Enter the balance date as YYYY-MM-DD") from None
        if day > date.today():  # noqa: DTZ011 - balances use the server's local calendar
            raise ValueError("A balance cannot be dated in the future")
        identifier = str(payload.get("id") or "")
        with closing(self.connect()) as connection, connection:
            if identifier:
                clash = connection.execute(
                    "SELECT 1 FROM account_balances WHERE portfolio_id=? AND account=? AND occurred_on=? AND id<>?",
                    (owner, account, day.isoformat(), identifier),
                ).fetchone()
                if clash:
                    raise ValueError("This account already has a balance for that day")
                if not connection.execute(
                    "UPDATE account_balances SET balance=?, occurred_on=? WHERE id=? AND portfolio_id=? AND account=?",
                    (str(balance), day.isoformat(), identifier, owner, account),
                ).rowcount:
                    raise ValueError("Balance entry not found")
                return identifier
            return self._upsert_balance(connection, owner, account, day, balance)[0]

    @staticmethod
    def _upsert_balance(connection, owner: str, account: str, day: date, balance: Decimal) -> tuple[str, str]:
        """``(id, "added" | "updated" | "unchanged")`` for one account's balance on one day."""

        existing = connection.execute(
            "SELECT id, balance FROM account_balances WHERE portfolio_id=? AND account=? AND occurred_on=?",
            (owner, account, day.isoformat()),
        ).fetchone()
        if existing and Decimal(existing[1]) == balance:
            return existing[0], "unchanged"
        identifier = existing[0] if existing else str(uuid.uuid4())
        connection.execute(
            "INSERT INTO account_balances VALUES (?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET balance=excluded.balance",
            (identifier, owner, account, day.isoformat(), str(balance)),
        )
        return identifier, "updated" if existing else "added"

    def import_account_balances(self, owner: str, entries: list[tuple[str, date, Decimal]]) -> dict[str, int]:
        """Add balances in bulk; a row already saved for that account and day is updated, never repeated."""

        counts = {"added": 0, "updated": 0, "unchanged": 0}
        with closing(self.connect()) as connection, connection:
            for account, day, balance in entries:
                counts[self._upsert_balance(connection, owner, account, day, balance)[1]] += 1
        return counts

    def delete_account_balance(self, owner: str, identifier: str) -> None:
        with closing(self.connect()) as connection, connection:
            if not connection.execute(
                "DELETE FROM account_balances WHERE portfolio_id=? AND id=?", (owner, identifier)
            ).rowcount:
                raise ValueError("Balance entry not found")
