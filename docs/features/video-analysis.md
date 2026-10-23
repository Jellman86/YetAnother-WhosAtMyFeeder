# Deep Video Analysis

**Deep Video Analysis** samples multiple frames from a clip and checks whether their
identifications agree. It can provide clearer evidence when a snapshot is blurred or the bird
is partly hidden. If neither the video nor the snapshot fallback provides sufficient evidence,
YA-WAMF keeps the existing identification.

## Check a photograph and count the birds

Video identification, the displayed photograph and additional birds in a capture are separate
outcomes. A completed species analysis does not prove that a suitable new photograph was found.

- **Best available event snapshots** in **Settings → Data → Snapshot quality** controls automatic
  photo work. Owner-selected photos and explicit species corrections remain protected.
- **Automatically find additional birds** in that section is off by default, including on
  upgrade. Normal identification and target-photo selection still work when it is off.
- **Find more birds** scans one retained whole frame. **Scan again** repeats a scan without changing
  the chosen photo or the capture's primary identification, and keeps corrections and exclusions.
  An empty retry preserves earlier counted-bird records.
- When a large detector box encloses several smaller regions, those regions might
  be separate birds or parts of one bird. The scan reports that it could not
  distinguish them and keeps existing findings. This is not a zero count; try
  another retained whole frame. Species confidence alone cannot resolve the count
  because a crop can include a nearby bird.
- The scan reports queued and running states separately, then **find**, **name**, **count** and
  **save** progress. A waiting scan shows how many scans are ahead; a running button says
  **Scanning…**. A failed scan is distinct from a photo that has never been scanned.
- **Regenerate snapshots and recount birds** rebuilds available photo choices and checks their
  birds again. A failed or empty generation keeps saved choices. **Needs your call** offers the
  species picker and **Skip for now** when a person is needed.

See [Explorer and reviewing visits](explorer.md) for the viewing and correction workflow.

## How it works

YA-WAMF waits briefly for Frigate to finish a new clip. It prefers a usable cached full-visit
recording, then a partial recording, then an event clip, before asking Frigate for media. Missing
video has bounded retries and a snapshot fallback. A shorter, decodable clip remains useful evidence.

The default is **15 frames**, configurable under **Settings → Detection**. Each sampled moment can
provide a full-frame view, a timestamp-aligned Frigate crop and detector crops. Those are alternate
views of one moment, not extra votes. A result needs repeated confident support; reliable tracked
geometry and repeated evidence for the event's bird take priority over another bird in the scene.
Unresolved source disagreement causes abstention.

The first saved classification or an explicit owner species choice can guide target selection,
but cannot force a result without video support. A borrowed Frigate sublabel is not an independent
model prediction. Old visits without preserved initial evidence still use available geometry and
consensus; YA-WAMF does not invent their original classification.

**Score again** requests a model decision. It does not turn the output into a human species choice
or erase an explicit choice. A below-threshold or abstaining run tries the retained snapshot; if
neither route qualifies, it keeps the identification and reports **No confident result**.

### Photograph progress

Photo work can reuse the winning decoded frame to avoid decoding it again. Invalid or unavailable
reusable data falls back to decoding. The job says **Updating photograph** while that work finishes,
and completion waits for its outcome. Owner photo choices, corrections, hidden/blocked visits and
storage eviction are checked before a replacement is saved.

## Running an Analysis

Open a detection and select **Score again**. The same detail view also carries **Confirm
<species>**, **Pick a different species**, and **Edit name** for correcting an identification by
hand, and **Ask AI Naturalist** for the behavioural note. When an event clip or fetched full-visit
clip is available, YA-WAMF performs temporal video analysis; it does not replace that explicit video run
with a faster snapshot-only result. If the video is unavailable, cannot form a safe consensus, or
only produces a below-threshold candidate, it explains the downgrade and uses the best cached or
Frigate snapshot as a fallback.

The action is admitted to the same bounded queue as live and maintenance video work, returns
immediately, and deduplicates by event. The Jobs view is authoritative for queued/running progress.
Temporal inference always runs in a supervised subprocess; cancellation or a hard timeout
terminates that worker, so native OpenVINO/ONNX work cannot continue invisibly after the request
ends.

A replaced worker returns unfinished work to the queue for at most two retries. Queued work waits
for the replacement; exhausted retries fail visibly. Check **Notifications → Jobs** and a fresh
[diagnostics bundle](../troubleshooting/diagnostics.md#capture-current-evidence-for-a-report) when a
worker repeatedly restarts.

This source selection is independent of stale Frigate metadata. If the detection says its event
clip is gone but YA-WAMF can still play a cached full-visit recording, the **Score again** action uses
that recording. Completing a cached-video run also replaces any obsolete `event_not_found` status
with the result of the new attempt.

## Visual Feedback

A queued capture keeps its photograph and says **Video analysis queued**. When a worker has
started but frame progress has not arrived, the record says **Preparing video analysis**.
Neither state reports an estimated frame count or an execution device.

Once live frame progress arrives, a real-time **progress overlay** appears. It shows:

- How many frames have been processed so far
- The current leading species based on frames analyzed so far
- A progress bar counting toward the total frame count

Once complete, the detection card updates only when a result clears both temporal and promotion
rules. An unchanged outcome reports how many independent moments could vote, how many supported the
leading species, and how many matches were required. A snapshot downgrade remains visible;
exhaustion of both media routes is an unchanged result, while an unrecovered media/runtime fault is
an explicit failure.

**Notifications → Jobs** includes automatic and maintenance video work, delayed media retries and
worker recovery. **Queued** means no worker has started yet. Unfinished automatic work is reclaimed
after a container restart. Use its **Health · Diagnostics export** link to
[capture a fresh support bundle](../troubleshooting/diagnostics.md#capture-current-evidence-for-a-report).
Missing recordings and temporary Frigate outages have bounded retries; they do not start endless
recovery loops.

## Settings

| Setting | Location | Description |
|---------|----------|-------------|
| **Frame count** | Settings → Detection | Number of frames sampled per clip (default: 15). Higher values sample more of the clip but take longer and do not guarantee a better identification. |

Video-job concurrency follows `CLASSIFICATION__BACKGROUND_WORKER_COUNT` (one worker when
unset), with one clip per worker. The legacy `video_classification_max_concurrent` setting is
ignored. See [Maintenance concurrency](../setup/configuration.md#maintenance-concurrency).

Live snapshot work takes priority over new video starts. **Settings → Health** reports queue
counts, waiting ages and active phases. Queue relief and pressure counters describe scheduler
observations, not accelerator utilization or proof that a job succeeded; check its stored result.

## Requirements

A missing clip is a media-availability problem; it does not establish an inference failure. Check
the recording configuration on the specific camera, including after changing its power or network
connection. A working live stream or snapshots do not prove that Frigate recorded a clip.

- Enable recording and an FFmpeg `record` role on every analyzed camera. Event clips need retained event footage. **Full-visit clips** additionally require positive `record.continuous.days` (at least `1` in the example configuration); alert/detection retention alone cannot guarantee that longer window.
- The active model must be downloaded. Deep Video Analysis uses the same model as real-time detection.

See the [Recommended Frigate Config](../setup/frigate-config.md) for the exact recording settings needed.

## Keeping the photo aligned

A replacement needs both localized bird presence and species evidence for the accepted identity.
A species score alone cannot prove a bird is visible, so successful classification does not
guarantee a new photo. A matching, checked HQ photo stays selected; otherwise the selected video
moment can supply a suitable crop even when optional HQ scanning is off.

An abstaining run may repair a misleading automatic crop without changing the species. A whole-scene
fallback shows context without claiming the accepted species was found there. Owner-selected photos,
manual identifications, hidden/blocked visits and storage eviction remain protected. Failed extraction
keeps the current photo and does not discard a successful classification.

`bird_presence_unconfirmed` means no suitable localized photograph was found. A completed miss does
not rescan the same media on a timer; an explicit scan or final-event refresh can try again.
`media_cache_unavailable` means the media directory could not be written. Temporary inference
failures, deferred work and missing clips have distinct bounded retry paths.

### Earlier photograph choices

A new scan keeps its generated choices plus up to eight earlier choices. The
earliest recorded photograph, the previously displayed photo, the owner's
selected photograph and scenes used by
persisted bird observations are protected. A kept crop retains its matching
whole frame for comparison. These protections can take the total above eight;
the limit does not reduce the birds counted in a capture or the current scan.

Earlier choices are trimmed when a new set is saved, not at startup. Media already removed by
storage eviction cannot be restored by this photo-history protection; see
[retention boundaries](favourites.md#retention-boundaries).
