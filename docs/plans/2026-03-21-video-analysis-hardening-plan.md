# Video Analysis Hardening Plan

**Date:** 2026-03-21
**Scope:** Fix two confirmed bugs and harden three failure modes identified from live container logs.

---

## Background

A database reset + backfill on 2026-03-21 exposed four distinct failure modes in the video analysis pipeline. Two are code bugs with clear fixes. Two are already handled gracefully but can be tightened. One (OpenVINO GPU recovery) is already fully implemented and needs no change.

---

## Issue 1 — OpenCV crash on stub clips in thumbnail generation [BUG — FIX]

### What happened
Frigate returns a 78-byte body for clips whose recordings were not retained (expired). The media cache stores this stub as a real file. When the user's browser requests `/api/frigate/{event_id}/clip-thumbnails.vtt`, `_ensure_preview_assets` in `proxy.py` finds the cached path (not `None`), skips the Frigate fetch, and passes the 78-byte file directly to `video_preview_service.generate()`. OpenCV crashes:

```
OpenCV(4.10.0) error: (-215:Assertion failed) number < max_number in function 'icvExtractPattern'
→ HTTP 500 on /clip-thumbnails.vtt
```

This cascades: the UI retries, hitting the same 500 repeatedly.

### Root cause
`_ensure_preview_assets` trusts that any cached `clip_path` is a valid MP4. There is no size or header guard before handing the file to OpenCV.

### Fix — `backend/app/routers/proxy.py`

After retrieving `clip_path` from the cache (line ~506), add a minimum-size check before calling `video_preview_service.generate()`:

```python
# After: clip_path = media_cache.get_clip_path(event_id)
if clip_path is not None:
    try:
        clip_size = os.path.getsize(clip_path)
    except OSError:
        clip_size = 0
    if clip_size < 1024:  # sub-1KB files are Frigate stub responses
        raise HTTPException(
            status_code=404,
            detail=i18n_service.translate("errors.proxy.clip_not_found", lang)
        )
```

Apply the same guard to the freshly-downloaded `temp_clip` path (after `tmp.write(resp.content)`) in the Frigate fetch branch, so stubs that arrive over the wire are also rejected before reaching OpenCV.

**Acceptance:** Requesting `/clip-thumbnails.vtt` for a stub-cached event returns 404, not 500. No OpenCV output in logs.

---

## Issue 2 — `existing_unknown` override fires with noise-level video scores [BUG — FIX]

### What happened
When a detection is "Unknown Bird", the video analysis override path (`existing_is_unknown`) unconditionally overrides with any video result, including scores as low as 0.05:

```
Video analysis overriding primary identification
  old_species=Unknown Bird  old_score=0.214
  new_species=Pheucticus melanocephalus  new_score=0.050  ← noise
  reason=existing_unknown
```

A Black-headed Grosbeak (NA species) at 0.05 is worse than "Unknown" — it adds a wrong species label with no useful confidence.

### Root cause
`detection_service.py` around line 379:

```python
elif existing_is_unknown:
    should_override = True          # ← no floor at all
    override_reason = "existing_unknown"
```

### Fix — `backend/app/services/detection_service.py`

Add a minimum confidence floor for unknown-upgrades. The intent of `existing_unknown` is "if we currently have no ID, a reasonable new result is always worth taking" — but "reasonable" must have a floor:

```python
elif existing_is_unknown:
    # Only upgrade from Unknown if the video result has some minimum confidence.
    # A floor of 0.1 keeps the permissive spirit (well below the main threshold)
    # while filtering out pure noise (e.g. 0.05 from blank/corrupt frames).
    _UNKNOWN_UPGRADE_MIN = 0.10
    should_override = video_score >= _UNKNOWN_UPGRADE_MIN
    override_reason = "existing_unknown"
```

If `should_override` is False here, execution falls through to the existing `if should_override:` block — nothing else needs changing. The log line for non-overrides already exists (`"Video analysis completed but did not override primary ID"`).

**Acceptance:** A video result at 0.05 against an Unknown Bird detection does NOT change the label. A result at 0.12+ still overrides as before.

---

## Issue 3 — Stub clips cached by the proxy clip endpoint [HARDEN]

### What happened
The clip proxy (`proxy_clip_start`) happily caches the 78-byte Frigate stub as a real clip. Subsequent requests for thumbnails then hit Issue 1.

### Current behaviour
The clip endpoint checks `if not resp.content:` (empty body), but 78 bytes passes that check. No MP4 header validation or minimum size check exists.

### Hardening — `backend/app/routers/proxy.py` (clip caching path)

Before calling `await media_cache.cache_clip(...)`, validate the response body:

```python
# Minimum valid MP4 is several KB. Frigate "not retained" stubs are ~78 bytes.
_MIN_VALID_CLIP_BYTES = 512

clip_body = response.content  # (or however the clip bytes are referenced)
if len(clip_body) < _MIN_VALID_CLIP_BYTES:
    raise HTTPException(
        status_code=404,
        detail=i18n_service.translate("errors.proxy.clip_not_found", lang)
    )
```

This prevents stubs from ever entering the cache, so Issue 1 can only arise from pre-existing stale cache entries (cleared on next cache reset).

**Acceptance:** Requesting a clip for an expired event returns 404 immediately. Nothing is written to the clip cache for sub-512-byte responses.

---

## Issue 4 — Snapshot admission pressure during bulk backfill [HARDEN]

### What happened
A 13-event backfill ran with 9 of 13 clips not retained. All 9 fell back to snapshot classification simultaneously. With `max_concurrent=1` for the image classifier, `admission_timeouts` reached 7 in under 10 seconds. Events retried at 0.5s / 1.0s and all eventually resolved — but the burst of admission failures generates misleading log noise.

### Current behaviour
This self-heals correctly. The retries (max 3, 0.5s / 1.0s back-off) are already implemented in `auto_video_classifier_service.py`.

### Hardening — `backend/app/services/auto_video_classifier_service.py`

Two targeted improvements:

**4a — Jitter on snapshot fallback start:** When a clip is confirmed not-retained and snapshot fallback begins, add a small random jitter (`0.0–0.5s`) before the first admission attempt. This de-synchronises workers that all hit "not retained" at the same instant during a bulk run:

```python
# In the snapshot fallback branch, before attempting admission:
if fallback_to_snapshot and len(repair_rows_being_processed) > 1:
    await asyncio.sleep(random.uniform(0.0, 0.5))
```

**4b — Log the admission timeout counter at WARNING only on first occurrence:** Currently every admission timeout is a WARNING. Change repeated timeouts within the same classification job to DEBUG after the first, so the logs stay useful without drowning in noise:

```python
if admission_timeouts == 1:
    log.warning("Image classification admission timed out...", ...)
else:
    log.debug("Image classification admission timed out (retry)...", ...)
```

**Acceptance:** During a 10-event bulk backfill with all clips expired, WARNING log count for admission timeouts drops to 1 per event (not 7 total). All events still resolve.

---

## Issue 5 — OpenVINO GPU transient CL_OUT_OF_RESOURCES [NO ACTION NEEDED]

### What happened
Two GPU crashes (`clFlush -5`, `clWaitForEvents -5`) occurred during the model reload triggered by the database reset cycle.

### Assessment
The classifier already implements full GPU restore logic:
- `_maybe_restore_gpu_provider()` with 120s cooldown (`CLASSIFIER_GPU_RESTORE_COOLDOWN_SECONDS`)
- Automatic fallback to ONNX Runtime CPU on failure
- GPU health tracking (`_gpu_invalid_retry_remaining`, `_runtime_gpu_restore_*` counters)
- Configurable via `CLASSIFIER_GPU_RESTORE_COOLDOWN_SECONDS` env var

Both failures recovered automatically within minutes (GPU was back for the manual reclassify at 09:02:37 and the ONNX CPU fallback served all backfill events at 09:04). No code change needed.

---

## Implementation Order

| Priority | Issue | File | Risk |
|---|---|---|---|
| P0 | Fix thumbnail 500 crash (Issue 1) | `routers/proxy.py` | Low — adds a guard, no behaviour change for valid clips |
| P0 | Fix `existing_unknown` score floor (Issue 2) | `services/detection_service.py` | Low — only affects Unknown Bird upgrades from video |
| P1 | Prevent stub caching (Issue 3) | `routers/proxy.py` | Low — only affects sub-512-byte responses |
| P2 | Snapshot backfill jitter (Issue 4a) | `services/auto_video_classifier_service.py` | Low — no functional change |
| P2 | Admission timeout log level (Issue 4b) | `services/auto_video_classifier_service.py` | Trivial |

Issues 1 and 2 are the only ones causing wrong data or user-visible 500 errors and should be fixed first.
