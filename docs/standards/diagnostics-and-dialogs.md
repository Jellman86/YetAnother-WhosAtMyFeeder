# Diagnostics & dialog standard

The codified look and behaviour for **guided, staged flows** in YA-WAMF: the
first-run setup wizard and every "test / diagnostic" dialog (AI model, Frigate &
MQTT connection, notification channels, integration tokens). One shape, one set
of rules, so a user who has seen setup already understands every test.

This is the depth behind [`CLAUDE.md`](../../CLAUDE.md) §5. When this page and
`CLAUDE.md` disagree, `CLAUDE.md` wins.

---

## 1. Use the shared components

- **Test/diagnostic flows use [`DiagnosticDialog`](../../apps/ui/src/lib/components/DiagnosticDialog.svelte).**
  Do not hand-roll a modal for a test. The dialog owns the chrome, the progress
  bar, the checklist, the auto-progress reveal, focus management, and the portal.
- **The guided wizard uses `WizardShell` / `WizardStepLayout`.** Both share the
  same visual language as the dialog (below) so the two never drift.
- A caller supplies *content and truth* (title, subtitle, the ordered `stages`,
  a `summary` snippet, the final `result`); the component supplies *behaviour and
  style*.

## 2. The look (shared visual language)

- **Shell:** `rounded-3xl`, `max-w-2xl`, `border border-white/10`, `shadow-2xl`,
  on a `fixed inset-0` dimmed + `backdrop-blur-sm` scrim.
- **Header band:** `bg-gradient-to-r from-teal-50 via-emerald-50 to-white`
  (dark: teal/emerald → slate). A `YA-WAMF` eyebrow in
  `text-[10px] font-black uppercase tracking-[0.22em] text-teal-700`, then a
  `text-2xl font-black` title and a calm `text-sm` subtitle.
- **Progress:** a row of equal-width segments — teal for passed, amber for warnings,
  red for failed, pulsing teal for the running step, slate for pending/skipped. A visually-hidden
  `role="progressbar"` mirrors it for assistive tech.
- **Checklist:** one bordered container with `divide-y` rows — **not** a stack of
  separate cards. Each row is a small status disc (number → ✓ / ! / –) plus a
  bold label and a plain-language message.
- **Footer:** `border-t`, right-aligned, using the shared button kit (`btn` +
  `btn-ghost` / `btn-primary`).

## 3. The behaviour

- **Overlays portal to `document.body`** (via the `portal` action). A `fixed`
  backdrop rendered deep in the tree is trapped by any ancestor `transform` /
  `filter` / `backdrop-filter` stacking context, so a lower-`z` sticky header can
  paint over it. Portalling guarantees the scrim covers the whole window.
- **Auto-progress, honestly.** Results often arrive from the backend at once; the
  dialog *reveals* them one step at a time (~350 ms cadence) so the flow visibly
  steps forward. **A step only turns green when its check actually passed** — the
  reveal controls *when* a resolved step appears, never *whether* it passed. This
  is [`CLAUDE.md`](../../CLAUDE.md) §1/§5: never imply state that did not happen.
- **Every state is legible:** pending, running, passed, warning, failed, skipped. A
  failure stops the run, colours its row, and states the cause and next step in
  plain language (Nielsen #9) — not an error code. Warning and skipped outcomes
  remain terminal but must not be promoted to a pass or produce a green summary.
- **Keyboard & focus:** `Escape` closes, focus is trapped while open, and body
  scroll is locked. Bump `runId` on each run so the reveal restarts.

## 4. Adding a new test flow

1. Model the checks as an ordered `DiagnosticStage[]` (`id`, `label`, `state`,
   `message`). Prefer *real* sequential checks (each its own backend call that
   resolves a stage) over one call mapped onto stages.
2. Render `<DiagnosticDialog … {stages} busy={running} result={…} runId={…}>` and
   pass a `summary` snippet for the context strip (e.g. "Provider · Model").
3. Keep every user-facing string in i18n with a `{ default }` fallback.
4. Guard the wiring with a `*.layout.test.ts` that asserts the dialog is used and
   the stages are present.

## References

- [`CLAUDE.md`](../../CLAUDE.md) §5 — Clean, honest UI
- [`ui-ux.md`](./ui-ux.md) — usability, accessibility, and visual-craft bar
- Implementation: `DiagnosticDialog.svelte`, `AITestModal.svelte` (reference
  caller), `WizardShell.svelte`
