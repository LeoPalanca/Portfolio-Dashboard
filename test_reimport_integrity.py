"""Re-reading, deleting and overlapping imports must never duplicate or lose movements."""

# Revolut statements carry local wall-clock times, so the parser works with naive datetimes.
# ruff: noqa: DTZ001

from __future__ import annotations

import io
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import app
from src.portfolio_dashboard.config import PortfolioProfile
from src.portfolio_dashboard.imports.revolut import amount
from src.portfolio_dashboard.movements import MovementStore
from src.portfolio_dashboard.movements.store import ImportRecord

TR_HEADER = (
    "datetime,date,account_type,category,type,asset_class,name,symbol,shares,price,amount,fee,tax,currency,"
    "original_amount,original_currency,fx_rate,description,transaction_id,counterparty_name,counterparty_iban,"
    "payment_reference,mcc_code\n"
)


def tr_buy(day: str, transaction_id: str, value: int = 100) -> str:
    return f",{day},,TRADING,BUY,,Example ETF,XX0000000001,2,{value // 2},-{value},-1,0,EUR,,,,Purchase,{transaction_id},,,,\n"


class ReparseReplacesRowsTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.store = MovementStore(Path(temporary.name) / "movements.sqlite3")
        self.base = {"event_type": "dividend", "account": "Broker", "asset": "ETF", "currency": "EUR"}

    def record(self, movements: list[dict]) -> ImportRecord:
        return self.store.record_import(
            sha256="file", source_kind="bank", original_name="file.csv", stored_path="file.csv",
            parser_version="old", movements=movements,
        )

    def test_a_corrected_reading_replaces_rows_and_drops_rows_it_no_longer_reads(self) -> None:
        record = self.record([
            {**self.base, "date": "2026-01-02", "amount": "10"},
            {**self.base, "date": "2026-02-02", "amount": "1.00"},
            {**self.base, "date": "2026-03-02", "amount": "5"},
        ])
        ids = [row["id"] for row in self.store.movements()]
        counts = self.store.enrich_import(record, parser_version="new", movements=[
            {**self.base, "date": "2026-01-02", "amount": "10"},
            {**self.base, "date": "2026-02-02", "amount": "0.74"},
        ])
        rows = self.store.movements()
        self.assertEqual(counts, (0, 2, 1))
        self.assertEqual([(row["id"], row["amount"]) for row in rows], [(ids[0], "10"), (ids[1], "0.74")])
        self.assertEqual(self.store.import_by_hash("file").parser_version, "new")
        self.assertEqual(self.store.imports()[0].movement_count, 2)
        with sqlite3.connect(self.store.path) as connection:
            removed = [json.loads(row[0]) for row in connection.execute("SELECT previous_json FROM movement_revisions")]
        self.assertIn({"amount": "5", "removed": f"reparsed import {record.id}"}, [
            {"amount": item["amount"], "removed": item.get("removed")} for item in removed if item.get("removed")
        ])

    def test_reading_the_same_file_twice_changes_nothing(self) -> None:
        movements = [{**self.base, "date": "2026-01-02", "amount": "10"}, {**self.base, "date": "2026-01-02", "amount": "10"}]
        record = self.record(movements)
        self.assertEqual(self.store.enrich_import(record, parser_version="new", movements=movements), (0, 2, 0))
        self.assertEqual(len(self.store.movements()), 2)

    def test_deleted_import_is_remembered_until_uploaded_again(self) -> None:
        record = self.record([{**self.base, "date": "2026-01-02", "amount": "10"}])
        self.assertEqual(self.store.delete_import(record), 1)
        self.assertEqual((self.store.movements(), self.store.imports()), ([], []))
        self.assertTrue(self.store.is_removed("file"))
        self.store.forget_removed("file")
        self.assertFalse(self.store.is_removed("file"))


class DeleteImportTest(unittest.TestCase):
    def test_deleting_a_file_keeps_rows_another_file_also_contains(self) -> None:
        first = TR_HEADER + tr_buy("2026-01-02", "a") + tr_buy("2026-01-09", "b")
        second = TR_HEADER + tr_buy("2026-01-09", "b") + tr_buy("2026-01-16", "c")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with (
                patch.object(app, "ROOT_DIR", root / "sources"),
                patch.object(app, "MOVEMENT_DATABASE", root / "private" / "movements.sqlite3"),
                patch.object(app, "_movement_store", None),
                patch.object(app, "_legacy_imported_portfolios", {app.PRIMARY_PORTFOLIO_ID}),
                app.app.test_client() as client,
            ):
                for name, content in (("first.csv", first), ("second.csv", second)):
                    response = client.post(
                        "/api/imports",
                        data={"source": "trade_republic", "file": (io.BytesIO(content.encode()), name)},
                        content_type="multipart/form-data",
                    )
                    self.assertEqual(response.status_code, 200)
                listed = client.get("/api/imports/status").get_json()["import_list"]
                self.assertEqual([item["name"] for item in listed], ["second.csv", "first.csv"])
                first_id = listed[1]["id"]
                archived = app.configured_path(app.get_movement_store().imports()[0].stored_path)

                deleted = client.delete(f"/api/imports/{first_id}").get_json()
                trades = [row["metadata"].get("transaction_id") for row in app.get_movement_store().movements(None, ("trade",))]
                listed_after = client.get("/api/imports/status").get_json()["import_list"]

                startup = app.import_statement_path(archived, requested_source="trade_republic", archive=False, skip_removed=True)
                reupload = client.post(
                    "/api/imports",
                    data={"source": "trade_republic", "file": (io.BytesIO(first.encode()), "first.csv")},
                    content_type="multipart/form-data",
                ).get_json()
                missing = client.delete("/api/imports/999").status_code

        self.assertEqual((deleted["removed"], deleted["restored"], deleted["not_rechecked"]), (4, 2, []))
        self.assertEqual(sorted(trades), ["b", "c"])
        self.assertEqual([item["name"] for item in listed_after], ["second.csv"])
        self.assertEqual(startup["status"], "removed")
        self.assertEqual(reupload.get("status"), "imported", reupload)
        self.assertEqual(missing, 400)


class ParserUpgradeTest(unittest.TestCase):
    def test_a_newer_parser_rereads_archived_files_without_duplicates(self) -> None:
        export = TR_HEADER + tr_buy("2026-01-02", "a") + tr_buy("2026-01-09", "b")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            incoming = root / "export.csv"
            incoming.write_text(export, encoding="utf-8")
            with (
                patch.object(app, "ROOT_DIR", root / "sources"),
                patch.object(app, "MOVEMENT_DATABASE", root / "private" / "movements.sqlite3"),
                patch.object(app, "_movement_store", None),
                patch.object(app, "_legacy_import_errors", {}),
            ):
                app.import_statement_path(incoming, requested_source="trade_republic")
                before = [(row["id"], row["amount"]) for row in app.get_movement_store().movements()]
                with patch.object(app, "IMPORT_PARSER_VERSION", "newer"), patch.object(app, "_legacy_imported_portfolios", set()):
                    app.ensure_legacy_statements_imported(app.PRIMARY_PORTFOLIO_ID)
                after = [(row["id"], row["amount"]) for row in app.get_movement_store().movements()]
                versions = {record.parser_version for record in app.get_movement_store().imports()}
        self.assertEqual(after, before)
        self.assertEqual(versions, {"newer"})


class FamilyExportTest(unittest.TestCase):
    def test_a_family_members_archived_export_stays_out_of_the_primary_portfolio(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / "broker_exports" / "trade_republic"
            folder.mkdir(parents=True)
            for name in ("trade-republic-own.csv", "relative-trade-republic.csv"):
                (folder / name).write_text(TR_HEADER, encoding="utf-8")
            with (
                patch.object(app, "ROOT_DIR", Path(temporary)),
                patch.dict(app.SETTINGS.portfolios, {"household": PortfolioProfile(display_name="Household", trade_republic_name="relative")}),
            ):
                names = [path.name for path, source in app.legacy_statement_candidates(app.PRIMARY_PORTFOLIO_ID) if source == "trade_republic"]
        self.assertEqual(names, ["trade-republic-own.csv"])


class RevolutOverlapTest(unittest.TestCase):
    @staticmethod
    def cash(moment: str, value: str) -> dict:
        return {"occurred_on": moment, "event_type": "cash_flow", "currency": "EUR", "amount": value}

    def test_rows_from_the_other_statement_format_are_skipped_one_for_one(self) -> None:
        consolidated = [self.cash("2026-06-15T00:00:00", "100"), self.cash("2026-06-16T00:00:00", "-3.00"), self.cash("2026-06-16T00:00:00", "-3")]
        regular = [
            {**self.cash("", "100"), "occurred_on": datetime(2026, 6, 15, 10, 4)},
            {**self.cash("", "-3"), "occurred_on": datetime(2026, 6, 16, 9, 0)},
            {**self.cash("", "-3"), "occurred_on": datetime(2026, 6, 16, 18, 0)},
            {**self.cash("", "-3"), "occurred_on": datetime(2026, 6, 16, 20, 0)},
            {"occurred_on": datetime(2026, 6, 16, 9, 0), "event_type": "spend", "currency": "EUR", "amount": "-3"},
        ]
        kept, skipped = app.drop_revolut_cross_format_duplicates(regular, consolidated)
        self.assertEqual(skipped, 3)
        self.assertEqual([(item["event_type"], item["occurred_on"].hour) for item in kept], [("cash_flow", 20), ("spend", 9)])

    def test_two_timed_rows_are_separate_movements(self) -> None:
        kept, skipped = app.drop_revolut_cross_format_duplicates(
            [{**self.cash("", "-3"), "occurred_on": datetime(2026, 6, 16, 18, 0)}], [self.cash("2026-06-16T09:00:00", "-3")]
        )
        self.assertEqual((len(kept), skipped), (1, 0))

    def test_consolidated_amounts_in_either_notation(self) -> None:
        self.assertEqual(amount("€12.50"), "12.50")
        self.assertEqual(Decimal(amount("-1.234,56€")), Decimal("-1234.56"))
        self.assertEqual(amount(""), "")


if __name__ == "__main__":
    unittest.main()
