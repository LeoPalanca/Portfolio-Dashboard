"""Archived imports read by an older parser are read again at startup, once, in place."""

from __future__ import annotations

import hashlib
import io
import tempfile
import unittest
from contextlib import ExitStack
from datetime import date
from pathlib import Path
from unittest.mock import patch

from openpyxl import Workbook

import app


def export(rows: list[tuple]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Lista Operazione"
    sheet.append(("Data", "Operazione", "Dettagli", "Conto o carta", "Contabilizzazione", "Categoria ", "Valuta", "Importo"))
    for day, merchant, category, amount in rows:
        sheet.append((day, merchant, f"Payment to Account Owner from {merchant}", "Conto", "SI", category, "EUR", amount))
    output = io.BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


EXPORT = export(
    [
        (date(2023, 5, 2), "Example employer", "Stipendi e pensioni", 2000),
        (date(2023, 5, 3), "Example market", "Generi alimentari e supermercato", -50),
        (date(2023, 5, 4), "Account Owner", "Bonifici in uscita", -300),
        (date(2023, 5, 9), "Account Owner", "Bonifici ricevuti", 100),
    ]
)


class OutdatedImportRereadTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.stack = ExitStack()
        for name, value in (
            ("ROOT_DIR", self.root / "sources"),
            ("MOVEMENT_DATABASE", self.root / "private" / "movements.sqlite3"),
            ("_movement_store", None),
            ("_legacy_imported_portfolios", {app.PRIMARY_PORTFOLIO_ID}),
            ("_legacy_import_errors", {}),
            ("_stale_imports", {}),
            ("SELF_TRANSFER_NAMES", ("account owner",)),
            ("read_expense_category_rules", lambda *args: []),
        ):
            self.stack.enter_context(patch.object(app, name, value))

    def tearDown(self) -> None:
        self.stack.close()
        self.temporary.cleanup()

    def archive(self, relative: str, content: bytes) -> Path:
        path = self.root / "sources" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def record_ledger4_import(self, path: Path, stored_path: str | None = None) -> None:
        """What the ledger-4 parser stored for this file: own-account transfers were dropped."""

        movements = [app.normalize_expense_movement(event) for event in app.read_intesa_expense_events(path)]
        app.get_movement_store().record_import(
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            source_kind="intesa",
            original_name=path.name,
            stored_path=stored_path or app.configured_path_label(path),
            parser_version="ledger-4",
            movements=movements,
        )

    def startup(self) -> None:
        app._legacy_imported_portfolios.clear()
        app.ensure_legacy_statements_imported(app.PRIMARY_PORTFOLIO_ID)

    def test_an_archived_ledger4_intesa_import_gains_its_own_account_transfers(self) -> None:
        self.record_ledger4_import(self.archive("cash_exports/intesa/account_operations-20230510-aaaaaaaaaa.xlsx", EXPORT))
        store = app.get_movement_store()
        before = {row["id"]: row["event_type"] for row in store.movements()}

        self.startup()
        after = {row["id"]: row["event_type"] for row in store.movements()}
        versions = {record.parser_version for record in store.imports()}
        self.startup()
        again = {row["id"]: row["event_type"] for row in store.movements()}

        self.assertEqual(sorted(before.values()), ["income", "spend"])
        self.assertEqual(sorted(after.values()), ["income", "personal_transfer", "spend", "top_up"])
        self.assertTrue(set(before.items()) <= set(after.items()), "re-reading kept the earlier rows and their ids")
        self.assertEqual(versions, {app.IMPORT_PARSER_VERSION})
        self.assertEqual(again, after)
        self.assertEqual(app._legacy_import_errors[app.PRIMARY_PORTFOLIO_ID], [])
        events = app.read_ledger_expenses()
        self.assertEqual(app.summarize_expense_events(events)["summary"]["income_eur"], 2000.0)

    def test_imports_outside_the_rediscovered_folders_are_reread_and_missing_files_reported(self) -> None:
        # Not under an archive folder nor matching a configured pattern: only the
        # import record knows where this file is.
        self.record_ledger4_import(self.archive("old-uploads/bank.xlsx", EXPORT))
        # A file that was imported, then removed from the archive by hand.
        gone = self.root / "removed-from-disk.xlsx"
        gone.write_bytes(export([(date(2023, 1, 2), "Example cafe", "Ristoranti e bar", -4)]))
        self.record_ledger4_import(gone, stored_path="sources/cash_exports/intesa/removed-from-disk.xlsx")

        self.startup()
        store = app.get_movement_store()
        versions = {record.original_name: record.parser_version for record in store.imports()}
        status = app.import_status_payload()

        self.assertEqual(versions["bank.xlsx"], app.IMPORT_PARSER_VERSION)
        self.assertIn("top_up", {row["event_type"] for row in store.movements()})
        self.assertEqual(versions["removed-from-disk.xlsx"], "ledger-4")
        self.assertEqual(status["outdated_without_file"], ["removed-from-disk.xlsx"])
        self.assertEqual(len(store.imports()), 2)

    def test_a_deleted_import_stays_deleted(self) -> None:
        incoming = self.root / "upload.xlsx"
        incoming.write_bytes(EXPORT)
        app.import_statement_path(incoming, original_name="upload.xlsx", requested_source="intesa")
        record = app.get_movement_store().imports()[0]
        app.delete_statement_import(record.id)

        with patch.object(app, "IMPORT_PARSER_VERSION", "next"):
            self.startup()

        self.assertEqual(app.get_movement_store().imports(), [])
        self.assertEqual(app.get_movement_store().movements(), [])


if __name__ == "__main__":
    unittest.main()
