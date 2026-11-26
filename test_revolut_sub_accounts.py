"""Consolidated Revolut statements: sub-accounts, own-account transfers and the joint account.

Every name, amount and description below is synthetic. The layout follows the
Italian consolidated statement: summaries per sub-account first, then one
transaction table per sub-account with a running balance ("Saldo"). Foreign
tables list each money column twice, the EUR equivalent first.
"""

from __future__ import annotations

import csv
import io
import tempfile
import unittest
from collections import Counter
from contextlib import ExitStack
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import app
from src.portfolio_dashboard.config import PortfolioProfile
from src.portfolio_dashboard.imports.revolut import ConsolidatedStatement, read_revolut_rows
from src.portfolio_dashboard.movements.reconcile import AccountMovement, BalanceCheckpoint, reconcile_balances

HOUSEHOLD = "household"
EUR_HEADER = ["Data", "Descrizione", "Categoria", "Denaro in entrata/uscita", "Saldo", "Imposte ritenute", "Altre imposte", "Costi"]
FX_HEADER = [
    "Data", "Descrizione", "Categoria", "Denaro in entrata/uscita", "Denaro in entrata/uscita", "Saldo", "Saldo",
    "Imposte ritenute", "Imposte ritenute", "Altre imposte", "Altre imposte", "Costi", "Costi",
]


def eur(day: str, description: str, category: str, amount: str, balance: str) -> list[str]:
    return [day, description, category, f"{amount}€", f"{balance}€", "0,00€", "0,00€", "0,00€"]


def chf(day: str, description: str, category: str, amount_eur: str, amount: str, balance_eur: str, balance: str) -> list[str]:
    return [
        day, description, category, f"{amount_eur}€", f"{amount} CHF", f"{balance_eur}€", f"{balance} CHF",
        "0,00€", "0,00 CHF", "0,00€", "0,00 CHF", "0,00€", "0,00 CHF",
    ]


def summary(title: str, holding: str = "Individuale", purpose: str = "Personali", holders: tuple[str, str] | None = None) -> list[list[str]]:
    block = [
        [title], [], ["Estremi del conto attuali"],
        ["Numero di conto", "N/A", "Data di apertura", "1 gen 2026"],
        ["Titolarità", holding, "Data di chiusura", ""],
        ["Scopo del conto", purpose, "Giorni di possesso (nel periodo selezionato)", "90"],
        [], ["Valore del deposito"], ["", "", "Saldo di apertura", "0,00€"], ["", "", "Saldo di chiusura", "0,00€"], [],
    ]
    if holders:
        block += [["Cointestazione del conto"], ["Co-titolare", holders[0], "Co-titolare", holders[1]], []]
    return [*block, ["---------"], []]


def table(title: str, header: list[str], rows: list[list[str]]) -> list[list[str]]:
    return [[title], [], ["Riepilogo delle transazioni"], header, *rows, ["Totale", "0,00€"], [], ["---------"], []]


def statement_rows(holders: bool = True, period: tuple[str, str] | None = None, joint: bool = True) -> list[list[str]]:
    """A statement with the personal account in EUR and CHF, Pro, a joint account,
    two pockets of the same name, a pocket with transfers, and the savings deposit."""

    rows: list[list[str]] = [["Conti correnti Riepiloghi"], []]
    if period:
        rows += [["Periodo", *period], []]
    rows += summary("Conto personale (EUR)") + summary("Conto personale (CHF)") + summary("Pro (EUR)", purpose="Professional")
    if joint:
        rows += summary("Conto cointestato (EUR)", "Cointestato", holders=("Example Owner", "Example Partner") if holders else None)
    rows += summary("Holidays (EUR)") + summary("Rainy day (EUR)") + summary("Rainy day (EUR)")
    rows += [["Conti deposito Riepiloghi"], [], ["Deposito senza vincoli  (EUR)"], [], ["Dettagli del conto di risparmio"],
             ["Titolarità", "Individuale"], [], ["---------"], [], ["Investment Services Riepiloghi"], [], ["---------"], []]
    rows += [["Conti correnti Estratti conto delle operazioni"], []]
    rows += table("Conto personale (EUR)", EUR_HEADER, [
        eur("2 mar 2026", "Ricarica di Apple Pay con *0000", "Ricarica", "200,00", "250,00"),
        eur("3 mar 2026", "Example Market", "Esercente", "-30,00", "220,00"),
        eur("4 mar 2026", "Accredita EUR Holidays da EUR", "Altri", "-50,00", "170,00"),
        eur("5 mar 2026", "Prelievo da Pocket", "Altri", "20,00", "190,00"),
        eur("6 mar 2026", "Conversione in CHF", "Cambio valuta", "-20,00", "170,00"),
        eur("7 mar 2026", "To EUR Pro", "Altri", "-10,00", "160,00"),
        eur("8 mar 2026", "To EUR Personal", "Altri", "5,00", "165,00"),
        eur("9 mar 2026", "Pagamento a favore di EXAMPLE OWNER & EXAMPLE PARTNER", "Altri", "-100,00", "65,00"),
        eur("10 mar 2026", "A EUR Conto deposito senza vincoli", "Altri", "-15,00", "50,00"),
        eur("11 mar 2026", "Pagamento da parte di Example Friend", "Altri", "12,00", "62,00"),
        eur("12 mar 2026", "Prelievo di contanti presso Example Bank", "Prelievo", "-40,00", "22,00"),
    ])
    rows += table("Conto personale (CHF)", FX_HEADER, [
        chf("6 mar 2026", "Conversione in CHF", "Cambio valuta", "20,00", "19,00", "20,00", "19,00"),
        chf("7 mar 2026", "Example Cafe", "Esercente", "-5,26", "-5,00", "14,74", "14,00"),
    ])
    rows += table("Pro (EUR)", EUR_HEADER, [
        eur("7 mar 2026", "To EUR Pro", "Altri", "10,00", "10,00"),
        eur("8 mar 2026", "To EUR Personal", "Altri", "-5,00", "5,00"),
        eur("9 mar 2026", "Example Software", "Esercente", "-3,00", "2,00"),
    ])
    if joint:
        rows += table("Conto cointestato (EUR)", EUR_HEADER, [
            eur("9 mar 2026", "Pagamento da parte di EXAMPLE OWNER", "Altri", "100,00", "100,00"),
            eur("10 mar 2026", "Pagamento da parte di Example Partner", "Altri", "80,00", "180,00"),
            eur("11 mar 2026", "Example Grocer", "Esercente", "-45,00", "135,00"),
            eur("12 mar 2026", "Pagamento da parte di Example Relative", "Altri", "25,00", "160,00"),
        ])
    rows += table("Holidays (EUR)", EUR_HEADER, [
        eur("4 mar 2026", "Accredita EUR Holidays da EUR", "Altri", "50,00", "50,00"),
        eur("5 mar 2026", "Prelievo da Pocket", "Altri", "-20,00", "30,00"),
    ])
    rows += table("Rainy day (EUR)", EUR_HEADER, [])
    rows += table("Rainy day (EUR)", EUR_HEADER, [eur("6 mar 2026", "Example Shop", "Esercente", "-4,00", "6,00")])
    rows += [["Conti deposito Transaction Statements"], [], ["Deposito senza vincoli  (EUR)"], [],
             ["Riepilogo della transazione (solo ricevuta degli interessi)"],
             ["Data", "Descrizione", "Gross rate", "Gross interest", "Imposte trattenute", "Other taxes", "Fees", "Net interest"],
             ["31/03/26", "Interessi netti", "2,00%", "0,04€", "0,01€", "0,00€", "0,00€", "0,03€"], [], ["---------"], [],
             ["Investment Services Estratti conto delle operazioni"], [], ["---------"]]
    return rows


def statement_text(**options) -> str:
    output = io.StringIO()
    csv.writer(output).writerows(statement_rows(**options))
    return output.getvalue()


def household_profiles() -> dict[str, PortfolioProfile]:
    return {HOUSEHOLD: PortfolioProfile(display_name="Household", features={app.REVOLUT_JOINT_ACCOUNT_FEATURE})}


def no_network(*_args, **_kwargs):
    raise AssertionError("the consolidated statement prices foreign rows itself")


def isolated_app(stack: ExitStack, root: Path) -> None:
    for name, value in (
        ("ROOT_DIR", root / "sources"),
        ("MOVEMENT_DATABASE", root / "private" / "movements.sqlite3"),
        ("_movement_store", None),
        ("_legacy_imported_portfolios", {app.PRIMARY_PORTFOLIO_ID, HOUSEHOLD}),
        ("fetch_history", no_network),
    ):
        stack.enter_context(patch.object(app, name, value))
    stack.enter_context(patch.object(app, "read_expense_category_rules", return_value=[]))
    stack.enter_context(patch.dict(app.SETTINGS.portfolios, household_profiles()))


def upload(client, owner: str, text: str, name: str = "statement.csv"):
    return client.post(
        "/api/imports",
        data={"portfolio_id": owner, "file": (io.BytesIO(text.encode("utf-8")), name)},
        content_type="multipart/form-data",
    )


class SubAccountParsingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.statement = ConsolidatedStatement(statement_rows())
        self.rows = self.statement.movements

    def test_every_row_names_its_sub_account_kind_and_currency(self) -> None:
        kinds = {account.label: account.kind for account in self.statement.accounts}
        self.assertEqual(kinds, {
            "Revolut · Conto personale (EUR)": "personal",
            "Revolut · Conto personale (CHF)": "personal",
            "Revolut · Pro (EUR)": "pro",
            "Revolut · Conto cointestato (EUR)": "joint",
            "Revolut · Holidays (EUR)": "pocket",
            "Revolut · Rainy day (EUR)": "pocket",
            "Revolut · Rainy day #2 (EUR)": "pocket",
            "Revolut · Deposito senza vincoli (EUR)": "deposit",
        })
        self.assertEqual(
            Counter(row["Conto"] for row in self.rows),
            Counter({
                "Revolut · Conto personale (EUR)": 11, "Revolut · Conto personale (CHF)": 2, "Revolut · Pro (EUR)": 3,
                "Revolut · Conto cointestato (EUR)": 4, "Revolut · Holidays (EUR)": 2, "Revolut · Rainy day #2 (EUR)": 1,
                # The transfer the current account lists, mirrored, and the interest.
                "Revolut · Deposito senza vincoli (EUR)": 2,
            }),
        )
        cafe = next(row for row in self.rows if row["Descrizione"] == "Example Cafe")
        # The EUR equivalent comes first in the real layout; the native column is read as the amount.
        self.assertEqual((cafe["Valuta"], cafe["Importo"], cafe["Importo EUR"], cafe["Saldo"]), ("CHF", "-5.00", "-5.26", "14.00"))
        self.assertEqual(cafe["Sottoconto"], "Conto personale")

    def test_own_account_transfers_are_internal_on_both_legs_and_joint_ones_cross(self) -> None:
        marks = {(row["Conto"].split(" · ")[1], row["Descrizione"]): row["Trasferimento"] for row in self.rows}
        internal = [
            ("Conto personale (EUR)", "Accredita EUR Holidays da EUR"), ("Holidays (EUR)", "Accredita EUR Holidays da EUR"),
            ("Conto personale (EUR)", "Prelievo da Pocket"), ("Holidays (EUR)", "Prelievo da Pocket"),
            ("Conto personale (EUR)", "Conversione in CHF"), ("Conto personale (CHF)", "Conversione in CHF"),
            ("Conto personale (EUR)", "To EUR Pro"), ("Pro (EUR)", "To EUR Pro"),
            ("Conto personale (EUR)", "To EUR Personal"), ("Pro (EUR)", "To EUR Personal"),
            ("Conto personale (EUR)", "A EUR Conto deposito senza vincoli"),
            ("Deposito senza vincoli (EUR)", "A EUR Conto deposito senza vincoli"),
        ]
        for key in internal:
            with self.subTest(leg=key):
                self.assertEqual(marks[key], "interno")
        self.assertEqual(marks[("Conto personale (EUR)", "Pagamento a favore di EXAMPLE OWNER & EXAMPLE PARTNER")], "cointestato")
        self.assertEqual(marks[("Conto cointestato (EUR)", "Pagamento da parte di EXAMPLE OWNER")], "cointestato")
        self.assertEqual(marks[("Conto cointestato (EUR)", "Pagamento da parte di Example Partner")], "cointestato")
        external = [
            ("Conto personale (EUR)", "Example Market"), ("Conto personale (EUR)", "Pagamento da parte di Example Friend"),
            ("Conto cointestato (EUR)", "Pagamento da parte di Example Relative"), ("Rainy day #2 (EUR)", "Example Shop"),
            ("Conto personale (EUR)", "Ricarica di Apple Pay con *0000"),
        ]
        for key in external:
            with self.subTest(external=key):
                self.assertEqual(marks[key], "")

    def test_without_a_holder_list_the_joint_transfer_is_told_by_its_opposite_leg(self) -> None:
        rows = ConsolidatedStatement(statement_rows(holders=False)).movements
        marks = {(row["Tipo conto"], row["Descrizione"]): row["Trasferimento"] for row in rows}
        self.assertEqual(marks[("personal", "Pagamento a favore di EXAMPLE OWNER & EXAMPLE PARTNER")], "cointestato")
        self.assertEqual(marks[("joint", "Pagamento da parte di EXAMPLE OWNER")], "cointestato")
        self.assertEqual(marks[("joint", "Pagamento da parte di Example Partner")], "")

    def test_a_regular_statement_has_no_sub_accounts_and_reads_as_before(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "account-statement.csv"
            path.write_text(
                "Tipo,Prodotto,Data di inizio,Data di completamento,Descrizione,Importo,Costo,Valuta,State,Saldo\n"
                "Pagamento con carta,Attuale,2026-03-03 09:00:00,2026-03-03 09:00:00,Example Market,-30.00,0.00,EUR,COMPLETATO,20.00\n",
                encoding="utf-8",
            )
            rows = read_revolut_rows(path)
            household = app.revolut_profile_rows(path, joint=True)
        self.assertNotIn("Conto", rows[0])
        self.assertEqual(len(household), 1)


class ProfileSplitTest(unittest.TestCase):
    def parse(self, owner: str) -> list[dict]:
        with tempfile.TemporaryDirectory() as temporary, patch.dict(app.SETTINGS.portfolios, household_profiles()), patch.object(app, "fetch_history", no_network):
            path = Path(temporary) / "statement.csv"
            path.write_text(statement_text(), encoding="utf-8")
            return app.parse_statement_movements("revolut", path, owner)

    def test_the_joint_account_belongs_only_to_the_profile_with_the_feature(self) -> None:
        own = self.parse(app.PRIMARY_PORTFOLIO_ID)
        household = self.parse(HOUSEHOLD)
        own_accounts = {(row.get("metadata") or {}).get("account_label") for row in own if row["event_type"] == "cash_flow"}
        household_accounts = {(row.get("metadata") or {}).get("account_label") for row in household if row["event_type"] == "cash_flow"}
        self.assertNotIn("Revolut · Conto cointestato (EUR)", own_accounts)
        self.assertEqual(household_accounts, {"Revolut · Conto cointestato (EUR)"})
        self.assertEqual(len([row for row in household if row["event_type"] == "cash_flow"]), 4)

    def test_classification_of_each_side(self) -> None:
        own = Counter((row["event_type"], row["description"]) for row in self.parse(app.PRIMARY_PORTFOLIO_ID) if row["event_type"] not in {"cash_flow", "balance_checkpoint"})
        self.assertEqual(own, Counter({
            ("spend", "Example Market"): 1, ("spend", "Example Cafe"): 1, ("spend", "Example Software"): 1, ("spend", "Example Shop"): 1,
            ("income", "Pagamento da parte di Example Friend"): 1, ("income", "Interessi netti"): 1,
            ("cash_withdrawal", "Prelievo di contanti presso Example Bank"): 1,
        }))
        household = Counter((row["event_type"], row["description"]) for row in self.parse(HOUSEHOLD) if row["event_type"] not in {"cash_flow", "balance_checkpoint"})
        self.assertEqual(household, Counter({("spend", "Example Grocer"): 1, ("income", "Pagamento da parte di Example Relative"): 1}))

    def test_foreign_rows_are_priced_by_the_statement_itself(self) -> None:
        cafe = next(row for row in self.parse(app.PRIMARY_PORTFOLIO_ID) if row["description"] == "Example Cafe" and row["event_type"] == "spend")
        self.assertEqual((cafe["currency"], cafe["amount"], cafe["metadata"]["amount_eur"]), ("CHF", Decimal("-5.00"), Decimal("5.26")))
        self.assertEqual(cafe["metadata"]["account_label"], "Revolut · Conto personale (CHF)")

    def test_each_sub_account_reconciles_from_its_own_running_balance(self) -> None:
        for owner, expected in ((app.PRIMARY_PORTFOLIO_ID, 5), (HOUSEHOLD, 1)):
            rows = self.parse(owner)
            movements, checkpoints = [], []
            for row in rows:
                account = app.reconciliation_account({**row, "source_kind": "revolut"})
                if row["event_type"] == "balance_checkpoint":
                    checkpoints.append(BalanceCheckpoint(account, row["occurred_on"], Decimal(str(row["amount"]))))
                elif row["event_type"] == "cash_flow":
                    movements.append(AccountMovement(account, row["occurred_on"].date(), Decimal(str(row["amount"]))))
            result = reconcile_balances(movements, checkpoints)
            with self.subTest(owner=owner):
                self.assertEqual(len(result["intervals"]), expected)
                self.assertEqual([item["gap"] for item in result["intervals"]], [Decimal(0)] * expected)
                self.assertEqual(result["rows"], [])
        own = {row["account"]: row for row in self.parse(app.PRIMARY_PORTFOLIO_ID) if row["event_type"] == "balance_checkpoint"}
        self.assertNotIn("Revolut · Deposito senza vincoli (EUR)", own)  # interest-only: no running balance

    def test_coverage_is_first_to_last_row_or_the_stated_period(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            plain, stated = Path(temporary) / "plain.csv", Path(temporary) / "stated.csv"
            plain.write_text(statement_text(), encoding="utf-8")
            stated.write_text(statement_text(period=("1 mar 2026", "31 mar 2026")), encoding="utf-8")
            plain_rows, stated_rows = (app.parse_statement_movements("revolut", path) for path in (plain, stated))
            plain_coverage = {account: (first, last) for account, first, last in app.import_coverage_ranges("revolut", plain, plain_rows)}
            stated_coverage = {account: (first, last) for account, first, last in app.import_coverage_ranges("revolut", stated, stated_rows)}
        self.assertEqual(plain_coverage["Revolut · Holidays (EUR)"], (date(2026, 3, 4), date(2026, 3, 5)))
        self.assertEqual(plain_coverage["Revolut · Conto personale (EUR)"], (date(2026, 3, 2), date(2026, 3, 12)))
        self.assertEqual(stated_coverage["Revolut · Holidays (EUR)"], (date(2026, 3, 1), date(2026, 3, 31)))
        opening = next(row for row in stated_rows if row["event_type"] == "balance_checkpoint" and row["account"] == "Revolut · Holidays (EUR)")
        self.assertEqual(opening["occurred_on"], date(2026, 2, 28))


class JointProfileImportTest(unittest.TestCase):
    def test_one_file_imports_into_both_profiles_and_transfers_are_neither_income_nor_spend(self) -> None:
        text = statement_text()
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            isolated_app(stack, Path(temporary))
            client = stack.enter_context(app.app.test_client())
            own_first = upload(client, app.PRIMARY_PORTFOLIO_ID, text)
            household_first = upload(client, HOUSEHOLD, text)
            own_again = upload(client, app.PRIMARY_PORTFOLIO_ID, text)
            household_again = upload(client, HOUSEHOLD, text)
            own = client.get(f"/api/expenses?person={app.PRIMARY_PORTFOLIO_ID}").get_json()
            household = client.get(f"/api/expenses?person={HOUSEHOLD}").get_json()

        self.assertEqual([response.get_json()["status"] for response in (own_first, household_first)], ["imported", "imported"])
        self.assertEqual([response.get_json()["status"] for response in (own_again, household_again)], ["duplicate", "duplicate"])

        to_joint = [row for row in own["rows"] if row["merchant"] == "Joint account"]
        self.assertEqual([(row["flow_kind"], row["amount_eur"]) for row in to_joint], [("transfer_out", 100.0)])
        contributions = sorted((row["merchant"], row["flow_kind"], row["amount_eur"]) for row in household["rows"] if row["flow_kind"] == "top_up")
        self.assertEqual(contributions, [("EXAMPLE OWNER", "top_up", 100.0), ("Example Partner", "top_up", 80.0)])
        self.assertEqual(household["summary"]["income_eur"], 25.0)
        self.assertEqual(household["summary"]["spend_eur"], 45.0)
        # Pockets, Pro and the exchange to CHF are neither income nor spending.
        self.assertEqual(own["summary"]["income_eur"], 12.03)
        self.assertAlmostEqual(own["summary"]["spend_eur"], 42.26)

        accounts = {item["account"]: item for item in own["reconciliation"]["accounts"]}
        self.assertEqual(accounts["Revolut · Conto personale (CHF)"]["currency"], "CHF")
        self.assertEqual(accounts["Revolut · Conto personale (CHF)"]["latest_balance_eur"], 14.0)
        for label in ("Revolut · Conto personale (EUR)", "Revolut · Conto personale (CHF)", "Revolut · Pro (EUR)",
                      "Revolut · Holidays (EUR)", "Revolut · Rainy day #2 (EUR)"):
            with self.subTest(account=label):
                self.assertEqual(accounts[label]["status"], "reconciled")
        self.assertEqual([item["status"] for item in household["reconciliation"]["accounts"]], ["reconciled"])
        self.assertEqual(own["summary"]["calculated_income_eur"] + own["summary"]["calculated_expenses_eur"], 0)

    def test_a_statement_without_a_joint_account_is_refused_by_the_household_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            isolated_app(stack, Path(temporary))
            client = stack.enter_context(app.app.test_client())
            response = upload(client, HOUSEHOLD, statement_text(joint=False))
        self.assertEqual(response.status_code, 400)
        self.assertIn("no joint account", response.get_json()["error"])


class CrossFormatTest(unittest.TestCase):
    def test_rows_already_stored_from_the_regular_statement_are_skipped_and_that_sub_account_is_not_balanced(self) -> None:
        regular = (
            "Tipo,Prodotto,Data di inizio,Data di completamento,Descrizione,Importo,Costo,Valuta,State,Saldo\n"
            "Pagamento con carta,Attuale,2026-03-03 10:15:00,2026-03-03 10:15:00,Example Market,-30.00,0.00,EUR,COMPLETATO,220.00\n"
        )
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            isolated_app(stack, Path(temporary))
            client = stack.enter_context(app.app.test_client())
            first = upload(client, app.PRIMARY_PORTFOLIO_ID, regular, "account-statement.csv")
            second = upload(client, app.PRIMARY_PORTFOLIO_ID, statement_text())
            own = client.get(f"/api/expenses?person={app.PRIMARY_PORTFOLIO_ID}").get_json()
            stored = app.get_movement_store().movements(app.PRIMARY_PORTFOLIO_ID, ("cash_flow",))

        self.assertEqual(first.get_json()["status"], "imported")
        self.assertGreaterEqual(second.get_json()["duplicates"], 1)
        self.assertEqual(sum(1 for row in stored if Decimal(str(row["amount"])) == Decimal(-30) and row["occurred_on"].startswith("2026-03-03")), 1)
        accounts = {item["account"]: item["status"] for item in own["reconciliation"]["accounts"]}
        self.assertEqual(accounts["Revolut · Conto personale (EUR)"], "no_balance")
        self.assertEqual(accounts["Revolut · Holidays (EUR)"], "reconciled")
        self.assertEqual(own["summary"]["calculated_income_eur"] + own["summary"]["calculated_expenses_eur"], 0)


if __name__ == "__main__":
    unittest.main()
