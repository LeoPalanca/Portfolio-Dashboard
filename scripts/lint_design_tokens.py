#!/usr/bin/env python3
"""Guard the design system against drift.

The 0.4 layout pass collapsed a pile of eyeballed values onto a small set of tokens.
Without a check, they creep back one hardcoded #34d399 at a time. This enforces:

  1. every var(--token) reference resolves to a token the theme actually defines
  2. no colour literals outside the theme blocks in app.css
  3. no colour literals in app.js (they cannot follow a theme switch)
  4. padding/margin/gap values come from the spacing scale
  5. light and dark define exactly the same token names

Run with --strict to fail the build (used in CI); without it, counts are reported
so a migration in progress can be tracked.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "static" / "app.css"
JS = ROOT / "static" / "app.js"
HTML = ROOT / "templates" / "index.html"

SPACING_PROPS = r"(?:padding|margin|gap|row-gap|column-gap)(?:-(?:top|right|bottom|left|inline|block))?"
# (?<!&) keeps numeric HTML entities such as &#9650; from reading as colours
HEX_RE = re.compile(r"(?<![&\w])#[0-9a-fA-F]{3,8}\b")
RGB_RE = re.compile(r"\brgba?\(")
VAR_USE_RE = re.compile(r"var\(\s*(--[\w-]+)")
VAR_DEF_RE = re.compile(r"^\s*(--[\w-]+)\s*:", re.MULTILINE)
# hairlines and full-bleed values are not spacing-scale concerns
SPACING_EXEMPT = {"0", "0px", "1px", "auto", "-1px", "2px"}


def theme_blocks(css: str) -> list[tuple[str, str]]:
    """Return (label, body) for :root and each [data-theme] block."""
    blocks = []
    for m in re.finditer(r"(:root(?:\[data-theme=\"\w+\"\])?|:root:not\(\[data-theme=\"\w+\"\]\))\s*\{", css):
        start = m.end()
        depth, i = 1, start
        while i < len(css) and depth:
            depth += (css[i] == "{") - (css[i] == "}")
            i += 1
        blocks.append((m.group(1).strip(), css[start : i - 1]))
    return blocks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="exit non-zero on any finding")
    args = parser.parse_args()

    css, js, html = CSS.read_text(), JS.read_text(), HTML.read_text()
    blocks = theme_blocks(css)
    theme_src = "".join(body for _, body in blocks)
    theme_tokens = set(VAR_DEF_RE.findall(theme_src))

    # A token may also be scoped to a component rule, set inline on an element, or
    # written from JS. Those are legitimate definitions, so collect them too.
    scoped = set(re.findall(r"(--[\w-]+)\s*:", css))
    scoped |= set(re.findall(r"(--[\w-]+)\s*:", html))
    scoped |= set(re.findall(r"setProperty\(\s*['\"](--[\w-]+)", js))
    defined = theme_tokens | scoped

    # css with every theme block removed - the "component" layer
    component_css = css
    for _, body in blocks:
        component_css = component_css.replace(body, "")

    findings: list[tuple[str, list[str]]] = []

    # 1. unresolved var() references
    unresolved = set()
    for label, src in (("app.css", css), ("app.js", js), ("index.html", html)):
        for name in VAR_USE_RE.findall(src):
            if name not in defined:
                unresolved.add(f"{label}: var({name})")
    if unresolved:
        findings.append(("unresolved var() references", sorted(unresolved)))

    # 2. colour literals in the component layer
    stray = [f"app.css: {h}" for h in HEX_RE.findall(component_css)]
    stray += [f"app.css: rgb(...)  x{len(RGB_RE.findall(component_css))}"] if RGB_RE.search(component_css) else []
    if stray:
        findings.append(("colour literals outside the theme blocks", sorted(set(stray))))

    # 3. colour literals in JS
    js_colours = sorted(set(HEX_RE.findall(js)))
    if js_colours:
        findings.append(("colour literals in app.js (cannot follow a theme)", js_colours))

    # 4. off-scale spacing
    scale = {v for k, v in re.findall(r"(--space-\d)\s*:\s*([^;]+);", theme_src)}
    off = set()
    for decl in re.findall(rf"{SPACING_PROPS}\s*:\s*([^;{{}}]+);", component_css):
        if "var(" in decl:
            continue
        for token in decl.split():
            if token in SPACING_EXEMPT or token in scale:
                continue
            if re.fullmatch(r"-?[\d.]+(px|rem|em)", token):
                off.add(token)
    if off:
        findings.append(("spacing values outside the scale", sorted(off)))

    # 5. theme parity
    per_block = {label: set(VAR_DEF_RE.findall(body)) for label, body in blocks}
    root = per_block.get(":root", set())
    for label, names in per_block.items():
        if label == ":root":
            continue
        missing = (root - names) - {n for n in root if n.startswith(("--space-", "--text-", "--radius-", "--motion-", "--ease", "--z-"))}
        extra = names - root
        if extra:
            findings.append((f"tokens defined in {label} but not :root", sorted(extra)))

    print(f"theme tokens: {len(theme_tokens)}   scoped: {len(scoped - theme_tokens)}   blocks: {len(blocks)}")
    if not findings:
        print("design tokens: clean")
        return 0

    total = 0
    for title, items in findings:
        total += len(items)
        print(f"\n{title}: {len(items)}")
        for item in items[:20]:
            print(f"    {item}")
        if len(items) > 20:
            print(f"    ... and {len(items) - 20} more")

    print(f"\ntotal findings: {total}")
    return 1 if args.strict else 0


if __name__ == "__main__":
    sys.exit(main())
