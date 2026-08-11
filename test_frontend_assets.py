"""The frontend lives in templates/ and static/, not inside app.py.

These tests lock in the 0.4 extraction so the stylesheet and script cannot drift back
into a Python string literal, and so the config island stays the single channel for
server-provided values.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
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
        # Exactly three script tags are sanctioned: the pre-paint theme boot,
        # the JSON config island, and the external bundle. Anything else means
        # logic is creeping back into the template.
        self.assertEqual(html.count("<script"), 3)
        self.assertIn('id="app-config"', html)
        self.assertIn('localStorage.getItem("theme")', html)

    def test_theme_boot_runs_before_the_stylesheet_paints(self) -> None:
        html = render()
        # the inline boot script must precede </head> so no flash of the wrong theme
        self.assertLess(html.index('localStorage.getItem("theme")'), html.index("</head>"))

    def test_both_themes_define_the_same_tokens(self) -> None:
        with app.app.test_client() as client:
            css = client.get("/static/app.css").get_data(as_text=True)

        blocks = re.findall(r"(?::root|\[data-theme=\"light\"\])[^{]*\{([^}]*)\}", css)
        self.assertGreaterEqual(len(blocks), 3, "expected :root plus both light selectors")
        light = [set(re.findall(r"(--[\w-]+)\s*:", b)) for b in blocks[1:]]
        self.assertEqual(light[0], light[1], "the two light selectors have drifted apart")
        # every colour role the light theme overrides must exist in :root
        root = set(re.findall(r"(--[\w-]+)\s*:", blocks[0]))
        self.assertTrue(light[0] <= root, f"light-only tokens: {sorted(light[0] - root)}")

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

    def test_design_tokens_lint_clean(self) -> None:
        """Run the drift guard in-process so it is enforced without CI."""
        result = subprocess.run(
            [sys.executable, str(APP_DIR / "scripts" / "lint_design_tokens.py"), "--strict"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

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
