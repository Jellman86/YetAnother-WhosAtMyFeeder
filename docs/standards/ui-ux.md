# UI/UX standard

The researched usability, accessibility, and visual-craft bar for YA-WAMF's interface. This is
the depth behind [`CLAUDE.md`](../../CLAUDE.md) §5 — `CLAUDE.md` carries the enforceable rules;
this page carries the full checklist the UI-simplification / UI-refresh work applies. When this
page and `CLAUDE.md` disagree, `CLAUDE.md` wins.

YA-WAMF's UI is **operational, not marketing**: dense, calm, and honest about state. The three
pillars below make that concrete. Grounded in the sources at the [end](#references).

---

## 1. Usability — Nielsen's 10 heuristics

The baseline checklist for every screen, feature, and flow:

1. **Visibility of system status** — always show what's happening: loading, progress, saved,
   skipped, stale. Give timely feedback for every action.
2. **Match between system and the real world** — user language and real-world conventions, not
   internal jargon or implementation terms.
3. **User control and freedom** — clear cancel/undo/exit; and never imply an irreversible action
   is reversible (ties to [`CLAUDE.md`](../../CLAUDE.md) §1).
4. **Consistency and standards** — the same word and control for the same thing everywhere (the
   words are in [`glossary.md`](glossary.md)); use
   the shared UI kit (`apps/ui/src/app.css`) rather than one-off Tailwind.
5. **Error prevention** — prevent the problem (confirm destructive actions, constrain inputs,
   disable the impossible) rather than only reporting it after.
6. **Recognition rather than recall** — surface options, defaults, and prior choices; don't make
   users remember state from another screen.
7. **Flexibility and efficiency of use** — shortcuts and presets for power users without harming
   first-timers. Use **progressive disclosure** (basic vs. advanced) to keep the default simple.
8. **Aesthetic and minimalist design** — no irrelevant content competing for attention; dense is
   fine, cluttered is not.
9. **Help users recognize, diagnose, and recover from errors** — plain-language messages that
   state the cause and the next step, not error codes.
10. **Help and documentation** — contextual guidance where a screen genuinely needs it, close to
    the point of use.

## 2. Accessibility — WCAG 2.2 Level AA

**Level AA is the floor**, not a stretch goal. The four **POUR** principles, made concrete:

- **Perceivable** — sufficient colour contrast (AA ratios); **never signal meaning by colour
  alone** (pair with text/icon/shape); real `alt` text for informative images, and decorative
  media hidden from assistive tech.
- **Operable** — everything works from the **keyboard**; **visible focus** states; logical tab
  order; no keyboard traps; respect `prefers-reduced-motion`. A field that can sit flush against an
  edge that clips (a phone's edge, a scrolling rail) adds `input-focus-inset` to `input-base`, so its
  focus ring is drawn inside the border and cannot be cut off.
- **Understandable** — labelled form controls with associated error messaging; predictable,
  consistent navigation; clear language.
- **Robust** — **semantic HTML first**; add ARIA roles/names only to fill genuine gaps, never to
  paper over non-semantic markup.

### Kit rules that keep AA true

The kit in `apps/ui/src/app.css` carries the colours and sizes below, and
`apps/ui/src/app.kit-contrast.test.ts` proves each one against the page, a panel and a well in
both modes and both colour themes. A screen that uses the kit inherits the proof; a hand-rolled
class does not. `apps/ui/src/lib/kit-accessibility-classes.test.ts` rejects the classes that broke
these rules before.

- **Focus is one opaque colour per mode.** Use `focus-ring` (or `ring-focus` on a hand-built
  control): two opaque pixels of `--focus`, which is 3:1 or better against everything it can sit
  beside. Never a translucent ring (`ring-brand-500/50` measured 1.6:1 on white) and never a raw
  brand step, because teal and blue pass at different steps. A control over a photograph or on a
  ground that stays dark in the light theme (the video player) uses
  `focus-ring-on-dark`, `btn-on-dark` or `input-on-dark`.
- **Colour comes from the semantic tokens** ([`design-tokens.md`](design-tokens.md)): `text-strong`,
  `text-ink` and `text-muted` for words, `text-subtle` for marks only, and the status tones for
  state. Each is proved at 4.5:1 (marks and edges 3:1) on every ground in every mode, so a screen
  that uses them needs no `dark:` pair. Slate 500 and lighter fail as words on a tinted row or the
  page ground; that is why `muted` is the lightest ink for words.
- **No readable text under 12px, and the floor is not in pixels.** `text-3xs`, `text-2xs` and
  `text-xs` are `max(<step>rem, var(--text-floor))`. The floor is half the browser's
  own text size plus a third of the root: 12px at the smallest Appearance size, a little more at
  each larger one, and twice as much when the browser's text size is doubled. A `12px` floor would
  do neither. Do not set type in px or with an arbitrary size.
- **Hierarchy by size holds at every text size.** Where the floor catches up with the steps above
  it (the Smallest, Smaller and Standard Appearance sizes), `text-sm` stays a twenty-fourth above
  the floor and normal text (`text-base`, which `body` is set in) a twelfth above it, so small
  print, secondary text and normal text are always three sizes. Never rely on the bare root size
  for normal text. `apps/ui/browser-tests/type-scale.spec.ts` reads the sizes a browser actually
  draws, at every Appearance size and at the browser's text size and twice it: each kit step is
  12px or more, larger than the step below, larger at each Appearance size, and doubled when the
  browser's size is.
- **Nothing is made smaller to fit.** A page title that outgrows a narrow column is hyphenated by
  the page's language (`hyphens: auto`, with `overflow-wrap: anywhere` as the last resort); its
  size is never stepped down, because enlarged text has to stay enlarged.
- **A button is a 44px target.** `btn` alone gives the height and padding; add a height or padding
  utility only to change them. A control is never smaller than 24px in either direction.
- **A switch is `switch-track` with a `switch-thumb` inside it.** The off track is 3:1 against
  its ground, as visible as the on track; the thumb's side carries the state, so the state never
  reads by colour alone; keyboard focus draws the kit ring.
- **Words over a photograph use `photo-chip`.** White on a fill dark enough to pass 4.5:1 over a
  white frame, with no blur, so legibility never depends on what the camera saw.
- **A control's accessible name contains its visible words** (WCAG 2.5.3). Prefer no `aria-label`
  at all when the content already names the control; when a label adds context, it starts with the
  visible text ("Hide" on screen, "Hide detection" as the name).
- **Lists, definition lists and regions keep their shape.** `role="status"` goes on a wrapper,
  not on the `<ul>` it would turn into a non-list; a `<dl>` holds only `<dt>`/`<dd>` or `<div>`
  groups of them; a dialog portalled to the body uses plain `<div>`s, not `<header>`/`<footer>`,
  which would count as a second page banner and footer.
- **Text at 200% loses nothing.** A name, a caption or a row detail wraps (`wrap-break-word`, or
  `wrap-anywhere` for an identifier with no spaces); it is not ended with `truncate` or
  `line-clamp`. A flex child that holds words has `min-w-0` so it can shrink and wrap, and a row
  that cannot hold its figure beside its name lets the figure drop to a line of its own
  (`flex-wrap`). A fixed track in rem (`grid-cols-[9rem_…]`) doubles with the text, so prefer
  `auto-fit` tracks. The browser suite doubles the root font size at 390 and 1440 and fails on
  text that is cut by a clipping box, spills out of its control, or is drawn over other text.
- **A dense table reflows by its own width in rem, not by the window in px.** A window
  breakpoint (`md:`, `lg:`) does not know the text has grown, so a table keeps its columns while
  doubled text is squeezed into them. Put the table in an `@container` and switch between stacked
  rows and columns with container variants (`@4xl:block`, `@5xl:table-cell`), which are rem of
  the box: at a large text size the same box holds fewer rem and the table becomes rows. The
  Leaderboard ranking is the model.
- **A chart's colours are named in words beside it, all the time.** A key under the chart gives
  each colour its name and figure; a label that only appears on hover or focus does not count.
  Inside a bar, a figure is shown only where it fits whole (a container query in `em`), never cut.
- **A form checks its own fields.** Use `novalidate` with `aria-required`, and say what is
  missing in a message under the field, tied to it with `aria-describedby` and `aria-invalid`,
  with focus moved to the first field at fault. The browser's own bubble shows one field at a
  time, is not translated by the app and disappears by itself. An error from the server is
  reworded as a cause and a next step; a status word such as "Invalid credentials" is never shown.
- **A list that is still arriving is not drawn in part.** When rows come from more than one
  source, hold a skeleton until the slow source has answered, so late rows do not push what is
  already on screen (the Notifications history waits for the first jobs reading).
- **Turning off clicks must not turn off reading.** To let a parent take the clicks, use
  `pointer-events-none` on the children (`[&_*]:pointer-events-none!`), not `inert`, which also
  removes them from the accessibility tree.
- **Nothing changes by itself while it is being read.** No rotating text or carousel without a
  pause control; a count or a status that updates is a live region, not an animation.
- **The page declares its language.** `<html lang>` follows the language on screen.

The Chromium suite runs axe-core over the main routes and the main dialogs (the record, a delete
prompt, a connection test, the video player, the setup wizard) with data on them, in both themes
(`apps/ui/browser-tests/accessibility.spec.ts`); a serious or critical violation fails the build.
axe cannot assess focus order, target size or meaning carried by colour, so it is a floor under
the manual checks above, not a replacement for them.

## 3. Visual craft — Refactoring UI

- **Hierarchy through size, weight, and colour** — not size alone. Emphasise the primary action;
  de-emphasise secondary/tertiary. Don't let HTML semantics dictate visual styling — style for
  the visual hierarchy you want.
- **Design grayscale-first, add colour last** — so hierarchy comes from spacing, contrast, and
  type rather than leaning on colour as a crutch.
- **Constrained scales** — spacing, type, colour, and shadow come from a fixed system (the
  Tailwind scale); avoid arbitrary one-off values. Systems, not improvisation, produce
  consistency.
- **Generous whitespace** — give elements room to breathe; the easiest cleanup is usually more
  space, not more styling.
- **Stable layout for media** — fixed aspect ratios, lazy-loaded, silent placeholder fallback;
  artwork is a recognition aid and must never shift layout or imply state (`CLAUDE.md` §5).

## 4. Content-detail surfaces

Detail views such as Species Details are records, not miniature dashboards:

- Lead with the user's own data and likely next action. Put third-party reference and enrichment
  below the local record rather than making users scroll past it.
- Use one strong media anchor where it helps recognition. Do not repeat the same title or
  description over both the header and image.
- Group the main facts in a semantic list or table and separate later sections with whitespace and
  dividers. Reserve a bordered or tinted card for a genuinely distinct interactive object or state;
  do not wrap every section in one.
- Keep secondary provider labels and source links visible but quiet. External data must never look
  like a local detection.
- Detail dialogs wear the shared `DialogHeader` (`apps/ui/src/lib/components/ui/`): the dialog's
  name and the one round close button, with a 44px minimum target. They also keep a strong scrim,
  trapped focus, `Escape` dismissal, body-scroll locking, and reduced-motion support.
- On a phone, the dialog may become a full-height sheet using dynamic viewport units. On larger
  screens, constrain its width and height and keep one predictable internal scroll region.

## 5. Rankings and analytical surfaces

Leaderboards are working data views, not award ceremonies or collections of summary cards:

- Put the ranked list before supporting charts. A featured record and a short highlight strip may
  orient the user, but must not repeat the same top-three data in separate cards.
- Use styled numeric ranks rather than emoji medals. Keep table headings, units, source state, and
  time range explicit so colour is never carrying the meaning alone.
- Use a semantic table at widths where its useful comparison columns fit. On phones, provide a
  purpose-built vertical list with the core rank, species, active metric, trend, and recency rather
  than forcing horizontal table scrolling.
- Changing the active source or time range must reorder the data by that metric, not only recolour
  a control or swap the displayed value. Deduplicate merged sources before rendering stable lists.
- Treat charts as secondary evidence. Separate them with dividers, give them readable text context
  and empty/loading states, and reserve compact disclosures for optional overlays or analysis.
- Lazy-load below-fold species images, use stable thumbnail dimensions and quiet vector fallbacks,
  and retain a visible 44px focusable target for every row that opens detail.

## 6. History and log surfaces

History views are working records first and analytics dashboards second:

- Put the filter controls directly above the record they affect. Keep the active window, confidence,
  species, and source visible without making the user open a configuration panel.
- Lead with a semantic table when its comparison columns fit. Reflow the same rows into a compact
  vertical log on phones; do not force horizontal scrolling or duplicate the dataset in separate
  desktop and mobile markup unless the information genuinely differs.
- Page long histories in manageable batches so later context stays reachable. Keep current range,
  total count, previous/next availability, loading, empty, error, retry, and refresh state explicit.
- Use the most honest per-record artifact as the visual anchor. For audio history this is the
  spectrogram; stock species artwork is only a secondary recognition aid and must be labelled and
  positioned accordingly.
- Put trends, distributions, top-species summaries, and source rollups after the log. Use dividers
  and whitespace rather than a card around every chart, and keep chart labels readable at phone
  widths and in both colour themes.

---

## References

- [Nielsen Norman Group — 10 Usability Heuristics for User Interface Design](https://www.nngroup.com/articles/ten-usability-heuristics/)
- [W3C — Web Content Accessibility Guidelines (WCAG) 2.2](https://www.w3.org/TR/WCAG22/) · [WCAG 2 Overview](https://www.w3.org/WAI/standards-guidelines/wcag/)
- [Refactoring UI](https://www.refactoringui.com/) (Adam Wathan & Steve Schoger)

### Styling toolchain

The UI is built with Tailwind CSS 4 through `@tailwindcss/vite`; there is no `tailwind.config.js`
or PostCSS configuration. Design tokens (breakpoints, the closed colour palette, the type scale,
the 44px touch target) live in the `@theme` block of `apps/ui/src/app.css`, beside the kit. Classes
are read from `apps/ui/src` only.

`apps/ui/src/tailwind-3-parity.css` keeps the Tailwind 3 defaults the screens were drawn against
(border colour, form-control resets, the sibling selectors behind `space-y-*` and `divide-*`), so
the upgrade changed nothing on screen. Remove a block from it only together with a check of the
screens that depend on it.

The fixed palette is an `@theme inline` block, so those colours are written into each utility as
literals; the semantic tokens (`surface`, `strong`, `muted`, `accent`, `status-*`, …) and the scales
they read (`brand`, `success`, `attention`) stay variables, because a mode or a colour theme
resolves them. Unit tests are left out of the class scan.

Supported browsers follow from the toolchain: Chrome and Edge 111, Firefox 128 and Safari 16.4 or
newer ([setup guide](../setup/getting-started.md#supported-browsers)).

### Dialog focus lifecycle

The shared `trapFocus` utility returns focus to the connected, visible opener when a dialog
closes. Nested dialogs restore their own opener first; disposing a parent cannot steal focus
from a still-open child. A removed or disabled opener falls back to the remaining dialog or
the main page content. Closing cancels the delayed initial focus, and deliberately moving
focus to another control is preserved. Dialog components use this shared cleanup rather than
adding a second unconditional focus restoration.
