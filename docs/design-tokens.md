# Design Tokens

**Target release: 0.4 (layout)** — current shipped version is 0.3.1.

This is the specification for the 0.4 layout pass. It defines the token system, the light and
dark themes, and the exact mapping from every off-system value currently in the codebase to
its replacement.

Scope note: 0.4 is a **consistency** release, not a visual redesign. Applied correctly, the
mappings below change almost nothing visually in dark mode — they replace eyeballed values
with scale values and add a light theme. The actual aesthetic redesign comes after.

---

## Current state

Measured against `app.py:7594` (the 270,657-char inline frontend: 1,987 CSS lines / 386 rules,
3,239 JS lines, 952 markup lines).

| Dimension | Distinct values today | Target |
| --- | --- | --- |
| Spacing | 23 (of 214 uses) | 7 |
| Font size | 12 | 7 |
| Border radius | 11 | 4 |
| Box shadow | 20 (of 30 uses) | 4 |
| Transition | 21 (9 durations) | 3 durations, 2 easings |
| Hex colours | 32 across CSS/JS/markup | 0 outside the theme blocks |
| z-index | 5 unscaled (1, 5, 90, 100, 1200) | 5 named |

Two defects to fix while we are here:

- **`--text-sub` is a ghost token.** Used 8× as `var(--text-sub, #94a3b8)` — 7 in JS, 1 in
  markup — and never defined. The fallback always wins, so `#94a3b8` renders as an
  undocumented third secondary-text grey alongside `--ink-secondary` and `--muted`.
- **`--muted #64748b` fails WCAG AA**: 4.02:1 on `--bg`, 3.73:1 on `--panel-solid`, and it is
  used for 11–12px label text. Fixed below.

Six tokens are defined and never referenced — delete them: `--glass`, `--pink-dim`,
`--violet-dim`, `--gradient-1`, `--gradient-2`, `--gradient-3`.

---

## Architecture

Two tiers. Component CSS may **only** reference tier 2.

1. **Theme block** — `:root` (dark, default) and `:root[data-theme="light"]`. The only place
   a literal colour may appear.
2. **Semantic roles** — what a colour *means* (`--positive`, `--negative`, `--accent`), not
   what it looks like. A finance dashboard should never say "green" in a stylesheet; it should
   say "gain".

Hue-named legacy aliases (`--blue`, `--green`, …) are kept as pointers to the semantic roles
so the 386 existing rules keep working during migration. They get deleted once call sites move.

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

## Ready-to-paste theme block

Replaces the current `:root` block wholesale.

```css
:root {
  /* ---- surfaces ---- */
  --surface-page:    #0c0f1a;
  --surface-panel:   #111827;
  --surface-raised:  #1e293b;
  --surface-overlay: rgba(17, 24, 39, 0.70);

  /* ---- text ---- */
  --text-primary:   #f1f5f9;
  --text-secondary: #cbd5e1;
  --text-muted:     #7c8ba1;

  /* ---- borders ---- */
  --border:        rgba(148, 163, 184, 0.12);
  --border-strong: rgba(148, 163, 184, 0.20);

  /* ---- semantic ---- */
  --accent:   #60a5fa;
  --positive: #34d399;
  --negative: #f87171;
  --warning:  #fbbf24;

  /* ---- chart series ---- */
  --series-teal:   #2dd4bf;
  --series-violet: #a78bfa;
  --series-cyan:   #22d3ee;
  --series-pink:   #f472b6;

  /* ---- derived fills ---- */
  --accent-dim:   color-mix(in srgb, var(--accent)   15%, transparent);
  --positive-dim: color-mix(in srgb, var(--positive) 12%, transparent);
  --negative-dim: color-mix(in srgb, var(--negative) 12%, transparent);
  --warning-dim:  color-mix(in srgb, var(--warning)  12%, transparent);

  /* ---- elevation ---- */
  --elev-0: none;
  --elev-1: 0 1px 3px rgba(0,0,0,0.30), inset 0 1px 0 rgba(255,255,255,0.04);
  --elev-2: 0 8px 20px rgba(0,0,0,0.22), inset 0 1px 0 rgba(255,255,255,0.06);
  --elev-3: 0 12px 32px rgba(0,0,0,0.28), inset 0 1px 0 rgba(255,255,255,0.08);
  --elev-glow: 0 0 20px var(--accent-dim);

  /* ---- scales (theme-invariant) ---- */
  --space-1: 4px;  --space-2: 8px;  --space-3: 12px; --space-4: 16px;
  --space-5: 24px; --space-6: 32px; --space-7: 48px;

  --text-2xs: 10px; --text-xs: 11px; --text-sm: 12px; --text-base: 13px;
  --text-lg: 16px;  --text-xl: 19px; --text-2xl: 22px;

  --radius-sm: 8px; --radius-md: 10px; --radius-lg: 14px; --radius-pill: 999px;

  --motion-fast: 120ms; --motion-base: 200ms; --motion-slow: 360ms;
  --ease:     cubic-bezier(0.4, 0, 0.2, 1);
  --ease-out: cubic-bezier(0, 0, 0.2, 1);

  --z-base: 1; --z-sticky: 10; --z-header: 100; --z-overlay: 500; --z-modal: 1000;

  /* ---- legacy aliases: delete as call sites migrate ---- */
  --bg: var(--surface-page);
  --bg-secondary: var(--surface-panel);
  --panel: var(--surface-overlay);
  --panel-solid: var(--surface-panel);
  --panel-hover: var(--surface-raised);
  --ink: var(--text-primary);
  --ink-secondary: var(--text-secondary);
  --muted: var(--text-muted);
  --text-sub: var(--text-muted);        /* was the undefined ghost token */
  --line: var(--border);
  --line-strong: var(--border-strong);
  --blue: var(--accent);
  --green: var(--positive);
  --red: var(--negative);
  --amber: var(--warning);
  --teal: var(--series-teal);
  --violet: var(--series-violet);
  --cyan: var(--series-cyan);
  --pink: var(--series-pink);
  --blue-dim: var(--accent-dim);
  --green-dim: var(--positive-dim);
  --red-dim: var(--negative-dim);
  --amber-dim: var(--warning-dim);
  --shadow: var(--elev-2);
  --shadow-lg: var(--elev-3);
  --shadow-glow: var(--elev-glow);
  --radius: var(--radius-lg);
}

/* Light theme — OS preference, unless explicitly overridden to dark */
@media (prefers-color-scheme: light) {
  :root:not([data-theme="dark"]) { /* @import light-values */ }
}
/* Light theme — explicit toggle, wins in both directions */
:root[data-theme="light"] { /* @import light-values */ }
```

Both light selectors carry the same declarations:

```css
  --surface-page:    #f7f8fa;
  --surface-panel:   #ffffff;
  --surface-raised:  #f1f5f9;
  --surface-overlay: rgba(255, 255, 255, 0.80);

  --text-primary:   #0f172a;
  --text-secondary: #334155;
  --text-muted:     #5b6878;

  --border:        rgba(15, 23, 42, 0.10);
  --border-strong: rgba(15, 23, 42, 0.18);

  --accent:   #2563eb;
  --positive: #047857;
  --negative: #dc2626;
  --warning:  #b45309;

  --series-teal:   #0f766e;
  --series-violet: #6d28d9;
  --series-cyan:   #0e7490;
  --series-pink:   #be185d;

  --elev-1: 0 1px 2px rgba(15,23,42,0.06);
  --elev-2: 0 4px 12px rgba(15,23,42,0.08);
  --elev-3: 0 12px 28px rgba(15,23,42,0.12);
  --elev-glow: 0 0 0 3px var(--accent-dim);
```

The `--gradient-accent` token needs a light variant too; the other three gradients are unused
and get deleted.

---

## Execution order for 0.4

The frontend is still a single string literal at `app.py:7594`, and **262 inline-style
touchpoints** (69 in markup, 128 in JS template strings, 64 `el.style.x =` assignments) mean
presentation currently lives in JavaScript. You cannot theme what is hardcoded in a template
string, so extraction has to come first.

1. **Extract** the literal to `static/app.css`, `static/app.js`, `templates/index.html`.
   Pure move, zero behaviour change. This is also the last big piece of the backend
   restructure Codex has been running.
2. **Land the theme block** with all legacy aliases intact. Nothing else changes; the app
   should look identical. Only `--text-muted` shifts, and only to fix the contrast failure.
3. **De-inline presentation.** Move the 128 JS-template and 69 markup `style="` attributes to
   classes. Keep `el.style.display` (32 uses) or convert to `classList` — you already use
   `classList` 29 times, so the pattern exists.
4. **Sweep the scales** — spacing, radius, type, shadow, motion — using the mapping tables.
   Mechanical, and each is independently verifiable by screenshot diff.
5. **Add the theme toggle** and the runtime chart-palette reader.
6. **Delete the legacy aliases** and the six dead tokens.

Steps 2–6 are individually revertible. Do not batch them into one commit.

## Guardrails

Add a CI check so drift cannot return — this is the part that makes the system hold:

- Fail if any hex literal appears in `static/app.css` outside the `:root` / `[data-theme]`
  blocks, or anywhere in `static/app.js`.
- Fail on `px` values in `padding`/`margin`/`gap` that are not one of the seven scale steps.
- Assert every `var(--x)` reference resolves to a defined token. This alone would have caught
  `--text-sub` before it shipped.

## Verification

- Screenshot-diff every section in dark mode before and after each step; steps 2 and 4 should
  produce a near-empty diff.
- Toggle light/dark on every section and confirm no unreadable text — chart tooltips, table
  hover states, and the refresh overlay are the likely misses.
- Re-run the contrast table after any colour change; every text token must clear 4.5:1 against
  both `--surface-page` and `--surface-panel`.
- Confirm the theme survives reload and that first paint does not flash the wrong theme.
- The 71 existing tests must stay green throughout — none of this touches Python logic beyond
  moving the literal out.
