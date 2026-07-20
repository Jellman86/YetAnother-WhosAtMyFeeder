# Image classification pipeline review — 2026-07-20

## Scope and method

This review follows a detection from Frigate MQTT admission through snapshot classification,
Frigate sublabel fallback, audio correlation, persistence, high-quality snapshot refinement, and
deep-video classification. It also covers inference admission, TFLite/ONNX/OpenVINO runtime
boundaries, cached recording media, recovery after restart, and the model registry contracts that
control preprocessing and providers.

The review used repository tests, the Quark runtime symptoms recorded during the investigation,
and primary upstream contracts:

- [Frigate MQTT events](https://docs.frigate.video/integrations/mqtt/) publish `new`, `update`, and
  `end` events and represent a scored sublabel as `[label, score]`; `top_score` remains the tracked
  object's detector score.
- [Frigate object classification](https://docs.frigate.video/configuration/custom_classification/object_classification/)
  requires a per-attempt threshold plus at least three attempts and 60% label consensus.
- [Frigate event snapshots](https://docs.frigate.video/integrations/api/event-snapshot-events-event-id-snapshot-jpg-get/)
  apply query parameters only while an event is in progress; after it ends, the saved snapshot
  configuration determines whether the returned image is cropped.
- [Frigate's sublabel API](https://docs.frigate.video/integrations/api/schemas/eventssublabelbody/)
  accepts labels up to 100 characters and a separate `subLabelScore`.
- [TensorFlow's integer quantization contract](https://blog.tensorflow.org/2019/06/tensorflow-integer-quantization.html)
  defines real values as `(integer - zero_point) * scale`; input and output quantization metadata
  therefore cannot be ignored for signed-int8 models.

## Conclusions

The overall architecture is sound: live work has priority-aware admission, model preprocessing is
registry-driven, asynchronous video analysis has separate diagnostic fields, and automatic crop
refinement is already conservative. The review nevertheless found several cross-path correctness
failures. The common theme was not model accuracy but **evidence provenance**: object score,
sublabel score, visual score, audio score, single-frame score, and manual identity were sometimes
treated as though they were interchangeable.

The fixes below keep those evidence types separate and prefer abstention over an unjustified
species change. They do not alter provider declarations or per-model crop contracts; those remain
empirical outputs of the hardware/model validation harness.

## Findings and implemented corrections

### 1. Manual identity could be overwritten by later automation — critical, fixed

Both a higher-scoring live upsert and an asynchronous video/HQ result could replace a user's manual
species correction. A service-level read was not sufficient because a manual correction could land
between that read and the automatic write.

The repository now guards automatic identity writes in the same SQL statement with
`manual_tagged = 0`. Video results are still saved in the dedicated video-analysis columns for
diagnostics, but primary species, taxonomy, and confidence remain untouched. An explicit manual
reclassification can still override and atomically sets the manual flag.

**Second-order consequence:** automatic evidence is not discarded merely because it disagrees
with a person; it remains inspectable without becoming canonical truth. Context enrichment of an
already-manual row may wait for a dedicated context-only path rather than risking an identity
write through the generic upsert.

### 2. Frigate object confidence was being used as species confidence — high, fixed

Frigate's `top_score`/object `score` describes the bird detector, while the second element of
`sub_label` describes the sublabel classifier. The previous path could use the object score to
admit a species fallback or make a disagreement harder to overturn.

YA-WAMF now parses plain, list, tuple, mapping, and JSON-encoded sublabels into an explicit
`label + optional score` value. Live and backfill paths pass that score separately. Deep-video
disagreement policy no longer consults object confidence. When YA-WAMF writes a local result back
to Frigate it sends the full label (within Frigate's 100-character contract) and a separate score.

**Second-order consequence:** historical plain-string sublabels remain usable when the owner has
enabled trust, but they have no measured confidence. Their stored score is a policy admission floor,
not a reconstructed model measurement. New Frigate payloads preserve the real score.

### 3. Trusted Frigate labels bypassed the local model — high, fixed

Trusting Frigate previously short-circuited snapshot inference. This saved compute but also blocked
YA-WAMF's selected model from correcting stale or lower-quality upstream enrichment.

The local model now runs first. A trusted Frigate sublabel is used only when media is unavailable,
the local runtime returns no result, or the local prediction fails the configured policy. A result
that originated from Frigate is never written straight back to Frigate.

**Second-order consequence:** installations with trusted sublabels will perform more local
inference. The work still uses the bounded live admission path, so overload sheds work instead of
growing an unbounded queue.

### 4. MQTT updates could not recover a missed `new` event — high, fixed

Frigate documents repeated `update` messages as a tracked object improves. YA-WAMF previously
dropped all updates, so a transient snapshot or runtime failure during `new` could permanently lose
the visit.

`update` is now a recovery signal: the processor checks the database first, ignores it when the
detection already exists, and retries the normal pipeline only when the event is still missing.
Duplicate in-flight work remains coalesced.

**Second-order consequence:** recovery adds a cheap indexed database read for update messages but
does not repeatedly reclassify established detections.

### 5. Video soft voting was vulnerable to a single-frame outlier — high, fixed

A maximum/average probability aggregation can be dominated by one excellent but incorrect frame,
especially for distant birds, motion blur, or a transient second bird.

Deep video now uses a pure temporal policy: at least three valid frames must be evaluated; hidden
or low-confidence predictions count as abstentions; a species needs at least two supporting frames
and 60% of all evaluated frames; and reported confidence is the median of supporting frames.
Non-species classes are masked before voting. Support/evaluated counts are attached to results.

The input representation is now part of the same policy. Every sampled frame retains the unchanged
full frame and can add one valid Frigate-box crop plus one detector crop. Each representation builds
its own temporal consensus, so two transformations of one frame never become two votes. If
trustworthy representations select different species, video analysis abstains; if they agree, the
strongest consensus wins. The persisted result records the exact input source.

**Second-order consequence:** very short, visually ambiguous, or representation-sensitive clips now
abstain instead of producing a plausible-looking answer. Evaluating up to three bounded
representations costs more inference per sampled frame, but runs in the background and retains the
full frame even when a crop detector is available. The original snapshot classification remains
available and the video job can still report completion without replacing the primary species.

Snapshot fallback now also carries durable provenance. Known cache metadata is preserved; an
ended Frigate event is never assumed to honour a live crop request; and legacy cache entries with
unknown provenance are treated as uncropped. The detection detail UI labels snapshot fallbacks as
single-frame results rather than implying that temporal video evidence produced them. Media-cache
metadata describes the bytes actually retained, while classification provenance follows any
additional Frigate-hint or detector crop that reached model preprocessing. Historical backfill uses
the same ended-event rule instead of marking every returned snapshot as cropped.

### 6. HQ snapshot selection could promote a tiny or inconsistent crop — high, fixed

The old selector preferred any generated crop over a full high-quality frame. Candidate inference
also called the synchronous classifier directly, bypassing the background admission/supervisor path
and failing in subprocess mode.

Candidate scoring now uses the supervised background classifier and the active model's normal input
contract. Ranking combines classifier evidence with sharpness, usable exposure, resolution, crop
confidence, and a small crop-source bonus. Crops must retain usable source detail and match the
known detection identity; before an identity exists, the same crop label must appear on two
independent frames. The full frame competes in the same pool and is retained in the bounded saved
candidate set even when many crops rank above it.

The Quark review then exposed a second-order sampling defect: a 10.09-second, 300-frame event clip
produced candidate offsets `0.000`, `0.034`, and `0.067` seconds because the first promising target
was expanded to its immediate neighbours before the three-frame limit was applied. HQ sampling now
keeps the best centre/track-weighted target and distributes the other evidence slots across the
visible path interval. A hard 250 ms temporal boundary is enforced again at consensus time, and
neighbours are decode fallbacks within one slot rather than votes. Frigate's event box is translated
to the nearest timestamped path point; it is withheld for recording clips whose start time cannot be
proven against the event timeline.

**Second-order consequence:** crop source is no longer a user preference masquerading as quality.
A clear full frame can beat a poor crop, while a distant but consistent crop can still win. Short
visits that cannot provide two separated moments now abstain instead of manufacturing consensus;
recording-frame hint crops also abstain when their timeline cannot be aligned. Automatic
classification refinement remains stricter than image selection and cannot replace a conflicting
known species or manual tag.

### 7. Playable partial recording clips were deleted and fetched forever — high, fixed

Quark exposed the concrete failure: Frigate returned a playable 17-second recording for a requested
28-second window; YA-WAMF deleted it as too short and retried every reconciliation cycle.

The cache now distinguishes **partial but measurable** media from corrupt/stub media. A partial clip
is retained and may feed video/HQ work; an unmeasurable clip is not accepted merely because its file
size is non-zero. Full-visit reconciliation stops fetching once a usable partial exists.

Manual temporal reclassification now applies that same contract end to end. An explicit video
request is no longer short-circuited by a confident snapshot preflight, and stale Frigate
`has_clip` metadata cannot hide a locally retained full-visit clip. Candidate resolution proceeds
from complete recording to decodable partial recording, cached event clip, and live Frigate event
clip. A corrupt cached candidate is removed without preventing the next source from being tried;
only exhaustion of usable video activates snapshot fallback.

HQ recovery now also persists event-scoped retry state across restarts. Failures back off for five,
fifteen, and forty-five minutes and become terminal on the fourth failed attempt. Successful manual
or automatic generation clears the failure. State is isolated from species data and cascades away
when its detection is deleted.

**Second-order consequence:** a partial visit has less temporal coverage but is strictly better than
discarding all usable evidence. Manual Reclassify can consume the same retained bytes the owner can
play even after Frigate retention expires, while still refusing a file that exists but cannot be
decoded. Terminal recovery does not prevent an owner from explicitly regenerating the snapshot
after upstream media becomes available.

### 8. Runtime failures could look like valid empty classifications — high, fixed

ONNX Runtime exceptions were swallowed into `[]`, preventing the existing provider-recovery policy
from distinguishing “no prediction” from a failed execution provider. ONNX execution and output
shape failures now raise the typed inference error used by fallback/circuit logic; preprocessing
errors remain outside provider recovery so malformed input does not unnecessarily remount a model.

TFLite signed-int8 input/output now applies declared scale and zero point, supports per-class output
scales, and fails explicitly when signed integer tensors omit required quantization metadata. The
legacy uint8 raw-byte fallback remains for older models that do not publish metadata.

**Second-order consequence:** runtime faults become visible and recoverable, while unsupported
quantized artifacts fail validation instead of silently returning confidently wrong species.

### 9. Audio confirmation replaced the visual confidence — medium, fixed

Audio and image scores come from different models and are not calibrated onto one probability
scale. The prior correlation path could replace a visual score with BirdNET-Go confidence.

Audio confirmation now preserves the visual score and records `audio_species`/`audio_score` as
independent supporting evidence.

**Second-order consequence:** notification and promotion thresholds continue to mean visual-model
confidence. A future combined score requires a labelled calibration set and an explainable fusion
policy; taking `max`, averaging, or multiplying the two numbers would overstate certainty.

## Deliberate non-changes and remaining validation

- **No automatic confidence fusion.** This remains a roadmap research item until it can be
  calibrated against labelled visual/audio pairs.
- **No unvalidated provider flags.** Intel GPU/NPU/CUDA support stays per model and per host. A
  successful compile alone is insufficient; finite output, CPU agreement, and latency must pass the
  hardware harness before changing registry or installed sidecar providers.
- **No global threshold rewrite.** Registry recommendations inform video frame admission, but the
  owner's configured threshold remains the primary live-policy boundary. Changing it automatically
  would silently alter notification volume and historical comparability.
- **Output semantics remain a model contract.** Current ONNX/OpenVINO registry artifacts are
  validated as logits. A future model that exports probabilities must declare that explicitly and
  gain a conformance test before activation; guessing from numeric range is unsafe.
- **Crop thresholds need fleet evidence, not generic tuning.** The first distant Quark replay below
  confirms that the new quality/identity gates fail safely, but one event is not a calibration set.
  Any adjustment should use saved candidates and top-frame outcomes across near and distant visits
  rather than changing per-model crop configuration from one anecdotal frame.

## Quark live validation — 20 July 2026

The fixed worker was deployed through Dockhand as the Intel runtime image at dev commit `f4c5290`.
Runtime diagnostics reported image flavor `intel`, selected and active provider `intel_npu`, an
OpenVINO backend, CPU/Intel CPU/GPU/NPU packaged, and no provider mismatch or fallback. The active
ConvNeXt model completed five NPU inference samples with no failure during the replay.

Detection `1784561844.911783-4k90r6` provided a direct regression case. Before deployment its saved
candidate slots were frames 0, 1, and 2 at 0.000, 0.034, and 0.067 seconds. After explicit HQ
regeneration they were frames 1, 104, and 207 at 0.034, 3.498, and 6.962 seconds. The pairwise
separation assertion passed, proving that adjacent decode fallbacks no longer become independent
votes.

Both the 8.1 MB cached event clip and 17.6 MB cached full-visit recording remained range-readable.
The accurate crop detector was installed and healthy but found no valid model crop for this distant
subject. Visual review showed the Wood Pigeon in the far-left hedge of the selected 2560×1920 frame;
the two available Frigate-hint crops contained foliage and scored below the full frame. YA-WAMF
therefore retained the centre-weighted full frame, recorded `insufficient_evidence`, and left the
un-tagged detection as Unknown Bird because no second independent frame supported the weak 0.305
Wood Pigeon result. That is the intended best-available-media and safe-abstention outcome.

## Verification requirements

The implementation is covered by focused tests for manual-write races, Frigate payload variants,
update recovery, temporal consensus, HQ identity/quality selection, admission, ONNX provider
failure, int8 quantization, partial/corrupt clips, and persistent retry state. Dev commit `f4c5290`
passed the full backend and frontend suites, repository-wide Ruff lint/format, reversible Alembic
upgrade/downgrade/upgrade, migration path checks, all four x86 runtime-image startup checks, the
full → CPU → full persistence gate, and the live Quark observation above. Release acceptance still
requires the same checks to pass for the exact annotated release tag before mutable stable tags are
promoted.
