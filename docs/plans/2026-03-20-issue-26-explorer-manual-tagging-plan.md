# Issue 26: Explorer Name Canonicalization And Multi Manual Tagging

## Problem
- Explorer manual-tag search showed duplicate species rows for the same bird when classifier labels mixed common-name, scientific-name, and alias formats.
- Explorer manual tagging only supported one event at a time.

## Fix
1. Canonicalize `/api/species/search` results.
   - Collapse alias labels to one selectable species row.
   - Prefer `taxa_id`, then scientific name, then common/display fallback.
   - Return canonical manual-tag IDs so the backend stores normalized taxonomy instead of UI alias strings.
2. Add bulk manual-tag backend support.
   - New bulk endpoint reuses the single-event manual-tag logic.
   - Preserve taxonomy lookup, audio re-correlation, feedback rows, and broadcasts.
3. Add Explorer multi-select UI.
   - Selection mode on the Events page.
   - Bulk manual-tag modal using the same species search API.
   - Apply one chosen species across all selected events.

## Verification
- Backend:
  - species-search dedupe test
  - single-event manual-tag regression tests
  - bulk manual-tag API test
- UI:
  - `svelte-check`
  - targeted API test pass

## Follow-Up
- Add dedicated UI tests for Events multi-select interaction if the page gains more bulk actions.
- Consider surfacing the canonical species/taxa ID in the bulk response if the Explorer needs richer optimistic updates later.
