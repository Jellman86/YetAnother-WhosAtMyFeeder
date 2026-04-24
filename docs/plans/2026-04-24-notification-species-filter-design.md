# Notification Species Filter Mode Design

## Goal

Add a user-facing notification species filter that supports three simple modes:

- No species filter
- Block selected species
- Only selected species

The UI should let users pick birds reliably by common name, scientific name, or taxonomy ID, using the existing taxonomy-aware species search rather than raw text entry.

## Current State

The backend already supports structured notification allow-list and deny-list entries through `BlockedSpeciesEntry` objects:

- `notifications_filter_species_whitelist_structured`
- `notifications_filter_species_blacklist_structured`

Notification evaluation already gives blacklist matches precedence over whitelist matches. Settings round-trip preservation is also in place, but the active notification settings UI still exposes only the legacy raw species whitelist input.

The detection settings page already has the better interaction pattern: taxonomy-aware species search, structured `BlockedSpeciesEntry` objects, and display labels that include common and scientific names.

## Product Shape

Use a radio group, not two independent list editors.

Modes:

1. `none`
   - Notify for all species, subject to confidence, audio-only, cooldown, and channel settings.
   - Hide or disable the species picker.
2. `blacklist`
   - Notify for all species except selected entries.
   - Picker label: "Do not notify for these species".
3. `whitelist`
   - Notify only for selected entries.
   - Picker label: "Only notify for these species".

The main UI must not allow editing blacklist and whitelist at the same time. That avoids precedence rules in the user model. Internally, the backend can keep both arrays for compatibility, but the selected mode is authoritative.

## Data Model

Add a new settings field:

```text
notifications_filter_species_mode: "none" | "blacklist" | "whitelist"
```

Save behavior:

- `none`: clear structured whitelist and structured blacklist.
- `blacklist`: write picker entries to `notifications_filter_species_blacklist_structured`; clear structured whitelist.
- `whitelist`: write picker entries to `notifications_filter_species_whitelist_structured`; clear structured blacklist.

Legacy `notifications_filter_species_whitelist` remains supported for backward compatibility. On load, if no explicit mode exists and a legacy whitelist has entries, initialize the UI as `whitelist`. Exact-match migration to structured entries can be attempted using the existing species search helper, with unresolved labels kept as legacy labels.

## UI Components

Extract or generalize the existing blocked-species helpers so notification filters can reuse:

- `buildBlockedSpeciesEntry`
- `mergeBlockedSpeciesEntries`
- `formatBlockedSpeciesLabel`
- taxonomy-aware search against `/api/species/search?hydrate_missing=true`

Prefer a neutral shared name such as `species-filter-entries.ts` if touching the helper broadly. It can keep type compatibility with `BlockedSpeciesEntry` until a rename is worth the churn.

The picker should show:

- common name as primary label when present
- scientific name as secondary label when present
- `Taxon <id>` fallback when only `taxa_id` exists

## Backend Behavior

The existing `_should_notify()` semantics can remain:

- blacklist match returns `False`
- whitelist mode requires a whitelist match
- confidence/audio/camera/cooldown filters still run after species filtering

With the new mode field, backend evaluation should ignore inactive structured lists. That prevents stale hidden entries from affecting behavior after the user switches modes.

## Testing

Backend tests should cover:

- `none` mode ignores structured species filter arrays.
- `blacklist` mode blocks selected taxonomy entries and ignores stale whitelist entries.
- `whitelist` mode allows only selected taxonomy entries and ignores stale blacklist entries.
- legacy whitelist without an explicit mode still behaves as whitelist for compatibility.
- settings API round-trips the mode and structured entries.

Frontend tests should cover:

- switching modes changes the saved payload correctly.
- blacklist mode writes blacklist entries and clears whitelist entries.
- whitelist mode writes whitelist entries and clears blacklist entries.
- none mode clears both structured lists.
- selected taxa render common/scientific labels consistently.

## Non-Goals

- Do not add separate always-visible whitelist and blacklist editors.
- Do not add a new taxonomy table or backend search endpoint.
- Do not remove legacy raw whitelist support in this change.
- Do not change confidence, audio-only, cooldown, or channel behavior.
