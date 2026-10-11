# Frigate "Event Not Found" Explained

YA-WAMF occasionally records a detection as `event_not_found` — meaning it received a Frigate MQTT event for a bird, but when it then queried Frigate's HTTP API for event metadata or the video clip, Frigate returned a 404.

A 404 does not by itself identify a classifier fault or prove that the bird never existed. Check
the exact event ID, camera and time before changing detection thresholds.

## Check the event and media separately

1. Open the same tracked event in Frigate. An MQTT tracker ID may arrive before metadata or media
   is available, or may no longer exist after retention, a database reset or storage changes.
2. Check the camera's current snapshots and recording configuration. A live stream and a saved
   snapshot do not establish that a recording clip exists. See the
   [recommended Frigate recording setup](../setup/frigate-config.md).
3. Check YA-WAMF's retained media. A cached event clip or full-visit recording can remain usable
   after Frigate removes the event. A file must decode successfully to support inference.
4. Capture a fresh [diagnostics bundle](diagnostics.md#capture-current-evidence-for-a-report) after
   reproducing the problem. Include recent network, camera power or storage changes and distinguish
   a 404 from a connection timeout or service-unavailable response.

YA-WAMF retries transient event/media availability within bounded limits. It cannot create a clip
that Frigate never recorded or recover an expired snapshot that it did not retain. A missing
snapshot can prevent initial classification; a missing video on an existing visit does not erase
that visit's identification. Do not reset the database to repair missing media.

## Tune Frigate only after checking the evidence

Frigate's `min_score` rejects individual weak detections; `threshold` evaluates its score history
to decide whether a tracked object is a true positive. A higher threshold can miss real birds,
and a lower threshold admits more false positives. Neither control guarantees a stored clip.
See [Frigate's object-score filters](https://docs.frigate.video/configuration/object_filters/) and
[MQTT event contract](https://docs.frigate.video/integrations/mqtt/) for your installed version.

YA-WAMF has its own species-confidence and admission rules. They cannot guarantee that every
false positive admitted by a lower Frigate threshold is rejected. Change one setting at a time
and inspect new tracked events, their snapshots and retained clips before changing more.

Frigate may also lose and reacquire the same bird as a new track. In that case YA-WAMF can retain
the original MQTT tracker ID while the Frigate history contains a nearby event with a different ID.
YA-WAMF does not silently substitute the nearby ID: two close tracks can represent different birds,
so timestamp proximity alone is not a safe identity rule.

---

## What YA-WAMF does about it

YA-WAMF retains available media during normal processing, subject to its media settings, writable
storage and upstream availability. It cannot guarantee that every incoming tracker already has a
local snapshot and clip. When the event precheck returns `event_not_found`, it checks for retained
video before giving up on that source:

- **Cached clip found** → classification proceeds using the local cache. The diagnostic entry will show reason code `precheck_cache_bypass`.
- **No cached clip** → automatic video work records `event_not_found`; an owner-requested job
  continues with the best snapshot after its bounded retry.

Local video takes precedence over a live Frigate fetch in all subsequent operations (manual
reclassify, video analysis retry), so a detection that was cached before Frigate lost the event can
still be classified successfully. Manual video reclassification tries a complete cached full-visit
recording, a decodable partial recording, the cached event clip, and finally Frigate's event clip.
The ideal duration controls full-visit completeness, not whether retained frames are valid
classification evidence. If one cached file is corrupt, YA-WAMF removes that candidate and tries
the next source before considering a snapshot fallback.

For an owner-requested reclassification, failure of the event precheck or any video source is not
terminal by itself. The bounded video job preserves the manual request across the delayed Frigate
race retry, broadcasts a video-to-snapshot strategy change, and classifies the best cached or live
snapshot. Automatic video work still records an unavailable clip without silently changing its
configured strategy unless that caller explicitly enabled snapshot fallback.

The player and classifier therefore share the same retained-media principle even though they have
different validation needs: a file must be decodable for inference, not merely present on disk. A
successful cached-video attempt clears an obsolete `event_not_found` classification error.

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
**Notifications → Errors** view (and in health telemetry) you may see any of these:

| Reason code | Component | What it means | Detection kept? |
|---|---|---|---|
| `precheck_cache_bypass` | event processor | The event was gone from Frigate, but YA-WAMF had cached the clip and classified from it. | ✅ kept |
| `event_not_found` | event processor / video | Frigate had no event and no cached copy existed. | ⚠️ classify failed |
| `drop_classify_snapshot_unavailable` | event processor | No snapshot could be fetched from Frigate and none was cached in time, so the detection was **dropped** before classification. | ❌ **dropped** |
| `clip_not_found` / `clip_not_retained` | video analysis | The event clip is not (or no longer) available in Frigate. Manual analysis visibly falls back to the best snapshot; automatic work records the unavailable video according to its fallback policy. | ✅ kept |
| `snapshot_fetch_failed` | video analysis | Neither a retained nor an upstream snapshot could be loaded for fallback classification. The job fails visibly without pausing other jobs through the inference circuit. | ✅ kept |
| `video_precheck_snapshot_fallback` | video analysis | Frigate could not supply the event/video, so an owner-requested job continued from the best snapshot. | ✅ kept |
| `frigate_missing_marked` | frigate-missing policy | A stored detection was flagged because Frigate no longer has its event/media (see Media integrity above). | ✅ kept |
| `frigate_missing_deleted` | frigate-missing policy | A stored detection was **deleted** because Frigate no longer has it and the policy is set to delete. | ❌ **deleted** |

The two that lose data — `drop_classify_snapshot_unavailable` (a live detection
dropped) and `frigate_missing_deleted` (a stored detection removed) — are the ones
worth acting on. For snapshot failures, verify camera snapshots and reachability while the event is still
available. For deletion by policy, select **Mark missing and keep local data** or **Keep local
data unchanged** before the next integrity pass. Changing a policy does not restore rows already
permanently deleted.

Missing events, clips and snapshots do not count as inference circuit failures. Worker crashes
and inference timeouts still count, including when a snapshot fallback cannot recover the job.

## Checking whether this affected a specific detection

In the YA-WAMF **Notifications → Errors** view, look for the reason codes above. For example:

- `reason_code: precheck_cache_bypass` — classification succeeded from local cache despite `event_not_found`
- `reason_code: event_not_found` — classification failed because there was no cached copy either

You can also inspect the detection directly via the API:

```bash
curl -fsS http://localhost:9852/api/events/{id}
```

A detection affected by this scenario will have:
- `has_frigate_event: false`
- `has_clip: true` (if YA-WAMF cached the clip in time)
- `video_classification_status: "failed"` or `"completed"` (depending on whether the cache bypass succeeded)
