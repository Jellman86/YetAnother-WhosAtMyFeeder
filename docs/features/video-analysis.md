# Deep Video Analysis

**Deep Video Analysis** samples multiple frames from a clip and checks whether their
identifications agree. It can provide clearer evidence when a snapshot is blurred or the bird
is partly hidden. If neither the video nor the snapshot fallback provides sufficient evidence,
YA-WAMF keeps the existing identification.

## How It Works

1. The backend resolves the best local video first: a complete cached full-visit recording, a
   decodable partial recording, then the cached event clip. It asks Frigate for the event clip only
   when no usable local copy exists. Each candidate is decoded before inference; an invalid cached
   file is removed and resolution continues instead of falling straight back to a snapshot.
2. It uses deterministic, centre-weighted stratified sampling. Event clips retain their first/last
   boundaries and place the remaining samples through the central half, where the tracked subject is
   most likely to be useful. Longer recording clips keep roughly 70% uniform coverage and spend the
   remaining samples in that central region. The default is **15 frames**, configurable in
   **Settings → Detection**.
3. Each frame is evaluated as a full frame and, when valid, with independent Frigate-hint and
   detector-crop representations that match the active model's input contract.
4. Each representation must form its own temporal consensus across multiple frames. At least two
   confident moments must vote, and one species must own at least 60% of those confident votes.
   Samples less than 250 ms apart collapse into one moment, and every winning source needs three
   independent evaluated moments. Decoded frames below the confidence floor prove source coverage
   but do not vote against a fleeting visitor. A detector crop can win from sparse recurring
   evidence without occupying a fixed percentage of a long visit. A reliable tracked-object crop
   has priority over a different bird elsewhere in the frame. Otherwise, two separated, confident
   identifications of the initial event species keep that target ahead of a scene winner; a weak
   guess or single glimpse does not. Without either anchor, conflicting source winners cause an
   abstention instead of adding misleading extra votes. When a frame has no valid hint,
   video inference checks up to three distinct native detector crops per sampled frame. This is one
   native detector pass, without tiled scanning or retries, but may add two species-classifier
   calls. A guided detector miss in an otherwise valid box also permits that native pass, because
   the bird may already have left the hinted position.
5. A video result must still clear the configured promotion threshold before a user-requested run
   can replace the stored identification. If temporal evidence abstains or stays below that
   threshold, YA-WAMF tries the best retained snapshot. If neither route has usable evidence, it
   returns **No confident result**, preserves the existing identification, and records no manual
   override.

The first saved classification is retained separately from later labels. Repeated analysis uses
that initial classification as a soft prior, or an explicitly confirmed or chosen species.
Clicking Reclassify requests a model decision and does not turn its output into a human
species choice or erase a previous explicit species choice. Another confirmation or manual
species choice replaces that prior. The existing manual lock still protects both actions from automatic changes.
A prior is not proof of which bird Frigate tracked and cannot force a result without repeated
confident video support. A genuinely wrong initial label can still change. The first saved classification may have used a trusted Frigate sublabel as a snapshot
fallback. A sublabel can also be YA-WAMF's own earlier write-back, so it is not proof of
independent species evidence. Video runs do not add the current Frigate sublabel as another
prior.

Existing visits without preserved initial classification remain unknown; migration does not
copy a possibly overwritten current label into their history. They still use available tracked
geometry and temporal consensus. Diagnostics report whether the species prior came from the
initial classification, an explicit manual correction or was unavailable. Native multi-crop
search does not require a species prior; older and Unknown visits keep the same bounded
search. Duplicate ingestion and a backfill with a different model do not rewrite the initial
classification. A downgrade removes this new provenance while preserving detections;
re-upgrading cannot recover that discarded provenance.

For retained full-visit recordings, a Frigate event box is used only at sampled timestamps that
match the event's tracked `path_data`. YA-WAMF never repeats one static event box across the whole
recording after the bird has moved away. Full-frame and detector-crop evidence remain available
when tracked coordinates are absent.

## Running an Analysis

Open a detection and select **Reclassify**. The same detail view also carries **Confirm
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

The worker is not the visit. A video worker is judged alive on its own heartbeat budget
(`CLASSIFICATION__VIDEO_WORKER_HEARTBEAT_TIMEOUT_SECONDS`, thirty seconds by default, because a
temporal analysis is one long native job), and the video hard deadline still ends one that has truly
hung. When a worker is replaced mid-analysis, whatever the reason, the visit in hand goes back on the
queue after a short pause and runs again on the fresh worker, twice at most, with its durable status
returned to **pending** so a process restart in the gap recovers it like any other queued visit.
Work queued while the replacement loads waits for it rather than being handed to the dead worker.
Only when those attempts are spent is the visit marked failed with the worker's reason, and a
manual request then falls back to the retained snapshot as before. Every worker kill is logged with
the numbers it rested on (seconds since the last heartbeat, activity and stderr, time in the
request, restarts in the window), so a false positive can be told from a hung worker afterwards.

A shorter-than-requested full-visit clip remains valid evidence when it is a real, decodable MP4.
YA-WAMF analyzes the frames it contains instead of discarding the clip merely because Frigate could
not provide the ideal window.

This source selection is independent of stale Frigate metadata. If the detection says its event
clip is gone but YA-WAMF can still play a cached full-visit recording, the Reclassify action uses
that recording. Completing a cached-video run also replaces any obsolete `event_not_found` status
with the result of the new attempt.

## Visual Feedback

During analysis, a real-time **progress overlay** appears on the detection card. It shows:

- How many frames have been processed so far
- The current leading species based on frames analyzed so far
- A progress bar counting toward the total frame count

Once complete, the detection card updates only when a result clears both temporal and promotion
rules. An unchanged outcome reports how many independent moments could vote, how many supported the
leading species, and how many matches were required. A snapshot downgrade remains visible;
exhaustion of both media routes is an unchanged result, while an unrecovered media/runtime fault is
an explicit failure.

The owner **Jobs** view also shows automatic and maintenance video work from the backend. A queued
item remains labelled **Queued** until a worker starts it, and pending/processing automatic jobs are
reclaimed from the detections database after a container restart. Frame progress sent by a
subprocess retains the sampled frame number and exact clip offset, so saved top-frame evidence can
be traced back to the media position that produced it.

Scheduled analysis of unknown detections waits for Frigate's API to become available during a
stack restart. If an entire precheck batch fails transiently, YA-WAMF leaves those detections
eligible and retries up to five times at two-minute intervals. A later daily cleanup will try
again if Frigate remains unavailable. Transient precheck errors are not queued as video jobs.

## Settings

| Setting | Location | Description |
|---------|----------|-------------|
| **Frame count** | Settings → Detection | Number of frames sampled per clip (default: 15). Higher values sample more of the clip but take longer and do not guarantee a better identification. |

Video-job concurrency follows `CLASSIFICATION__BACKGROUND_WORKER_COUNT` (one worker when
unset), with one clip per worker. The legacy `video_classification_max_concurrent` setting is
ignored. See [Maintenance concurrency](../setup/configuration.md#maintenance-concurrency).

## Requirements

- `record: enabled: True` must be set in your Frigate config, every analyzed camera needs an FFmpeg input with the `record` role, and `continuous.days` must be at least `1` so the recording exists when analysis runs. Alert/detection retention alone only preserves matching event segments and cannot guarantee the complete analysis window.
- The active model must be downloaded. Deep Video Analysis uses the same model as real-time detection.

See the [Recommended Frigate Config](../setup/frigate-config.md) for the exact recording settings needed.

## Keeping the photo aligned

After video analysis, a replacement photo uses an exact sampled frame and crop where
an object detector localized a bird and the species model supported the accepted species.
Object confidence and species confidence are checked separately. Weak exploratory detector
proposals still help classification but cannot select the photo. This step reuses localization
from the video analysis, decodes one previously analysed moment and performs no additional
inference. It works when optional high-quality photo scanning is disabled.

HQ scanning reuses its existing detector work to check the chosen full frame or crop. A
matching, checked HQ photo remains selected when its retained bytes match the displayed photo;
that check happens before another video decode. Older HQ choices without sufficient object
localization may be replaced once by a suitable video crop. The initial and previous photos
remain available through the normal retention rules.

HQ and baseline photo changes use the same species-confidence floor: the configured classification
threshold or 60%, whichever is higher. A photo must support the current accepted species; a weaker
HQ candidate cannot displace a stronger baseline photo and then be replaced on every repeated check.

If no suitable localized photo is available, YA-WAMF keeps the current photo and records
`bird_presence_unconfirmed`. This includes an absent or disabled crop detector, detector misses
and cases where no localized crop supports the accepted species. A species score alone cannot
prove that a bird is visible. Small or partly hidden birds can be missed, and an object detector
can still mistake background for a bird. Classification success therefore does not guarantee
a new photograph. A completed scan with no suitable localized bird does not repeatedly
rescan the same media on a timer; an explicit new scan or final-event refresh can try again.
Disabled media caching, disabled snapshot caching and unavailable cache storage are reported
separately. A persisted replacement needs writable snapshot caching; analysis does not silently
change those settings. Missing clips retain their bounded availability retries. A temporary detector or species-inference
failure, or deferred work while live processing is busy, also retains bounded retries with a distinct
reason. These are incomplete scans, not confirmed presence misses. Classification refinement remains
independent of photo eligibility. Owner choices and corrections are checked again before saving.

Automatic photo changes respect manual identifications and photo choices, hidden
visits, blocked species and storage eviction. A rejected video result cannot
replace the photo with a different species. Later routine Frigate snapshot writes
update event hints without overwriting a retained refined photo. Extraction
failures preserve the current photo and do not discard a successful classification.

### Earlier photograph choices

A new scan keeps its generated choices plus up to eight earlier choices. The
earliest recorded photograph, the previously displayed photo, the owner's
selected photograph and scenes used by
persisted bird observations are protected. A kept crop retains its matching
whole frame for comparison. These protections can take the total above eight;
the limit does not reduce the birds counted in a capture or the current scan.

Content hashes avoid rereading every saved JPEG to check for duplicates. Older
rows without a hash receive at most eight byte comparisons per update. Files
removed from the photo list are pruned only after the replacement commits.
Existing choices are trimmed when a new photo set is saved, not at startup.
Photographs already removed by storage eviction cannot be restored by retention.

Older installations may have equal creation times for several photos because
previous saves reset those times. Their exact original order cannot be recovered;
Frigate photographs are preferred when choosing the protected comparison.
