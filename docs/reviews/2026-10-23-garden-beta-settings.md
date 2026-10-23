# Garden beta settings: complete setup in one view

## Outcome

**Settings → Beta features → Garden animals** is now the single place to set up
Garden: beta switch, its own models, cameras and motion roles, labels, the animal
proposal and naming thresholds, and what happens to captures. The **Garden animals**
page stays the daily review surface and no longer downloads models.

## Audited contracts

Garden uses three models of its own, none of them the bird classifier:

| Role | Backend source | File | Size | Used by |
|---|---|---|---|---|
| Automatic check | `garden_identification.MODEL_SIZES["4.0.3a"]` | `models/garden/speciesnet-4.0.3a.onnx` | 223,998,782 B | `garden_automatic_review` (CPU), **Check photo**, crop suggestions |
| Species suggestions | `MODEL_SIZES["4.0.3b"]` | `models/garden/speciesnet-4.0.3b.onnx` | 223,999,179 B | owner **Suggest species** (default variant) |
| Motion detector | `garden_md1000_cedar.json` `model_bytes` | `models/garden/md1000-cedar.onnx` | 101,228,666 B | `garden_motion` scans |

Existing endpoints were enough, so this change adds no API:
`GET /api/garden/identification`, `GET /api/garden/motion`,
`POST /api/garden/models/{variant}/install` and `POST /api/garden/motion/install`.
All are owner-only and answer `404` while the saved beta switch is off. The installs
stream to a temp file under the Garden models directory, check the size and SHA-256,
and replace the file atomically. They share one Garden admission slot (`busy`), so they
return `409` while a check, scan or other download runs. They never touch bird model
activation, providers or settings.

The automatic check calls `ensure_model("4.0.3a")`, so the required model still
downloads itself on the first due check if the owner has not downloaded it. The UI
says so instead of claiming downloads only happen on request.

## Inventory and placement

| Control or information | Before | After | Reason |
|---|---|---|---|
| Beta switch, cameras, motion roles, labels, thresholds, naming | Beta features | unchanged | already the saved-settings home |
| SpeciesNet 4.0.3a/4.0.3b download | Garden page, behind the variant select | Beta features → **Garden models** | setup, not daily review |
| Cedar detector download | Garden page → Motion collection | Beta features → **Garden models** | same |
| Model ready/missing/unavailable/unknown | Garden page, partial | **Garden models**, every model | one truthful status per model |
| Country needed for naming | Garden page only | also **Garden models** | it decides whether naming can happen |
| CPU-only, one at a time, memory not measured, no CPU fallback | docs only | **Garden models** | stated requirements |
| Outcomes: Needs review, Confirmed, Dismissed, person removal | Garden page help | **Where captures go** | setup explains the result |
| Variant and provider choice for manual checks | Garden page | unchanged | a per-request choice, not a saved setting |
| Motion status, queue, last scan, automatic status message | Garden page | unchanged | live operational state |
| Review inbox and actions | Garden page | unchanged, linked | not duplicated in Settings |
| Detection, crop and provider controls | Detection | unchanged | shared bird controls; Detection has no Garden controls |
| Connection Garden note | Connection | unchanged | points to Beta features |

## Behaviour and races

- **Saved state only.** Status is fetched only when `settingsStore.settings.beta_garden_animals`
  is true. Toggling the switch on without applying shows "Choose Apply Settings…" and no
  downloads, because the API would answer `404`. After Apply, the store updates and the
  status loads.
- **Downloads are separate from Apply.** A download changes no form state, writes no
  settings and leaves unsaved edits in place. Tests assert no settings write and no
  non-Garden write during a download.
- **One at a time.** The component allows one download and disables the others,
  matching the backend slot. A busy backend disables downloads with a stated reason.
- **No false progress.** Install requests block for up to 180 s server-side (240 s
  client timeout). The row shows an indeterminate bar and text, never a percentage.
- **Unmount mid-download.** The request carries on server-side. On return the status
  shows `busy` and explains the wait; **Refresh model status** reads the final state.
  Stale responses are discarded by a generation counter.
- **Failures.** A `503` leaves the old file in place, so the row stays **Not downloaded**
  with the server's message and **Retry download**. A failed status read shows
  **Status unknown**, never ready, and offers no download.

## Privacy, history and rollback

No backend, schema, setting, default, threshold, inference or quarantine change. No
capture, review or history is read or written by the settings view. Rollback is a
plain revert. Downloaded model files are left behind and remain valid for the Garden page.

## Second-order costs

- Three more model rows lengthen the Beta features card. At 320 px with 200% text the
  shared `SettingsCard` leaves about 158 px of content width, so long words wrap
  mid-word. Nothing overflows, but it is cramped. That card constraint is shared and
  left unchanged.
- Model sizes appear as static text in the beta-off requirements, matching earlier
  button labels. Live rows read sizes from the API.
- Translations for eight locales were written with this change and need native review.

## Overlap with the Detection settings redesign (#780)

This branch does not edit `Settings.svelte`, `DetectionSettings.svelte` or
`ModelManager.svelte`. Both branches edit `CHANGELOG.md` (Unreleased head), all locale
files and `docs/setup/configuration.md`, in different keys or rows. Expect textual
conflicts only at the top of the changelog and possibly adjacent locale lines.

## Validation

See the pull request for exact commands and results.
