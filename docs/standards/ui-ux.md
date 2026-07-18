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
4. **Consistency and standards** — the same word and control for the same thing everywhere; use
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
  order; no keyboard traps; respect `prefers-reduced-motion`.
- **Understandable** — labelled form controls with associated error messaging; predictable,
  consistent navigation; clear language.
- **Robust** — **semantic HTML first**; add ARIA roles/names only to fill genuine gaps, never to
  paper over non-semantic markup.

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
- Detail dialogs use the established teal/emerald header language, a strong scrim, a 44px minimum
  close target, trapped focus, `Escape` dismissal, body-scroll locking, and reduced-motion support.
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
