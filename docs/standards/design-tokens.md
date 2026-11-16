# Design tokens and primitives

Colour in YA-WAMF comes from a small set of **semantic tokens**: what a colour is for, not which
colour it is. Each token is resolved once for light, dark and high contrast in
[`apps/ui/src/app.css`](../../apps/ui/src/app.css), so a component names no mode and needs no
`dark:` pair. Shared **primitives** in `apps/ui/src/lib/components/ui/` build on the tokens and on
the kit classes (`btn`, `card-base`, `input-base`, …). A CI gate stops new raw colours.

This page says which token or primitive to reach for. [`ui-ux.md`](ui-ux.md) carries the
accessibility and craft rules behind them; [`layout-patterns.md`](layout-patterns.md) carries the
page shapes.

## Tokens

All are Tailwind 4 theme colours, so they work with every colour utility (`bg-`, `text-`,
`border-`, `ring-`, `divide-`, `fill-`, `stroke-`) and take an opacity (`bg-media/60`).

| Token | Use it for |
|---|---|
| `surface` | A panel. `card-base` and `Panel` paint it. |
| `surface-raised` | A well or a hover fill inside a panel. |
| `surface-sunken` | The page ground behind panels; a recessed block such as a `StateBlock`. |
| `strong` | Headings, figures, names: `text-strong`. |
| `ink` | Body text. |
| `muted` | Secondary text, labels, placeholders. 4.5:1 on every ground. |
| `subtle` | Marks only: an icon beside words, a separator. 3:1; never the only carrier of words. |
| `line-soft`, `line` | Quiet rules between rows and round panels; a control's resting edge. |
| `line-strong` | An edge that has to be seen (a meter's track, an axis): 3:1. |
| `accent`, `accent-fg`, `accent-hover` | A primary action's fill and the words on it (`btn-primary`). |
| `accent-ink` | Brand-coloured words, links and lit icons on a panel. |
| `accent-soft`, `accent-line` | The recessed key of a chosen row (`choice-active`), a chosen tile's edge. |
| `danger`, `danger-fg`, `danger-hover` | A destructive action's solid fill (`btn-danger-solid`), an unread count. |
| `media`, `on-media` | A photograph's or the video player's dark ground, and what sits on it. The same in every mode. |
| `focus` | The keyboard focus ring (`focus-ring`). |

### Status tones

Five tones, each with an ink (`text-status-ok`, also its icon or dot), a soft ground
(`bg-status-ok-soft`) and an edge (`border-status-ok-line`, also a small mark's fill):

| Tone | Means | Colour |
|---|---|---|
| `ok` | Confirmed, passed, healthy, connected | Green in every theme |
| `attention` | **This needs a person**, and nothing else | Amber in every theme |
| `fail` | Failed or broken | Rose |
| `info` | Running, in flight, normal emphasis | The brand |
| `neutral` | Off by choice, idle, not measured, unknown | Slate |

A tone never carries meaning alone: `StatusChip` and `StateBlock` always say it in words, and each
tone has its own icon shape. `utils/status-tone.ts` maps a reported backend status to a tone
(`STATUS_TONE`) and to its translated label. Amber is still limited to the components named in
`ATTENTION_COMPONENTS` (`colour-language.layout.test.ts`), each with the work it waits on.

### What the tests prove

[`design-tokens.contrast.test.ts`](../../apps/ui/src/design-tokens.contrast.test.ts) reads the
values `app.css` declares and checks every foreground against every ground it can sit on, in
classic and bluetit, light and dark, and high contrast over both: words 4.5:1 (7:1 in high
contrast), marks and edges 3:1, every status ink on its own soft ground, and the words on every
filled control. A token that is missing in one mode fails too.

## Primitives

| Primitive | What it is |
|---|---|
| `Panel` | A standing section: `card-base`, a heading that names it, optional description and actions. Never tinted. |
| `StatusChip` | A state in words, with the tone's icon and colours. The label always carries the meaning. |
| `StateBlock` | What a section shows instead of its data: `loading`, `empty`, `failed`, `stale`, `off` or `not-measured`, each with a cause line and an optional next step. Only `failed` takes a colour. Inside a `Panel` or a Settings card it is `inline`: the sentence alone, with no box and no heading unless one is given, so a card never holds a second card. On the page it is a `block` with the state's heading. |
| `PageHeader` | A page's one h1, its subtitle and its actions. The shell's `AppPageHeader` adds the owner's controls. |
| `Stat` | One figure and its label as a `<dt>`/`<dd>` pair (inside a `<dl>`). A value that was not measured says so; it is never a zero. |
| `ChartFigure` | A chart with its words: a key, a caller-drawn legend, a data table, or several. The type will not accept a chart with none. A table lists the data the chart draws, every sample at its own time, never values borrowed for the axis ticks. |
| `StatusIcon`, `tone.ts` | The tone shapes and class maps the others use. |

## Figures

Every figure is lining and tabular: the base styles set `font-variant-numeric: lining-nums
tabular-nums`, and give each element the same defaults for Tailwind's numeric utilities, so a
display face never sets "08:00" as "o8:oo" and a `tabular-nums` class keeps lining figures.

## The ratchet

[`design-tokens.ratchet.test.ts`](../../apps/ui/src/design-tokens.ratchet.test.ts) counts, per
file, raw palette classes (`text-amber-600`, `bg-brand-700`, `text-white`), `dark:` colour
overrides and arbitrary values (`text-[10px]`), in `.svelte`, `.ts` and authored `.css` files
alike (an `@apply` is a class too). It compares them with
[`design-tokens.baseline.json`](../../apps/ui/src/design-tokens.baseline.json):

- a file whose count rises fails, and so does a new file that adds any;
- a file whose count falls fails until the baseline is lowered in the same change, so the gate
  never loosens again behind a migration;
- `npm run tokens:baseline` only lowers counts: it refuses any rise and writes nothing;
- in CI, a pull request's committed baseline is compared with the baseline on the branch it
  targets (`npm run tokens:check-base -- <ref>`), so a hand-raised allowance fails too.

```bash
cd apps/ui
npm run lint:tokens        # the ratchet and the contrast proof (also part of npm test)
npm run tokens:baseline    # lower the baseline after migrating a file; refuses any rise
```

The few places that genuinely need a literal colour sit in the test's `ALLOWLIST`, each with its
reason: the colour-theme picker's swatches, and the categorical load series on the Health chart.
In `app.css` the high-contrast repaint rules name the older classes in order to override them
inside the mode. They are nested in one top-level `.high-contrast { … }` rule, and the ratchet
parses the stylesheet with postcss and skips only the selectors of rules nested in that one rule
(`STYLESHEET_SCOPES`). Every other rule counts, wherever it sits and however its selector reads,
declarations and `@apply` lists count everywhere, and a second top-level `.high-contrast` rule is
refused. Comments are not counted. Keep new high-contrast repaints inside the nested rule.
Add to it only with a reason a reviewer accepts.

### Migrating a file

1. Replace each light and `dark:` pair with its token (`text-slate-600 dark:text-slate-400` is
   `text-muted`; `bg-white dark:bg-slate-900` is `bg-surface`).
2. Replace hand-made chips, empty lines and section cards with `StatusChip`, `StateBlock` and
   `Panel`.
3. Delete `dark:` overrides the tokens made redundant, then run `npm run tokens:baseline`.
4. Take before and after screenshots in light, dark, high contrast and the reading font.
