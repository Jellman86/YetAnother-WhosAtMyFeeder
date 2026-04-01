# Error Bundles UI Design

**Date:** 2026-04-01

**Problem**

The current `Error Bundles` section on the owner `Errors` page makes capture state ambiguous. After clicking `Capture Bundle`, the user only sees a new row appear in a flat list. There is no strong visual confirmation that a bundle is now available, no emphasis on the newest artifact, and the saved bundle list is too uniform to scan quickly.

**Goals**

- Make it obvious when a bundle has just been captured and is ready to download.
- Make saved bundles visually distinct from one another.
- Keep the interaction local to the existing `Errors` page and current diagnostics store.
- Preserve the current bundle model and local persistence behavior.

**Non-Goals**

- No new backend API for bundle persistence.
- No modal flow or multi-step wizard.
- No redesign of the broader incident workspace outside the bundle section.

**Recommended Approach**

Use a hybrid layout:

1. Add a prominent `Latest Bundle Ready` card at the top of the section.
2. Redesign the saved bundle list as a card-based bundle library below it.

This approach solves both moments of confusion:

- immediate post-capture confirmation
- later re-discovery and download of saved bundles

**Interaction Design**

After capture:

- The newest bundle is surfaced in a success-styled summary card.
- The card explicitly says the bundle is available locally.
- The primary action is `Download Latest`.
- Supporting metadata is shown as compact chips or stat pills:
  - groups
  - events
  - snapshots
  - captured time

Saved bundles:

- Replace the flat divided list with individual cards.
- Pin the newest bundle visually with a `Newest` badge.
- Show title, captured time, and a short metadata row.
- If report notes exist in the bundle payload, show a short preview line.
- Keep actions on each card:
  - `Download`
  - `Delete`

Empty state:

- Replace `No saved bundles yet.` with copy that clarifies availability.
- Example: `No captured bundles available yet. Capture one to save a downloadable diagnostics snapshot on this device.`

**Visual Direction**

- Distinct visual hierarchy between:
  - capture controls
  - latest captured artifact
  - saved bundle library
- Use warmer success/available styling for the latest card instead of another neutral card.
- Keep typography dense and operator-focused rather than decorative.
- Ensure mobile layout stacks cleanly with actions wrapping below metadata.

**Data / State Impact**

No new storage primitives are required. The page can derive:

- `latestBundle` from `jobDiagnosticsStore.bundles[0]`
- note preview from `bundle.payload.report.notes`

The existing bundle payload already contains enough metadata for the redesigned UI.

**Testing**

- Add UI store/component-level coverage for newest bundle derivation and notes preview extraction if helpers are introduced.
- Add render-oriented tests for the bundle section if there is existing page coverage nearby.
- Run Svelte type-check after the UI update.

**Risks**

- Over-styling the card could make the section louder than the actual incident workspace.
- Pulling note preview text directly from payload needs null-safe handling.
- The section must remain understandable when no workspace payload is currently loaded.

**Acceptance Criteria**

- After clicking `Capture Bundle`, the user can immediately tell a bundle is available.
- The newest bundle is visually emphasized and downloadable with one obvious action.
- The saved bundle library is easier to scan than the current flat list.
- Existing bundle persistence and download behavior remain intact.
