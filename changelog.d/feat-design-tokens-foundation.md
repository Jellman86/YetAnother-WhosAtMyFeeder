- The Health page, the connection and model test dialogs, the jobs banner, the header and the
  sidebar now draw every state the same way: a worded chip with its own icon shape (a tick for
  healthy, a diamond for "needs you", a cross for failed, a disc for running, a ring for off or
  unknown), so a state never rests on its colour. Empty and unreadable sections say what is
  missing and why in one shared block, and the Health load chart has its key under it and a
  "Show the data as a table" view. Dark mode and high contrast follow from the same colours, so
  these screens no longer need colours of their own for each mode.
- A test that warned now shows amber in the dialog's progress bar and green for a passed step,
  where a passed step used to be the brand colour.
- Under the hood, colour now comes from semantic tokens (surface, text, muted, status tones and
  so on) resolved once for light, dark and high contrast, with shared `Panel`, `StatusChip`,
  `StateBlock`, `PageHeader`, `Stat` and `ChartFigure` components. A unit test proves every
  token pairing meets WCAG 2.2 AA in every mode and colour theme, and a CI ratchet stops any
  file adding raw palette colours, `dark:` overrides or arbitrary values; see
  [design tokens](docs/standards/design-tokens.md).
- Heard-call scores under 60%, in the Explorer and the call player, are amber again in the
  classic theme; they had taken the theme's secondary colour, which classic painted green.
