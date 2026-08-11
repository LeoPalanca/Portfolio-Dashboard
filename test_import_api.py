from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app

TRADE_REPUBLIC_EXPORT = b"""datetime,date,account_type,category,type,asset_class,name,symbol,shares,price,amount,fee,tax,currency,original_amount,original_currency,fx_rate,description,transaction_id,counterparty_name,counterparty_iban,payment_reference,mcc_code
,2026-01-02,,TRADING,BUY,,Example ETF,IE0000000001,2,50,-100,-1,0,EUR,,,,Example purchase,,,,,
"""


class ImportApiTest(unittest.TestCase):
    def test_upload_archives_parses_and_deduplicates_statement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "private" / "movements.sqlite3"
            with (
                patch.object(app, "ROOT_DIR", root / "sources"),
                patch.object(app, "MOVEMENT_DATABASE", database),
                patch.object(app, "_movement_store", None),
                app.app.test_client() as client,
            ):
                first = client.post(
                    "/api/imports",
                    data={"source": "auto", "file": (io.BytesIO(TRADE_REPUBLIC_EXPORT), "export.csv")},
                    content_type="multipart/form-data",
                )
                second = client.post(
                    "/api/imports",
                    data={"source": "auto", "file": (io.BytesIO(TRADE_REPUBLIC_EXPORT), "export.csv")},
                    content_type="multipart/form-data",
                )
                status = client.get("/api/imports/status")

            imported_files = list((root / "sources" / "broker_exports" / "trade_republic").glob("*.csv"))

        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.get_json()["status"], "imported")
        self.assertEqual(first.get_json()["movements"], 1)
        self.assertEqual(second.get_json()["status"], "duplicate")
        self.assertEqual(status.get_json()["movements"], 1)
        supported = {item["id"]: item["format"] for item in status.get_json()["supported_sources"]}
        self.assertEqual(supported["trade_republic"], "CSV")
        self.assertEqual(supported["interactive_brokers"], "PDF")
        self.assertEqual(len(imported_files), 1)

    def test_rejects_unsupported_extension(self) -> None:
        with app.app.test_client() as client:
            response = client.post(
                "/api/imports",
                data={"file": (io.BytesIO(b"content"), "statement.txt")},
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Supported statement formats", response.get_json()["error"])

    def test_rejects_source_and_format_mismatch(self) -> None:
        with app.app.test_client() as client:
            response = client.post(
                "/api/imports",
                data={"source": "fineco", "file": (io.BytesIO(TRADE_REPUBLIC_EXPORT), "export.csv")},
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Fineco imports require XLSX; this file is CSV", response.get_json()["error"])


if __name__ == "__main__":
    unittest.main()
