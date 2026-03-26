# Blocked Species Picker Design

**Date:** 2026-03-26

## Goal

Replace the blocked-label free-text add flow with the same species-search picker pattern used for manual tagging, while preserving backward compatibility with existing raw `blocked_labels` entries and avoiding any silent unblock of legacy data.

## Recommended Approach

Use a conservative dual-format model:

- Keep legacy `blocked_labels: string[]` fully supported in the backend.
- Add structured `blocked_species` entries for all new picker-driven additions.
- Attempt automatic legacy migration only when a legacy label resolves unambiguously to a single canonical species.
- If a legacy label cannot be resolved confidently, keep it as a legacy raw-label chip instead of dropping it.

This keeps the failure mode safe. Ambiguous or stale labels remain blocked rather than disappearing during migration.

## Data Model

Add a structured blocked-species entry with the canonical identity fields already used elsewhere:

```json
{
  "scientific_name": "Columba livia",
  "common_name": "Rock Pigeon",
  "taxa_id": 3017
}
```

Rules:

- `taxa_id` is the strongest match key when present.
- `scientific_name` is the canonical text fallback.
- `common_name` is used for display and secondary matching support.
- Invalid or empty entries are discarded during normalization.

## Backend Behavior

The backend should treat `blocked_labels` and `blocked_species` as one effective blocklist.

Matching order:

1. Check legacy `blocked_labels` case-insensitively against the raw/collapsed label path.
2. Check `blocked_species.taxa_id` when a detection/tag path has a canonical taxon id.
3. Check `blocked_species.scientific_name` and `blocked_species.common_name` case-insensitively against resolved taxonomy names.

This shared logic should be reused in:

- `DetectionService.filter_and_label()`
- `DetectionService.save_detection()`
- `DetectionService.apply_video_result()`
- manual-tag guard in `events.py`

The settings API should read/write both `blocked_labels` and `blocked_species`.

## Frontend Behavior

`DetectionSettings.svelte` should:

- remove the free-text add input for new blocked entries
- add a manual-tag-style species search box using `/api/species/search`
- use hydrated searches for meaningful typed input
- render structured chips as `Common Name (Scientific name)` when both exist
- render legacy unresolved chips separately and clearly mark them as legacy
- allow removing either structured or legacy entries independently

## Conservative Auto-Migration

Auto-migration runs from Settings load state, not as a destructive config rewrite.

For each legacy raw label:

- search for likely matching species
- if there is exactly one unambiguous canonical match, move it into `blocked_species`
- if not, keep it in `blocked_labels`

This migration should be reflected in the local Settings baseline so the page does not appear dirty immediately after load.

## Testing

Required coverage:

- backend settings API round-trip for `blocked_species`
- backend blocked-species matching via `taxa_id` / scientific / common names
- manual-tag guard rejects structured blocked species
- frontend conservative migration helper tests
- frontend source/wiring tests showing Settings and Detection Settings thread `blocked_species` through the page

## Non-Goals

- No silent dropping of unresolved legacy labels
- No bulk destructive migration written directly to config on load
- No expansion into canonical identity normalization for the whole app beyond the blocked-species scope
