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

This is the expected behaviour for a brief or uncertain detection. You can tune Frigate's thresholds to reduce how often it occurs:

```yaml
# frigate config.yml — under objects > filters > bird
objects:
  filters:
    bird:
      min_score: 0.55       # raise to require higher raw confidence
      threshold: 0.75       # raise to require a higher confirmed median
      # min_initialized is derived from detect.fps, not set directly
```

Raising `detect.fps` gives the tracker more opportunities to accumulate frames, which helps confirm fast-moving birds. See the [Frigate object filters documentation](https://docs.frigate.video/configuration/object_filters/) for details.

---

## What YA-WAMF does about it

YA-WAMF caches the snapshot and clip to local storage the moment the MQTT event arrives, before any classification attempt. When the event precheck later returns `event_not_found`, YA-WAMF checks whether the clip is already cached:

- **Cached clip found** → classification proceeds using the local cache. The diagnostic entry will show reason code `precheck_cache_bypass`.
- **No cached clip** → the detection is marked as failed with error `event_not_found`.

The cached clip path takes precedence over a live Frigate fetch in all subsequent operations (manual reclassify, video analysis retry), so a detection that was cached before Frigate lost the event can still be classified successfully.

YA-WAMF can also mark existing detections as **Frigate event missing** during media integrity checks. This means YA-WAMF kept the local detection, but Frigate no longer had the event, clip, or snapshot at the last check. That can happen after normal Frigate retention cleanup, a Frigate database reset, storage repair, or a retention policy that is intentionally shorter than YA-WAMF's local retention.

You can control this in **Settings → Data → Media integrity**:

- **Mark missing and keep local data** keeps the detection and cached media, and shows the compact missing-Frigate note in the detection details.
- **Keep local data unchanged** leaves detections as-is even when Frigate no longer has the event/media.
- **Delete local data** removes local detections when Frigate no longer has the event/media.

---

## Checking whether this affected a specific detection

In the YA-WAMF **Errors** page, look for diagnostic entries with:

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
