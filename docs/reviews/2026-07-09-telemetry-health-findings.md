# Telemetry health findings — 2026-07-09

A review of the opt-in health telemetry to see what is actually failing across
real installs, and what YA-WAMF should do about it before `v3.0`.

## Source and scope

- Cloudflare D1 database `yawamf-health-issues`, table `health_issue_reports`
  (written by the telemetry worker in `apps/telemetry-worker`).
- **13 installs** reporting, **87 distinct issue fingerprints**, **1,621 reports**,
  **~79,600 occurrences**, window **2026-05-03 → 2026-07-09**.
- Severity split: **57 warning · 26 error · 4 critical**.
- Top components by installs affected: `event_processor` (13), `mqtt_service` (8),
  `auto_video_classifier` (7), `frigate_missing_policy` (4), `detections` (2).

Occurrence counts are per-install event tallies, so they measure *volume*, not how
widespread an issue is. Installs-affected is the better "how many people hit this"
signal.

## Findings

### 1. Frigate media/event unavailability is the dominant real problem

The largest cluster of genuine failures all trace to the same root cause: **Frigate
does not have the snapshot / event / clip when YA-WAMF goes to fetch it.** This is
the same family we recently diagnosed for a single user (brief tracked objects that
never persist as Frigate events, plus retention rotation) — but the telemetry shows
it is fleet-wide:

| Issue | Severity | Installs | Occurrences | Still active |
|---|---|---:|---:|---|
| `event_processor / drop_classify_snapshot_unavailable` | error | **8** | 3,418 | yes (today) |
| `auto_video_classifier / event_not_found` | warning | 6 | 4,683 | yes (today) |
| `auto_video_classifier / clip_not_found` | warning | 5 | 972 | yes |
| `event_processor / stage_failure @ classify_snapshot` | **critical** | 4 | 2,703 | yes (today) |
| `frigate_missing_policy / frigate_missing_marked` | warning | 3 | 7,680 | yes |
| `frigate_missing_policy / frigate_missing_deleted` | warning | 2 | **18,138** | yes (today) |

Two installs alone have **deleted local detections ~18k times** because Frigate no
longer had the event — i.e. real user history is being discarded due to this. The
`drop_classify_snapshot_unavailable` error (8/13 installs) means the snapshot was
not cached in time before classification, so the detection was dropped outright.

This is the highest-leverage area to improve: it affects the majority of installs,
is still active on current builds, and in its worst form silently loses data.

### 2. The only critical issue is on old versions

`event_processor / stage_failure @ classify_snapshot` (critical, 4 installs, 2,703
occ) appears **only on `2.9.15` and `2.10.0`** builds — not on `2.11`+. It is very
likely already resolved by the classifier inference-health refactor that shipped in
`2.11`. Roughly **5 installs are still on the released `2.10.0`** (active today), so
the fix exists but has not reached them.

Its `sample_context_json` is empty (`{}`) — see finding 5.

### 3. Expected, config-driven drops dominate the volume and pollute the signal

The single highest-*volume* "issue" is `event_processor / drop_filter_low_confidence`
(warning, 11 installs, **36,429 occ**), followed by `drop_filter_blocked_label`
(3 installs, 3,434 occ). These are **not faults** — they are the confidence filter
and the user's blocked-species list working as configured. Reporting them as
health *issues* buries the real failures under ~40k occurrences of normal
behaviour and inflates every aggregate.

### 4. Frigate connectivity blips are common but benign

`mqtt_service / frigate_went_offline` (warning, 8 installs, 226 occ) is widespread
but low-volume and transient — expected when Frigate restarts or the broker blips.
No action beyond ensuring reconnection stays robust.

### 5. Telemetry quality gaps

- **No context on the worst failures.** The critical `classify_snapshot`
  `stage_failure` records carry an empty `sample_context_json` (`{}`), so there is
  nothing to diagnose *why* it failed — only that it did.
- **Severity is miscalibrated.** Normal filtering (`drop_filter_*`) is recorded at
  `warning`, the same tier as genuine transient failures, so severity cannot be used
  to triage.

## Recommendations (feed the pre-3.0 roadmap item)

1. **Reduce Frigate media-unavailability drops (finding 1).** Ensure the snapshot/clip
   is cached before the classify stage can drop it (close the
   `drop_classify_snapshot_unavailable` gap), and make the `frigate_missing` policy
   default to *keep* rather than *delete* so history is never silently lost. Surface
   the [Event Not Found guide](../troubleshooting/frigate-event-not-found.md) in-app
   when the rate is high.
2. **Push old installs off the critical build (finding 2).** Confirm `classify_snapshot`
   `stage_failure` is fixed on `2.11`+, and nudge `2.9.x`/`2.10.x` installs to update.
3. **Separate expected drops from problems (finding 3).** Classify `drop_filter_*` as
   informational, not health issues, so aggregates reflect real faults.
4. **Capture context for critical failures (finding 5).** Populate
   `sample_context_json` for stage failures (exception type, stage inputs) and
   recalibrate severity so it is usable for triage.
