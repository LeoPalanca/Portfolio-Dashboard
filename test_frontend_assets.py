"""The frontend lives in templates/ and static/, not inside app.py.

These tests lock in the 0.4 extraction so the stylesheet and script cannot drift back
into a Python string literal, and so the config island stays the single channel for
server-provided values.
"""

from __future__ import annotations

import ast
import json
import re
import unittest
from pathlib import Path
from typing import Any

import app

APP_CONFIG_RE = re.compile(
    r'<script id="app-config" type="application/json">(.*?)</script>', re.DOTALL
)
PLACEHOLDER_RE = re.compile(r"__[A-Z0-9_]+__")
APP_DIR = Path(__file__).resolve().parent


def render() -> str:
    with app.app.test_client() as client:
        return client.get("/").get_data(as_text=True)


class FrontendAssetTest(unittest.TestCase):
    def test_page_links_external_assets(self) -> None:
        html = render()
        self.assertIn('href="/static/app.css', html)
        self.assertIn('src="/static/app.js', html)
        self.assertNotIn("<style>", html)
        # the config island is the only inline script the page may carry
        self.assertEqual(html.count("<script"), 2)

    def test_static_assets_are_served(self) -> None:
        with app.app.test_client() as client:
            css = client.get("/static/app.css")
            js = client.get("/static/app.js")

        self.assertEqual(css.status_code, 200)
        self.assertEqual(js.status_code, 200)
        # guards against an empty or truncated extraction
        self.assertGreater(len(css.get_data()), 40_000)
        self.assertGreater(len(js.get_data()), 120_000)

    def test_config_island_carries_server_values(self) -> None:
        match = APP_CONFIG_RE.search(render())
        assert match is not None
        config: dict[str, Any] = json.loads(match.group(1).replace("\\u003c", "<"))

        self.assertEqual(config["primaryPortfolioId"], app.PRIMARY_PORTFOLIO_ID)
        self.assertEqual(config["since2024PortfolioIds"], sorted(app.SINCE_2024_PORTFOLIO_IDS))
        self.assertEqual(config["appVersion"], app.APP_VERSION)

    def test_config_island_cannot_break_out_of_its_script_tag(self) -> None:
        match = APP_CONFIG_RE.search(render())
        assert match is not None
        self.assertNotIn("<", match.group(1))

    def test_no_build_placeholders_survive_rendering(self) -> None:
        with app.app.test_client() as client:
            html = client.get("/").get_data(as_text=True)
            js = client.get("/static/app.js").get_data(as_text=True)

        self.assertIsNone(PLACEHOLDER_RE.search(html))
        self.assertIsNone(PLACEHOLDER_RE.search(js))

    def test_app_py_holds_no_inline_frontend(self) -> None:
        tree = ast.parse((APP_DIR / "app.py").read_text(encoding="utf-8"))
        oversized = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and len(node.value) > 10_000
        ]
        self.assertEqual(oversized, [], "frontend markup has leaked back into app.py")


if __name__ == "__main__":
    unittest.main()
