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

---

## References

- [Nielsen Norman Group — 10 Usability Heuristics for User Interface Design](https://www.nngroup.com/articles/ten-usability-heuristics/)
- [W3C — Web Content Accessibility Guidelines (WCAG) 2.2](https://www.w3.org/TR/WCAG22/) · [WCAG 2 Overview](https://www.w3.org/WAI/standards-guidelines/wcag/)
- [Refactoring UI](https://www.refactoringui.com/) (Adam Wathan & Steve Schoger)
