# Upstream Missing Retention Design

## Problem

YA-WAMF currently treats missing upstream Frigate events or media as a deletion
signal in some maintenance paths. That is unsafe because YA-WAMF retention can
intentionally diverge from Frigate retention. A Frigate database reset,
migration, or shorter retention window can therefore silently erase local
history in YA-WAMF even when the user intends to keep those detections.

## Goals

- Preserve YA-WAMF detections when Frigate no longer has the corresponding
  event or media unless the operator explicitly selects deletion.
- Make the behavior configurable in the settings UI.
- Persist upstream-missing state on detections so it survives restarts and can
  be surfaced consistently.
- Emit explicit logs and diagnostics events whenever YA-WAMF evaluates,
  marks, keeps, or deletes detections due to upstream absence.
- Keep manual maintenance tools available while making automated behavior safe.

## Non-Goals

- Full event list filtering or badge UI for upstream-missing state in this
  change. The API will expose the state so the UI can build on it later.
- Retrofitting all historical workflows to stop querying Frigate. Live
  `has_frigate_event` and media checks remain useful runtime signals.

## Design

### Policy Model

Introduce an explicit maintenance policy:

- `mark_missing`: keep the local detection and cached media, record that
  upstream Frigate no longer has the event/media.
- `keep`: keep the local detection unchanged and do not persist a missing
  marker.
- `delete`: preserve legacy destructive behavior and remove the local detection
  and cached media.

This policy applies anywhere YA-WAMF currently turns upstream absence into
local deletion, including startup/daily maintenance scans and auto video
classification cleanup.

### Persistence

Add persisted columns to `detections`:

- `frigate_status`
- `frigate_missing_since`
- `frigate_last_checked_at`
- `frigate_last_error`

New or refreshed detections clear the missing marker and return to
`frigate_status = 'present'`.

### Compatibility

Existing configs migrate safely:

- If legacy `auto_delete_missing_clips` is `true`, migrate policy to `delete`.
- Otherwise default to `mark_missing`.
- Preserve `auto_purge_missing_clips` and `auto_purge_missing_snapshots` as
  scan schedulers, but make their action policy-driven instead of implicitly
  destructive.

### Operator Visibility

Every maintenance decision records:

- structured application logs
- bounded diagnostics history entries for owner troubleshooting

The record includes event id, maintenance kind, upstream failure reason, policy,
and action taken.

## Expected Outcome

After this change, a Frigate DB reset or retention rollover should no longer
erase YA-WAMF history by default. Operators can still choose destructive sync
behavior explicitly, and postmortem analysis will have concrete evidence of
what YA-WAMF decided and why.
