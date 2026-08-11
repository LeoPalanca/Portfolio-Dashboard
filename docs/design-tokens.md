# Design Tokens

**Shipped in 0.4.** This began as the specification for the layout pass and now documents the
system as built. The migration tables are kept because they explain *why* each value is what
it is.

0.4 was a **consistency** release, not a visual redesign: eyeballed values were replaced with
scale values and a light theme was added. Dark mode is visually unchanged apart from one
contrast fix. The aesthetic redesign comes after.

---

## Results

Starting point was `app.py:7594` — a 270,657-char inline frontend (1,987 CSS lines / 386 rules,
3,239 JS lines, 952 markup lines) inside a Python string literal.

| Dimension | Before | After |
| --- | --- | --- |
| Frontend location | one string literal in `app.py` | `templates/` + `static/` |
| `app.py` | 13,773 lines | 7,599 lines |
| Spacing | 23 literals (214 uses) | 7 scale tokens (+ `1px`/`2px` hairlines) |
| Font size | 12 values | 7 steps |
| Border radius | 11 values | 4 tokens |
| Box shadow | 28 bespoke | 4 elevation tiers |
| Transition | 11 durations | 3 tokens, 2 easings |
| Colour literals in JS | 16 hex + 30 rgba | 0 |
| Colour literals in CSS body | 32 hex + 187 rgba | 0 |
| z-index | 5 arbitrary | 5 named |
| Themes | dark only | dark + light, OS-aware, toggleable |

Enforced by `scripts/lint_design_tokens.py --strict`, which runs in CI and as a test.

Two defects fixed along the way:

- **`--text-sub` was a ghost token** — used 8× as `var(--text-sub, #94a3b8)` and never defined,
  so the fallback always won and `#94a3b8` acted as an undocumented third grey.
- **`color: var(--ink;)`** in the subcategory table — a stray semicolon inside the parentheses
  made it invalid CSS, so that colour had never applied. Found by the linter.

And **`--muted #64748b` failed WCAG AA** (4.02:1 on `--bg`, 3.73:1 on `--panel-solid`) at
11–12px. Now `#7c8ba1` at 5.52:1.

Six tokens were defined and never referenced, and are gone: `--glass`, `--pink-dim`,
`--violet-dim`, `--gradient-1`, `--gradient-2`, `--gradient-3`.

---

## Architecture

Two tiers. Component CSS may **only** reference tier 2.

1. **Theme block** — `:root` (dark, default) and `:root[data-theme="light"]`. The only place
   a literal colour may appear.
2. **Semantic roles** — what a colour *means* (`--positive`, `--negative`, `--accent`), not
   what it looks like. A finance dashboard should never say "green" in a stylesheet; it should
   say "gain".

Hue-named aliases (`--blue`, `--green`, …) existed during the migration so the 386 existing
rules kept working while call sites moved one commit at a time. All 253 have since been
migrated and the aliases are gone.

### Theme switching

Dark stays the default. Light responds to the OS and to an explicit toggle, with the toggle
winning in both directions:

```css
:root { /* dark tokens */ }

@media (prefers-color-scheme: light) {
  :root:not([data-theme="dark"]) { /* light tokens */ }
}

:root[data-theme="light"] { /* light tokens */ }
```

Persist the choice in `localStorage` and set `data-theme` on `<html>` before first paint to
avoid a flash.

---

## Colour

All values verified with the WCAG relative-luminance formula. Ratios shown are against page
background / panel background. Bar is **4.5:1** — body copy here is 11–13px, so the 3:1
large-text allowance does not apply.

### Dark (default)

| Token | Value | Contrast | Role |
| --- | --- | --- | --- |
| `--surface-page` | `#0c0f1a` | — | app background |
| `--surface-panel` | `#111827` | — | cards, tables |
| `--surface-raised` | `#1e293b` | — | hover, popovers |
| `--text-primary` | `#f1f5f9` | 17.44 / 16.19 | headings, figures |
| `--text-secondary` | `#cbd5e1` | 12.87 / 11.95 | body |
| `--text-muted` | **`#7c8ba1`** | **5.52 / 5.12** | labels, captions |
| `--border` | `rgba(148,163,184,0.12)` | — | hairlines |
| `--border-strong` | `rgba(148,163,184,0.20)` | — | dividers, inputs |
| `--accent` | `#60a5fa` | 7.52 / 6.98 | interactive, primary series |
| `--positive` | `#34d399` | 9.94 / 9.23 | gains |
| `--negative` | `#f87171` | 6.91 / 6.41 | losses |
| `--warning` | `#fbbf24` | 11.45 / 10.63 | stale data, partial sources |
| `--series-teal` | `#2dd4bf` | 10.27 / 9.53 | chart series |
| `--series-violet` | `#a78bfa` | 7.02 / 6.52 | chart series |
| `--series-cyan` | `#22d3ee` | 10.57 / 9.82 | chart series |
| `--series-pink` | `#f472b6` | 7.22 / 6.70 | chart series |

`--text-muted` is the only changed value: `#64748b` → `#7c8ba1`, which lifts it from a failing
4.02 to a passing 5.52. Everything else is your existing palette, unmodified.

### Light

| Token | Value | Contrast | Note |
| --- | --- | --- | --- |
| `--surface-page` | `#f7f8fa` | — | |
| `--surface-panel` | `#ffffff` | — | |
| `--surface-raised` | `#f1f5f9` | — | |
| `--text-primary` | `#0f172a` | 17.85 / 16.80 | |
| `--text-secondary` | `#334155` | 10.35 / 9.74 | |
| `--text-muted` | `#5b6878` | 5.68 / 5.35 | |
| `--border` | `rgba(15,23,42,0.10)` | — | |
| `--border-strong` | `rgba(15,23,42,0.18)` | — | |
| `--accent` | `#2563eb` | 5.17 / 4.86 | |
| `--positive` | `#047857` | 5.48 / 5.16 | |
| `--negative` | `#dc2626` | 4.83 / 4.54 | |
| `--warning` | `#b45309` | 5.02 / 4.73 | amber must darken hard on white |
| `--series-teal` | `#0f766e` | 5.47 / 5.15 | |
| `--series-violet` | `#6d28d9` | 7.10 / 6.69 | |
| `--series-cyan` | `#0e7490` | 5.36 / 5.04 | |
| `--series-pink` | `#be185d` | 6.04 / 5.68 | |

**Useful accident:** most of the light palette is already in your codebase. The off-system
values that drifted in — `#2563eb`, `#059669`, `#dc2626`-adjacent `#ef4444`, `#7c3aed`,
`#0e7490`-adjacent `#0ea5e9` — are the darker Tailwind 600/700 shades, which is exactly what a
light theme needs. The drift was half a light theme waiting to be named.

### Dim variants

Both themes need translucent fills for badges and chart bands. Derive them, do not hand-pick:

```css
--accent-dim:   color-mix(in srgb, var(--accent)   15%, transparent);
--positive-dim: color-mix(in srgb, var(--positive) 12%, transparent);
--negative-dim: color-mix(in srgb, var(--negative) 12%, transparent);
--warning-dim:  color-mix(in srgb, var(--warning)  12%, transparent);
```

This replaces the eight hand-written `*-dim` tokens and makes them track the theme
automatically.

### Colour-blindness

Gain/loss is the primary semantic pair and red/green is the worst possible choice for the
~8% of men with deuteranopia. Colour must never be the only signal: keep the explicit `+`/`−`
sign and the arrow glyph on every figure. Worth adding later as a config flag — a
blue/amber alternative pair reusing `--accent` and `--warning`.

### Migration map — every off-system colour

Delete the literal, use the token. Grouped by hue family.

| Current | Count | Replace with |
| --- | --- | --- |
| `#94a3b8` (the `--text-sub` fallback) | 9 | `--text-muted` |
| `#1e293b` | 3 | `--surface-raised` |
| `#475569`, `#334155`, `#0f172a` | 4 | `--surface-raised` / `--border-strong` |
| `#2563eb`, `#1d4ed8`, `#1455d9` | 3 | `--accent` |
| `#10b981`, `#059669`, `#16a34a`, `#22c55e`, `#84cc16` | 6 | `--positive` |
| `#ef4444` | 3 | `--negative` |
| `#f59e0b`, `#facc15`, `#f97316` | 6 | `--warning` |
| `#14b8a6`, `#06b6d4`, `#0ea5e9` | 3 | `--series-teal` / `--series-cyan` |
| `#8b5cf6`, `#7c3aed` | 2 | `--series-violet` |
| `#db2777` | 1 | `--series-pink` |
| `#ffffff` / `#fff` | 12 | `--text-primary` (never a raw white in light mode) |

Six greens for one concept is the clearest evidence of drift; that row alone is worth the pass.

### JS chart palettes

`app.py` hardcodes series colours in JS arrays:

```js
blue:  ["#60a5fa", "rgba(96,165,250,0.09)"]
green: ["#34d399", "rgba(52,211,153,0.08)"]
```

These break the moment a theme switches. Read them from CSS at runtime instead:

```js
const token = (name) =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const SERIES = ["--accent", "--positive", "--warning", "--series-violet",
                "--series-teal", "--series-pink"].map(token);
```

Re-read on theme change and redraw.

---

## Spacing

4px base. Seven steps absorb all 214 current uses.

| Token | Value | Replaces |
| --- | --- | --- |
| `--space-1` | `4px` | 1, 2, 3, 4, 5 |
| `--space-2` | `8px` | 6, 7, 8, 9 |
| `--space-3` | `12px` | 10, 11, 12, 13 |
| `--space-4` | `16px` | 14, 15, 16, 18 |
| `--space-5` | `24px` | 20, 22, 24 |
| `--space-6` | `32px` | 32, 36 |
| `--space-7` | `48px` | 48 |

Largest single shift is 18px → 16px (17 uses) and 20px → 24px (8 uses). Everything else moves
by ≤2px. `1px` stays literal where it is a hairline, not spacing.

## Type

Inter is already loaded. Seven sizes, and lift the floor — 9px and 10px text is below
comfortable reading for a data-dense financial UI.

| Token | Value | Replaces | Use |
| --- | --- | --- | --- |
| `--text-2xs` | `10px` | 9, 10 | dense table meta only |
| `--text-xs` | `11px` | 11 | labels, chart axes |
| `--text-sm` | `12px` | 12 | table body |
| `--text-base` | `13px` | 13, 14 | body copy |
| `--text-lg` | `16px` | 15, 16 | card figures |
| `--text-xl` | `19px` | 18, 19, 20 | section headings |
| `--text-2xl` | `22px` | 22 | page total |

Weights: `400 / 500 / 600 / 700`. Drop `800` (5 uses → 700) and the one-off `750`.

Add tabular figures globally — non-negotiable for a dashboard where columns of numbers must
align:

```css
font-variant-numeric: tabular-nums;
```

## Radius

| Token | Value | Replaces |
| --- | --- | --- |
| `--radius-sm` | `8px` | 7, 8, 9 |
| `--radius-md` | `10px` | 10, 11 |
| `--radius-lg` | `14px` | 12, 14 |
| `--radius-pill` | `999px` | 999px (22 uses, unchanged) |

## Elevation

Four steps replace 20 bespoke shadows. Both themes need their own — a black-alpha shadow that
reads as depth on `#0c0f1a` reads as dirt on `#ffffff`.

| Token | Dark | Light |
| --- | --- | --- |
| `--elev-0` | `none` | `none` |
| `--elev-1` | `0 1px 3px rgba(0,0,0,0.30), inset 0 1px 0 rgba(255,255,255,0.04)` | `0 1px 2px rgba(15,23,42,0.06)` |
| `--elev-2` | `0 8px 20px rgba(0,0,0,0.22), inset 0 1px 0 rgba(255,255,255,0.06)` | `0 4px 12px rgba(15,23,42,0.08)` |
| `--elev-3` | `0 12px 32px rgba(0,0,0,0.28), inset 0 1px 0 rgba(255,255,255,0.08)` | `0 12px 28px rgba(15,23,42,0.12)` |
| `--elev-glow` | `0 0 20px var(--accent-dim)` | `0 0 0 3px var(--accent-dim)` |

The six near-identical card shadows (`0 12px 34px`, `0 10px 24px`, `0 9px 20px`, `0 8px 20px`,
`0 8px 18px`) all collapse to `--elev-2`.

## Motion

Three durations, two easings. Replaces 21 distinct transitions across nine durations.

| Token | Value | Use |
| --- | --- | --- |
| `--motion-fast` | `120ms` | colour, opacity, hover |
| `--motion-base` | `200ms` | transform, shadow, borders |
| `--motion-slow` | `360ms` | expand/collapse, layout |
| `--ease` | `cubic-bezier(0.4, 0, 0.2, 1)` | default |
| `--ease-out` | `cubic-bezier(0, 0, 0.2, 1)` | entrances |

Never `transition: all` (currently 2 uses) — it animates properties you did not intend and
forces needless style recalculation. The existing `prefers-reduced-motion` block already
handles the accessibility case; keep it and extend it to zero out these tokens.

## z-index

Replaces `1, 5, 90, 100, 1200`.

| Token | Value | Use |
| --- | --- | --- |
| `--z-base` | `1` | in-flow stacking |
| `--z-sticky` | `10` | sticky table headers |
| `--z-header` | `100` | top bar |
| `--z-overlay` | `500` | refresh scrim |
| `--z-modal` | `1000` | dialogs, import onboarding |

---
## The theme block

The live definitions are in [`static/app.css`](../static/app.css) — `:root` for dark, then the
same light values under both `@media (prefers-color-scheme: light) :root:not([data-theme="dark"])`
and `:root[data-theme="light"]` so an explicit choice wins in either direction. The duplication
is deliberate: plain CSS has no way to share one declaration block between a media query and an
attribute selector, and a test asserts the two copies never drift apart.

Alongside the themed roles sit two deliberately **theme-invariant** groups:

- `--brand-*` — broker marks. Trade Republic is white and Fineco is yellow in light mode too,
  so these are literals on purpose and the linter exempts them.
- the scales (`--space-*`, `--text-*`, `--radius-*`, `--motion-*`, `--z-*`) — geometry and
  timing do not change with colour.

## How it was done

Each step was a separate commit, individually revertible, with the suite green throughout:

1. `6562cdc` extract the frontend out of `app.py` — verified byte-identical
2. `a645abb` two-tier theme system + light mode + the linter
3. `bc8ff52` presentation out of JS and inline attributes
4. `17a4ffd` collapse the scales (389 replacements)
5. `f582731` theme toggle
6. `63fcc01` retire the legacy aliases (253 call sites)

`el.style.display` was deliberately left in JavaScript. Those 32 assignments are component
state, not theming, and converting them would add risk without serving the goal.

## Guardrails

`scripts/lint_design_tokens.py` fails the build on:

1. a `var(--token)` reference that resolves to nothing — this is what caught `--text-sub`
   and the malformed `var(--ink;)`
2. colour literals outside the theme blocks in `app.css`
3. any colour literal in `app.js`, since it cannot follow a theme switch
4. `padding`/`margin`/`gap` values off the spacing scale
5. the two light selectors drifting apart

It runs in `.github/workflows/ci.yml` on Python 3.11/3.12/3.13 and again as a pytest case, so
it is enforced even outside CI.

## Still open

- **Contrast is verified by calculation, not by eye.** Someone should look at light mode on a
  real screen — chart tooltips, table hover states and the refresh overlay are the likely misses.
- **34 inline `style=` attributes remain in the markup and 93 in JS templates.** They no longer
  contain colour, so they do not block theming, but they are still presentation in the wrong
  place. Mostly one-off layout blocks that deserve named classes.
- **`color-mix()` needs Safari 16.2+ / Chrome 111+ / Firefox 113+.** Fine for a local dashboard;
  worth noting if this is ever embedded somewhere older.
- **The colour-blind alternative is not built.** Gain/loss still relies on red/green plus the
  `+`/`−` sign. A blue/amber pair reusing `--accent` and `--warning` would be the fix.
