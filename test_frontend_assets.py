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
        self.assertEqual(config["appVersion"], app.DISPLAY_VERSION)
        self.assertEqual(config["defaultProxyMode"], app.DEFAULT_PROXY_MODE)
        self.assertEqual(config["hasMultiplePortfolios"], len(app.SETTINGS.portfolios) > 0)
        self.assertEqual(config["annualRiskFreeRate"], app.SETTINGS.annual_risk_free_rate)

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

    def test_display_settings_menu_is_present_and_labelled(self) -> None:
        html = render()
        self.assertIn('id="settings-toggle"', html)
        self.assertIn('id="settings-menu"', html)
        # the control must say what it does; an unlabelled icon does not
        self.assertIn('aria-label="Display settings"', html)
        self.assertIn('aria-haspopup="true"', html)
        self.assertIn('role="radiogroup"', html)
        for choice in ("light", "dark", "system"):
            self.assertIn(f'data-theme-choice="{choice}"', html)
        self.assertIn('id="setting-colourblind"', html)

    def test_system_theme_is_reachable(self) -> None:
        """The two-state toggle this replaced had no way back to 'follow the OS'.

        'System' is the absence of an override, so choosing it must clear both the
        attribute and the stored value rather than writing a third one.
        """
        with app.app.test_client() as client:
            js = client.get("/static/app.js").get_data(as_text=True)

        self.assertIn('if (choice === "system")', js)
        self.assertIn('root.removeAttribute("data-theme")', js)
        self.assertIn("storeValue(THEME_KEY, null)", js)

    def test_settings_menu_closes_on_escape_and_outside_click(self) -> None:
        with app.app.test_client() as client:
            js = client.get("/static/app.js").get_data(as_text=True)

        self.assertIn('event.key === "Escape"', js)
        self.assertIn('document.addEventListener("click", () => setSettingsOpen(false))', js)

    def test_rankings_do_not_block_the_main_dashboard_render(self) -> None:
        with app.app.test_client() as client:
            js = client.get("/static/app.js").get_data(as_text=True)

        load_start = js.index("async function load(refresh")
        load_end = js.index('document.querySelectorAll("#periods button")', load_start)
        load_body = js[load_start:load_end]
        self.assertIn("renderDashboard(data);", load_body)
        self.assertIn("void loadRankings(params, requestId);", load_body)
        self.assertNotIn("Promise.all", load_body)

    def test_every_section_has_a_stable_key(self) -> None:
        """Section preferences are stored by key, so every section needs one."""
        html = render()
        main = html[html.index("<main>") : html.index("</main>")]
        sections = re.findall(r"<section\b([^>]*)>", main)
        self.assertTrue(sections)
        without_key = [s for s in sections if "data-section=" not in s]
        self.assertEqual(without_key, [], "sections cannot be reordered without a key")
        keys = re.findall(r'data-section="([^"]+)"', main)
        self.assertEqual(len(keys), len(set(keys)), "duplicate section keys")

    def test_section_preferences_survive_an_unknown_key(self) -> None:
        """A stored preference from an older build must not drop or duplicate sections."""
        with app.app.test_client() as client:
            js = client.get("/static/app.js").get_data(as_text=True)

        # unknown keys are filtered against the current DOM...
        self.assertIn("if (known.has(key) && !order.includes(key)) order.push(key);", js)
        # ...and newly added sections fall back to their default position
        self.assertIn(
            "DEFAULT_ORDER.forEach((key) => { if (!order.includes(key)) order.push(key); });", js
        )

    def test_user_hidden_sections_use_their_own_attribute(self) -> None:
        """Must not reuse .is-hidden, which the app itself drives."""
        with app.app.test_client() as client:
            js = client.get("/static/app.js").get_data(as_text=True)
            css = client.get("/static/app.css").get_data(as_text=True)

        self.assertIn('setAttribute("data-section-off", "")', js)
        self.assertIn("[data-section-off]", css)
        self.assertNotIn('classList.add("is-hidden")', js)

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
