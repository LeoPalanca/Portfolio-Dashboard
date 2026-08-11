"""Every foreground token must clear WCAG AA against both surfaces, in every theme.

Body copy in this dashboard sits at 11-13px, so the 3:1 large-text allowance does
not apply anywhere: the bar is 4.5:1 throughout.

This is a calculation, not a substitute for looking at the page. It catches a
token that is unreadable; it will not catch one that is merely ugly.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

CSS = Path(__file__).resolve().parent / "static" / "app.css"
AA_NORMAL = 4.5

FOREGROUNDS = (
    "--text-primary",
    "--text-secondary",
    "--text-muted",
    "--accent",
    "--positive",
    "--negative",
    "--warning",
    "--series-teal",
    "--series-violet",
    "--series-cyan",
    "--series-pink",
)
SURFACES = ("--surface-page", "--surface-panel")


def _srgb(hex_colour: str) -> tuple[float, float, float]:
    raw = hex_colour.lstrip("#")
    if len(raw) == 3:
        raw = "".join(c * 2 for c in raw)
    return tuple(int(raw[i : i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def relative_luminance(hex_colour: str) -> float:
    def channel(value: float) -> float:
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(v) for v in _srgb(hex_colour))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    la, lb = relative_luminance(a), relative_luminance(b)
    high, low = max(la, lb), min(la, lb)
    return (high + 0.05) / (low + 0.05)


def block(selector: str, css: str) -> dict[str, str]:
    """Hex declarations from the rule with exactly this selector.

    Brace-matches rather than regex-matching a whole rule, so a selector nested
    inside an @media wrapper is found the same as a top-level one.
    """
    pattern = re.compile(re.escape(selector) + r"\s*\{")
    for m in pattern.finditer(css):
        # reject a descendant selector that merely starts with the one we want
        preceding = css[: m.start()].rstrip()
        if preceding and preceding[-1] not in "{}*/;":
            continue
        depth, i = 1, m.end()
        while i < len(css) and depth:
            depth += (css[i] == "{") - (css[i] == "}")
            i += 1
        body = css[m.end() : i - 1]
        return dict(re.findall(r"(--[\w-]+)\s*:\s*(#[0-9a-fA-F]{3,8})\s*;", body))
    raise AssertionError(f"no rule for {selector!r}")


class ThemeContrastTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.css = CSS.read_text()
        dark = block(":root", cls.css)
        light = {**dark, **block(':root[data-theme="light"]', cls.css)}
        dark_cb = {**dark, **block(':root[data-palette="cb"]', cls.css)}
        light_cb = {**light, **block(':root[data-palette="cb"][data-theme="light"]', cls.css)}
        cls.themes = {
            "dark": dark,
            "light": light,
            "dark + colour-blind": dark_cb,
            "light + colour-blind": light_cb,
        }

    def test_every_foreground_clears_aa_on_every_surface(self) -> None:
        failures = []
        for theme_name, tokens in self.themes.items():
            for surface in SURFACES:
                bg = tokens.get(surface)
                self.assertIsNotNone(bg, f"{theme_name} has no {surface}")
                for fg_name in FOREGROUNDS:
                    fg = tokens.get(fg_name)
                    if fg is None:
                        continue
                    ratio = contrast(fg, bg)
                    if ratio < AA_NORMAL:
                        failures.append(
                            f"{theme_name}: {fg_name} {fg} on {surface} {bg} = {ratio:.2f}"
                        )
        self.assertEqual(failures, [], "\n".join(failures))

    def test_gain_and_loss_are_different_colours(self) -> None:
        for theme_name, tokens in self.themes.items():
            self.assertNotEqual(tokens["--positive"], tokens["--negative"], theme_name)

    def test_gain_and_loss_are_near_equiluminant_so_the_sign_matters(self) -> None:
        """Documents a real limitation rather than pretending it is fixed.

        Both palettes pair colours of near-identical luminance (ratio well under
        2:1), so in greyscale - or for an achromat - the two are indistinguishable
        by colour alone. The mitigation is the +/- sign and arrow glyph on every
        figure, which is why those must never be removed in favour of colour.
        """
        for theme_name, tokens in self.themes.items():
            ratio = contrast(tokens["--positive"], tokens["--negative"])
            self.assertLess(
                ratio, 2.0,
                f"{theme_name}: luminance ratio is {ratio:.2f}. If this now exceeds 2:1 the "
                "palette has changed enough that this note should be revisited.",
            )

    def test_colour_blind_palette_avoids_the_red_green_axis(self) -> None:
        """The whole point of the opt-in palette is dropping red vs green."""
        for theme_name in ("dark + colour-blind", "light + colour-blind"):
            tokens = self.themes[theme_name]
            pos_r, pos_g, pos_b = _srgb(tokens["--positive"])
            neg_r, neg_g, neg_b = _srgb(tokens["--negative"])
            # gain leans blue, loss leans red/orange - the axis deuteranopia preserves
            self.assertGreater(pos_b, pos_r, f"{theme_name}: --positive should lean blue")
            self.assertGreater(neg_r, neg_b, f"{theme_name}: --negative should lean warm")

    def test_both_light_selectors_are_identical(self) -> None:
        """The media query and the attribute selector must not drift apart."""
        media = block(':root[data-palette="cb"]:not([data-theme="dark"])', self.css)
        explicit = block(':root[data-palette="cb"][data-theme="light"]', self.css)
        self.assertEqual(media, explicit)


if __name__ == "__main__":
    unittest.main()
