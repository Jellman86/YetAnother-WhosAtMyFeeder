# Issue 23 eBird Export Design

## Goal

Replace YA-WAMF's current eBird CSV export with a strict eBird Record Format export that is safe for direct import into eBird without manual column cleanup.

## Problem

Issue `#23` identifies a mismatch between YA-WAMF's current export and the user's expectation of a direct eBird upload file. The current implementation is close to the eBird import format, but it is still too permissive and underspecified in ways that can create incorrect or unstable output:

- export is unnecessarily gated on eBird API enablement and API key presence
- common names can be influenced by configured eBird locale/taxonomy preferences instead of being pinned to English for export
- there is no date-scoped export flow even though eBird imports are typically built around a single checklist date
- there is no regression coverage proving exact field count/order/no-header behavior against the eBird template
- YA-WAMF-specific metadata placement is not formally constrained to comment fields

## Constraints

- Keep one export mode only: strict eBird format
- Do not emit extra columns
- Do not emit headers
- Keep the exported field order exactly aligned with the standard 19-column eBird Record Format (Extended) already referenced in the code and the issue attachment
- Use deterministic, fail-open local formatting; export must not depend on remote eBird API calls succeeding
- Favor correctness and importer compatibility over preserving current loosely-defined behavior

## Official Format Notes

The eBird upload guidance and attached sample support the following relevant rules:

- `Date` should be emitted as a single `MM/DD/YYYY` field
- `Start Time` should be emitted as a single `HH:MM` field
- imports are grouped by date/location/protocol/effort fields into checklists
- `Incidental` is a valid protocol for opportunistic detections
- direct import files should not rely on YA-WAMF-specific extra columns

## Recommended Approach

Use a single strict export endpoint that treats `/api/ebird/export` as an importer-oriented formatter rather than a general reporting dump.

### Backend

Update the export route to:

- remove the eBird API-key/config requirement for CSV export
- support optional `date=YYYY-MM-DD`
- emit only the standard 19 columns, no header row
- always format `Date` and `Start Time` as single fields
- force English-stable common names for export
- leave unsupported location region fields blank unless explicit values are available
- place YA-WAMF provenance, model name, and AI confidence only in `Submission Comments`
- leave `Species Comments` blank by default

### English Name Resolution

For export stability, use this fallback order for column 1:

1. trusted English common name from local taxonomy cache
2. stored detection `common_name` when it is already English-stable
3. `display_name` only as a last resort

The key rule is that export must not use locale-specific UI presentation names. The export path should be independent from UI locale and from `settings.ebird.locale`.

### UI

Keep the current export button but add a single-day date picker near it.

- blank date means export all eligible detections
- populated date means export only that day
- no “extended” mode, no alternate format selector

This keeps the UX simple while aligning with common eBird upload workflow.

## Correctness And Robustness Considerations

### Second-order effects

- Decoupling export from eBird credentials means users can still export historical detections even if eBird enrichment is off or temporarily broken.
- Pinning English names prevents locale changes from mutating exported CSV semantics across users or over time.
- Keeping YA-WAMF metadata only in comments preserves provenance without breaking importer expectations.

### Third-order effects

- Export tests will act as a compatibility contract against future accidental column drift.
- Date-scoped export reduces user-side manual filtering and avoids accidental multi-day mixed-checklist imports.
- Avoiding remote lookups during export prevents external API outages from blocking a local archival/export workflow.

## Testing Strategy

Add regression tests covering:

- exact 19-column row count
- no header row
- exact date/time formatting
- English-name forcing independent of non-English eBird locale
- date filtering
- export works when eBird is disabled or no API key is configured
- provenance text is in `Submission Comments`, not extra columns

## Out of Scope

- generating eBird checklist headers
- validating every possible eBird species-name edge case against the live remote taxonomy service
- building a second YA-WAMF-extended export format
