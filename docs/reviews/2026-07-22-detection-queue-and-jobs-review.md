# Detection queue and Jobs review (2026-07-22)

## Outcome

YA-WAMF now has bounded work lanes, safe intake/shutdown ordering, restart recovery for automatic
video classification, idempotent modern BirdNET ingestion, and one owner-facing jobs snapshot. The
review covered live Frigate and BirdNET MQTT intake, automatic video analysis, high-quality snapshot
selection, full-visit generation, backfill status, classifier subprocess progress, the global
progress bar, and the Jobs workspace.

## Findings and resolutions

| Boundary | Previous risk | Resolution |
|---|---|---|
| BirdNET MQTT | Latest-only coalescing could discard distinct songs; broker redelivery could duplicate history. | A dedicated serial audio lane preserves every observation. Stable BirdNET IDs are scoped by source and enforced with a unique database identity; the live buffer applies the same identity. |
| Frigate MQTT | A pending end/update could overwrite a false-positive tombstone. Shutdown cancelled work before consumers finished. | False-positive state is dominant when pending payloads merge. Shutdown stops intake and drains handlers for up to 15 seconds before downstream workers stop. |
| Event lifecycle | A missed `new` event stayed missing even when the final event state arrived. Failures after the database commit could make a saved detection appear failed. | A final event recovers a missing detection from final state, bypassing only the live-staleness gate. Media, sublabel, notification, and follow-up scheduling failures are isolated after the durable save. |
| Automatic video | The queue existed only in memory. A restart lost pending/processing work. | Status is written as `pending` before memory admission. Startup and the watchdog reclaim pending/processing detections into the bounded queue. |
| Full-visit clips | One task was created per completed event. | Two workers consume a 128-item deduplicated queue. Existing reconciliation remains the fail-soft retry path. |
| HQ snapshots | The immediate queue was bounded but its overflow deque was not. | The lane has 32 immediate and 128 deferred positions, exposes deferral/rejection telemetry, and retains persistent bounded retry/reconciliation. |
| Classifier progress | Subprocess progress omitted `frame_offset_seconds`; async callback tasks were not owned by the supervisor. | Frame offsets now cross the worker protocol, and progress tasks are tracked and cancelled during supervisor shutdown. |
| Jobs UI | Browser-local events were treated as authoritative; queued work could look running; mixed job units could produce a misleading aggregate percentage. | `GET /api/jobs` provides server truth. Queue depth and worker concurrency are separate, queued status remains queued, and aggregation occurs only for one kind with one unit. |

## Failure and overload behaviour

- The detection row is the primary durable record. Automatic video work is reconstructed from its
  persisted classification status.
- HQ and full-visit work remain best-effort enhancements. Their queues are bounded; the original
  detection and available Frigate/cached media remain intact if an enhancement lane is saturated.
- BirdNET persistence is attempted before a normal observation is added to the correlation buffer.
  If storage is temporarily unavailable, the observation remains available for immediate
  correlation and a later broker redelivery is deduplicated in memory.
- The global progress banner intentionally excludes routine automatic media work. Owners can inspect
  every current lane in **Notifications & Jobs → Jobs**.

## Remaining scale boundary

The supported deployment is one YA-WAMF application container with SQLite. A separate durable broker
such as ARQ or Celery would add operational dependencies without improving this contract today. It
should be reconsidered only if YA-WAMF supports multiple backend replicas or work that must outlive
the detections database itself. Until then, bounded in-process executors plus persisted domain state
provide the smaller and more recoverable design.
