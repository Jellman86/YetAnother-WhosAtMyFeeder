# Issue 23 eBird Export Follow-up Design

## Goal

Refine YA-WAMF's eBird export so it follows the latest issue `#23` comment as the source of truth, and add the missing export date-picker workflow in the UI.

## Why A Follow-up Is Needed

Issue `#23` was previously closed after the export was tightened to a strict 19-column eBird format. The latest comment reports that the current `dev` behavior still does not match the reporter's expected output and adds several new expectations:

- protocol should be `Stationary` instead of `Incidental`
- duration should be populated
- submission comments should include model/confidence
- the export UI should expose the single-day date filter directly
- English-only naming should remain enforced
- state/country should be populated when reliable local values exist

This follow-up treats that latest issue comment as the new contract.

## Scope

### In Scope

- reopen issue `#23`
- backend CSV export behavior updates
- UI date-picker next to export action
- regression tests for the new export semantics
- changelog update

### Out of Scope

- live reverse geocoding or remote location lookups
- weather-enriched submission comments
- building a second extended CSV format
- guessing model names for historical detections that do not persist them

## Export Contract

The export remains a strict headerless 19-column eBird CSV.

### Field Rules

- `Date`: one field in `MM/DD/YYYY`
- `Time`: one field in `HH:MM`
- `Protocol`: always `Stationary`
- `Duration`: whole minutes from the first exported detection to the last exported detection for that date
- `Common name`: English-stable local taxonomy name first, then stored detection names only as fallback
- `Submission Comments`: compact YA-WAMF provenance plus model/confidence when available

### Duration Semantics

- duration is calculated per exported date bucket
- if the export spans multiple dates, each row uses the duration for its own date
- if only one detection exists on a date, duration is `0`

### Submission Comments Semantics

Use this ordered composition:

- base: `Exported from YA-WAMF`
- append `model <friendly-or-stored-model-id>` when known
- append `confidence <score>` when finite

Examples:

- `Exported from YA-WAMF`
- `Exported from YA-WAMF; model ConvNeXt-Large`
- `Exported from YA-WAMF; model ConvNeXt-Large; confidence 0.95`

### Country And State

- use reliable local/configured values if already available in app settings or export context
- otherwise leave blank
- do not add remote reverse-geocoding in this pass

## UI Workflow

Add a small date input beside the existing eBird export action:

- empty input: export all eligible detections
- selected date: export only that date via `GET /api/ebird/export?date=YYYY-MM-DD`

No extra mode selector or format switch.

## Recommended Approach

Implement this as a tight backend helper refactor plus a small UI control:

- backend computes per-date duration buckets before streaming rows
- row formatter accepts protocol/comment/duration inputs explicitly
- UI reuses the existing export API helper and just passes the optional date

This keeps the change deterministic, local, and easy to regression-test.

## Testing Strategy

Backend:

- protocol is `Stationary`
- date/time remain single formatted fields
- duration is correct for one day and per-date grouping
- submission comments include model/confidence when available
- English-only export name remains stable under non-English locale

Frontend:

- export API helper uses no query when date is blank
- export API helper appends `?date=YYYY-MM-DD` when date is present
- UI build/type check passes with the new date input

## Risks And Mitigations

- Risk: changing protocol/duration semantics could break prior assumptions
  - Mitigation: lock them with explicit regression tests
- Risk: old detections may not have persisted model info
  - Mitigation: omit model from comments rather than guessing
- Risk: location metadata may tempt unsafe inference
  - Mitigation: only use reliable local values; otherwise leave blank
