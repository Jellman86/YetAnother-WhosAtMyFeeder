# Frigate "Event Not Found" Explained

YA-WAMF occasionally records a detection as `event_not_found` — meaning it received a Frigate MQTT event for a bird, but when it then queried Frigate's HTTP API for event metadata or the video clip, Frigate returned a 404.

This is not a bug in YA-WAMF. It is a known characteristic of how Frigate handles short or low-confidence detections. There are two distinct causes.

---

## Cause 1 — MQTT fires before Frigate commits to its database (race condition)

Frigate publishes MQTT messages in near-real-time as detections occur. However, Frigate's internal database write happens asynchronously after the MQTT publish. In practice, there is a brief window (usually under a second) during which the MQTT message has been delivered but the event does not yet exist in Frigate's API.

YA-WAMF is designed to tolerate this: it retries the event lookup several times with short delays before giving up. If the event appears within the retry window, classification proceeds normally.

---

## Cause 2 — The bird did not accumulate enough frames to be confirmed

Frigate uses a multi-stage confidence gate before writing an event to its database:

| Setting | Default | Purpose |
|---|---|---|
| `min_score` | `0.5` | Raw detection score required to begin tracking |
| `min_initialized` | ~½ × frame rate | Consecutive frames required for the tracker to initialise |
| `threshold` | `0.7` | Median score across tracked frames required for DB confirmation |

A detection only becomes a persistent Frigate event (visible in the API and UI) once all three gates are cleared. However, **Frigate publishes MQTT regardless**, even for transient detections that will never reach the database.

If a bird passes through frame quickly — fewer frames than `min_initialized` requires — Frigate sends the MQTT message, YA-WAMF receives it and caches the snapshot and clip immediately, but Frigate's event API returns 404 because the event was never written to its database. No clip file will exist in Frigate's media storage either.

This is expected Frigate behaviour, not a fault. How you tune it depends on **what you want** — and the two goals pull in opposite directions, so it is easy to change the wrong knob.

### First, understand the three gates

- **`min_score`** (per-frame, default `0.5`): a single frame scoring below this is discarded and never tracked.
- **`min_initialized`** (default **½ × `detect.fps`**): consecutive frames an object must be detected before Frigate *starts tracking* it (and publishes MQTT). Setting this **below** the default makes very brief blips become tracked objects — they fire MQTT (so YA-WAMF processes them) but frequently never persist.
- **`threshold`** (median score, default `0.7`): the **median** across the object's tracked frames must cross this before Frigate *saves the object as an event* in its database.

An object fires MQTT once it is tracked (`min_score` + `min_initialized`), but only becomes a persistent, API-visible event once its **median** crosses `threshold`. A brief visit can fire MQTT yet never cross `threshold`, giving `event_not_found`.

> ⚠️ **Common trap:** raising `threshold` does **not** reduce `event_not_found` — it *increases* it, because more tracked objects fail to reach the higher median bar and are never saved.

### If you want fewer, higher-confidence detections

Stop fleeting/weak objects from being tracked at all, so they never fire MQTT:

```yaml
# frigate config.yml — per camera
detect:
  min_initialized: 5     # require more frames before tracking (≈ ½ fps at fps 10)
objects:
  filters:
    bird:
      min_score: 0.5      # discard weaker per-frame detections
```

This removes brief fly-throughs entirely — you will not see them in YA-WAMF either.

### If you want to keep brief visits (recommended for a feeder)

Keep tracking sensitive, but **lower `threshold`** so briefly-tracked birds cross the median bar and Frigate saves them as real events:

```yaml
# frigate config.yml — per camera
detect:
  min_initialized: 2     # keep tracking brief objects
objects:
  filters:
    bird:
      min_score: 0.45     # allow fainter per-frame detections
      threshold: 0.5      # persist brief objects instead of dropping them
```

Trade-off: a lower `threshold` admits more marginal detections. YA-WAMF's own classifier and the **Minimum audio/visual confidence** settings then filter what is kept, so the noise does not reach your history.

`detect.fps` interacts with all of this: at a higher fps a brief bird accumulates its `min_initialized` frames sooner (5 frames = 0.5 s at 10 fps vs 1 s at 5 fps), so genuine quick visits confirm faster. Frigate recommends `fps: 5`; raise it only if your hardware has detection headroom. See the [Frigate object filters documentation](https://docs.frigate.video/configuration/object_filters/) and [detect configuration](https://docs.frigate.video/configuration/detect/).

Whichever you choose, YA-WAMF still caches the snapshot and clip the moment the MQTT event arrives, so a brief visit is classified even when Frigate never persists the event.

Frigate may also lose and reacquire the same bird as a new track. In that case YA-WAMF can retain
the original MQTT tracker ID while the Frigate history contains a nearby event with a different ID.
YA-WAMF does not silently substitute the nearby ID: two close tracks can represent different birds,
so timestamp proximity alone is not a safe identity rule.

---

## What YA-WAMF does about it

YA-WAMF caches the snapshot and clip to local storage the moment the MQTT event arrives, before any classification attempt. When the event precheck later returns `event_not_found`, YA-WAMF checks whether the clip is already cached:

- **Cached clip found** → classification proceeds using the local cache. The diagnostic entry will show reason code `precheck_cache_bypass`.
- **No cached clip** → the detection is marked as failed with error `event_not_found`.

The cached clip path takes precedence over a live Frigate fetch in all subsequent operations (manual reclassify, video analysis retry), so a detection that was cached before Frigate lost the event can still be classified successfully.

The reverse mismatch is also possible: Frigate can contain a persisted event that YA-WAMF did not
ingest, for example while YA-WAMF was stopped or restarting. An owner-triggered detection backfill
can import those persisted Frigate events while their snapshots remain available. Backfill cannot
create an event for a transient MQTT tracker ID that Frigate never persisted.

YA-WAMF can also mark existing detections as **Frigate event missing** during media integrity checks. This means YA-WAMF kept the local detection, but Frigate no longer had the event, clip, or snapshot at the last check. That can happen after normal Frigate retention cleanup, a Frigate database reset, storage repair, or a retention policy that is intentionally shorter than YA-WAMF's local retention.

You can control this in **Settings → Data → Media integrity**:

- **Mark missing and keep local data** keeps the detection and cached media, and shows the compact missing-Frigate note in the detection details.
- **Keep local data unchanged** leaves detections as-is even when Frigate no longer has the event/media.
- **Delete local data** removes local detections when Frigate no longer has the event/media.

> ⚠️ **"Delete local data" is destructive and irreversible.** Frigate routinely
> rotates events out of its own (often short) retention, so this option can quietly
> discard bird detections that YA-WAMF classified perfectly well and still has cached
> media for. Because it keys off Frigate's retention — not yours — it can delete far
> more than you expect. Prefer **Mark missing and keep local data** (or **Keep local
> data unchanged**) unless you specifically want YA-WAMF's history tied to Frigate's.

---

## Related reason codes

`event_not_found` is one of a family of Frigate media/event conditions. On the
**Errors** page (and in health telemetry) you may see any of these:

| Reason code | Component | What it means | Detection kept? |
|---|---|---|---|
| `precheck_cache_bypass` | event processor | The event was gone from Frigate, but YA-WAMF had cached the clip and classified from it. | ✅ kept |
| `event_not_found` | event processor / video | Frigate had no event and no cached copy existed. | ⚠️ classify failed |
| `drop_classify_snapshot_unavailable` | event processor | No snapshot could be fetched from Frigate and none was cached in time, so the detection was **dropped** before classification. | ❌ **dropped** |
| `clip_not_found` / `clip_not_retained` | video analysis | The event clip is not (or no longer) available in Frigate. Video analysis is skipped; snapshot classification is unaffected. | ✅ kept |
| `frigate_missing_marked` | frigate-missing policy | A stored detection was flagged because Frigate no longer has its event/media (see Media integrity above). | ✅ kept |
| `frigate_missing_deleted` | frigate-missing policy | A stored detection was **deleted** because Frigate no longer has it and the policy is set to delete. | ❌ **deleted** |

The two that lose data — `drop_classify_snapshot_unavailable` (a live detection
dropped) and `frigate_missing_deleted` (a stored detection removed) — are the ones
worth acting on. Both are reduced by the same steps: make sure `snapshots` are
enabled in Frigate for the camera, keep the brief-visit tuning above so more objects
persist, and set the Media integrity policy to **keep**.

## Checking whether this affected a specific detection

In the YA-WAMF **Errors** page, look for the reason codes above. For example:

- `reason_code: precheck_cache_bypass` — classification succeeded from local cache despite `event_not_found`
- `reason_code: event_not_found` — classification failed because there was no cached copy either

You can also inspect the detection directly via the API:

```bash
curl http://localhost:9852/api/events/{id}
```

A detection affected by this scenario will have:
- `has_frigate_event: false`
- `has_clip: true` (if YA-WAMF cached the clip in time)
- `video_classification_status: "failed"` or `"completed"` (depending on whether the cache bypass succeeded)
