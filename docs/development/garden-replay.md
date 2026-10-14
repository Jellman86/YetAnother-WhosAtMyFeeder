# Replay Garden recordings without changing history

## Current motion collector

Use `replay_garden_motion.py` to test the current Cedar CPU worker on a complete
local recording. It covers every frame in consecutive windows of at most ten
seconds, including a short final window. **Detection still samples three frames
per window**, exactly as the worker does; this is not inference on every frame.
Brief animals or people between those samples can be missed.

Keep production settings unchanged. Run one native test at a time under an
external deadline, memory monitor and bird/camera-pressure guard. The tool does
not provide that supervisor. FFmpeg and the application's CPU dependencies must
already be available. Record the source URL, licence and checksum separately;
the tool accepts local files only and downloads nothing.

```bash
python backend/scripts/replay_garden_motion.py \
  --source /private/camera-recording.mp4 \
  --source-sha256 <verified-recording-sha256> \
  --model /private/models/md1000-cedar.onnx \
  --ffmpeg /usr/bin/ffmpeg \
  --thresholds 0.5 0.6 \
  --root /private/new-motion-report
```

The model must match the committed Cedar bundle. Sources are bounded to 256 MiB,
ten minutes, 120 fps and 16 megapixels. Each window retains the live worker's
16 MiB limit. FFmpeg copies video packets without scaling or re-encoding. Before
inference, every requested frame must decode to the same pixels and constant
frame-rate timing as the original. Unsupported seeks, variable timing, oversized
windows or incomplete decoding fail the run; the tool does not silently lower
quality or skip a tail. Bounded keyframe padding is allowed by the worker.

The new owner-only directory contains per-window results and `complete.json`
only after every window succeeds. A failed or interrupted run is incomplete.
Candidate results bind the original frame index, RGB/tensor hashes, normalized
box, threshold and actual CPU provider. Temporary clips/photos are removed on
normal exit; after an external interruption, remove only this run's temporary
files once its owned processes have stopped. Reports contain no retained photos.

This qualifies the detector in isolation. It does not exercise Frigate's
additional person-history veto, queue admission, review storage, species
identification, the UI or visit counting. Check those separately in disposable
state. Compare boxes to human annotations and review negatives; confidence is
not measured accuracy. Public camera-trap results do not establish Patio recall,
and repeated windows from one animal are correlated observations.

## Earlier classifier prototype

This developer tool evaluates local captures without connecting to MQTT, Frigate,
the application database, notifications or external reporting. It produces a
private report of **candidates that all need review**. It does not write to the separate [garden review history](../features/garden-animals.md)
or enable automatic species identification. Follow progress in
[#641](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues/641).

### Prepare the inputs

Use a disposable working directory and the existing provider runtime. Keep the
production bird detector and settings unchanged. Native inference needs an
external process deadline and resource monitor; a timeout inside a native call
cannot reliably stop that call. Run one replay process at a time on each host.

The model directory contains locally converted and independently checked files:

- `4.0.3a.onnx` and `4.0.3b.onnx`, with 2,498 ordered outputs.
- `mdv6-compact-640.onnx` and `mdv6-compact-1280.onnx`, the raw three-class
  one-to-many head. Segmentation and end-to-end exports are incompatible.
- `speciesnet.json`, containing ordered taxon identities, names, ranks, geofence
  rules, an ISO-3 country registry and the exact model checksums.

Generate the JSON bundle from the extracted official releases and verified local
exports. `countries.json` is an array of ISO-3 codes from a trusted country
registry. The builder refuses differing label order, taxonomy or geofences between
variants. It reads upstream label files only during preparation; replay uses JSON.

```bash
python backend/scripts/prepare_garden_model_bundle.py \
  --source /private/speciesnet-releases \
  --models /private/garden-models \
  --countries /private/countries.json
```

Put `manifest.json` beside the retained media:

```json
[
  {"id": "retained-cat-1", "camera": "patio", "label": "cat",
   "path": "cat.jpg", "box": [0.2, 0.3, 0.4, 0.5]},
  {"id": "offline-scan-1", "camera": "patio", "label": "animal",
   "mode": "scan", "path": "recording.mp4"}
]
```

An event uses its normalized XYWH tracked box. A scan uses a separate local
MegaDetector on sampled full frames. Scans do not imitate real MQTT arrivals or
provide object tracking. The original bird events should also be included with
their real `bird` label to verify they bypass garden inference. Do not relabel
them as mammal ground truth. Paths cannot escape the input directory. Identical
input IDs are deduplicated; conflicting metadata fails the replay.

### Run and review

Inside the externally supervised test process, run:

```bash
python backend/scripts/replay_garden_visitors.py \
  --root /private/new-garden-report \
  --inputs /private/patio-replay --models /private/garden-models \
  --provider intel_npu --variant 4.0.3a --detector-size 1280 \
  --camera patio --label animal --label cat --label dog --country GBR
```

Providers are `cpu`, `intel_cpu`, `intel_gpu`, `intel_npu` and `cuda`. The requested
provider must load; a missing CUDA/NPU cannot silently become CPU. Test both
classifier variants and detector sizes. RGB float32 NHWC classifier input uses
the upstream crop/resize and uint8 round-trip. The NumPy bilinear implementation
must be compared against upstream quantized inputs and predictions on each
artifact; it is not claimed bit-identical to PyTorch.

The new directory contains a mode-0600 `report.json`; an existing output directory
is never overwritten. The report records providers, checksums, timings, skipped
inputs and sampled observations. Observations are not visit counts. All candidates
remain marked for review, with single-frame support stated explicitly. Confidence
is a model score, not measured accuracy: a real Patio toy car produced a confident
cattle classification during development.

Each candidate separates its detection box from the actual classifier input, and
records source/frame hashes and the decoder's returned frame index. A whole-image
prediction never claims to have scored the animal box. The crop model's fallback
without a box carries an additional review reason.

Frigate `person`/`human` inputs bypass classification. In scans, any detected
person rejects the entire input. A human top result or significant human runner-up also
rejects it, including earlier animal candidates from that clip. Rejected people
leave only aggregate counters, without identity, frame, box or media in the
report. These checks depend on model recognition and do not guarantee that a
missed person is absent from the source footage. Source media remains private.

Bird predictions are excluded from garden candidates. Country filtering rolls
the winning species up its own ancestry; it never substitutes a local runner-up.
Higher taxa remain unresolved. No garden result reaches bird totals,
personalization, BirdWeather, eBird or notifications.

The intended camera control is **Garden animals** alongside the existing
**Feeder** and **Nest** choices, with independent garden opt-in so a mixed camera
can still record birds. The application collects completed Frigate animal events and offers explicit owner-requested
SpeciesNet suggestions, independently of this tool. The application requires a tracked
box for the crop variant; the replay’s explicitly marked whole-frame fallback is not
used there. The application's optional motion collector uses Cedar with bounded private
photo retention, separately from this replay. Automatic identification and local accuracy
qualification remain separate work.
