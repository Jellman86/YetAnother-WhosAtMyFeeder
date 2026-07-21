# Crop-detector candidate review

Date: 2026-07-21  
Status: Evidence-recovery fix implemented; D-FINE-N and DEIMv2-N screened; replacement not selected

## Decision

Do not replace the accurate YOLOX-Tiny detector from a generic object-detection leaderboard or one
successful frame. The first labelled distant-bird replay showed that the current model did localise
the bird, but its correct boxes scored `0.0264` and `0.0450`, just below YA-WAMF's normal `0.05`
automatic-replacement floor. The immediate defect was therefore the application gate, not a proven
model incapability.

YA-WAMF now admits accurate-detector boxes down to `0.02` only in multi-representation evidence
paths. The original full frame remains a peer candidate, and a low-confidence crop can win only
after the existing identity, quality, temporal-independence, and ambiguity gates. Thumbnail and
single-image replacement retain the normal `0.05` floor. This recovers small distant subjects
without making weak boxes authoritative.

A replacement remains worthwhile to investigate. It must beat Frigate's crop end to end on
manually labelled feeder visits, have a redistributable model contract, export reproducibly to a
runtime available in YA-WAMF's images, and fit its CPU/Intel/CUDA resource budgets. COCO AP is only a
shortlisting signal; the promotion measure is whether the active bird classifier identifies the
right species from the resulting crop.

## Frigate-guided challenger implementation

The field result also exposed an architectural mismatch: Frigate detects repeatedly inside square
motion/tracking regions, while the prior YA-WAMF path reduced an entire 2560×1920 frame to YOLOX's
416-pixel input. YA-WAMF now uses the same-frame Frigate box as a localisation hint, expands it to a
square high-resolution search region, runs YOLOX inside that region, and restores the selected box
to full-frame coordinates. Frigate's crop and the unchanged full frame remain independent peers;
the hint does not become model ground truth.

When a trustworthy hint is unavailable, native inference remains first. Only a native miss on a
sufficiently large frame activates four 20%-overlapping tiles, bounding both latency and false-positive
exposure. A detector box may be as small as 24 source pixels in this evidence path, but the
classifier crop retains at least 160 source pixels of surrounding context. Thumbnail/direct
replacement keeps the existing stricter policy.

The selection defect is also corrected. Detector confidence and a model-source bonus previously
could outweigh a better Frigate species-classifier score. They are now diagnostic only. A model
crop may replace an available Frigate crop only when both produce the same species and the model
improves classifier confidence by at least `0.02`; otherwise the best Frigate/full-frame baseline
wins. Deep-video consensus still collapses multiple representations from one frame before voting.

Every saved model candidate records `native`, `frigate_guided`, `sliced_2x2`, or `fast_native`
strategy provenance. The schema-3 private manifest records structured same-frame Frigate baselines
and only exposes owner-confirmed labels as promotion truth. The delivered
`eval_crop_strategy_challenger.py` harness produces downstream Frigate/model win/tie/loss, detector
p50/p95/max latency, strategy distribution, and hard-negative crop counts. Stale schemas,
duplicate cases or positive visits, ambiguous multi-box rows, and labels without owner-manual
provenance fail closed. This implementation creates a fair challenger path; it is not a
superiority claim until the owner-labelled Quark run clears the gate.

## Distant falcon replay

The manually identified Eurasian Sparrowhawk event `1784555940.484185-eocv7l` supplied two
independent 2560×1920 full frames. Frigate's default OpenVINO path is based on a 300×300
SSD-Lite MobileNet V2 model, so it is a useful production baseline rather than ground truth. Its
saved box was also used only as an approximate localisation reference; the species label came from
the owner's manual identification.

| Representation | Detector confidence, frame 994 / 1238 | Classifier score for `Accipiter nisus`, frame 994 / 1238 | Finding |
|---|---:|---:|---|
| Full frame | n/a | low-confidence wrong labels | Localisation is necessary at this distance. |
| Frigate saved crop | not preserved with the cached candidate | 0.7633 / 0.8668 | Good baseline; both frames correct. |
| Current YOLOX-Tiny, native full frame, normal floor | 0.0264 / 0.0450 | crop rejected before classification | The prior apparent model miss was a threshold miss. |
| Current YOLOX-Tiny, evidence-only floor | 0.0264 / 0.0450 | 0.7085 / **0.9800** | Both crops correct; the stronger frame beats Frigate. |
| Current YOLOX-Tiny, 2×2 sliced inference | 0.8163 / 0.8081 | 0.6948 / 0.8472 | Much higher detector confidence, but tighter geometry reduced downstream confidence and costs four detector calls. |
| YOLOX-S 640, exploratory native inference | 0.4609 / 0.6668 | 0.6288 / 0.9694 | Stronger detection confidence, but no downstream improvement on either frame. |

These two correlated frames are a regression case, not a promotion dataset. The sliced result is
particularly instructive: detector confidence and classifier usefulness are not interchangeable.
The exact sliced result remains a regression comparison. Production now permits a bounded 2×2
sliced fallback only after unguided native inference misses; it never displaces a valid native
result merely because its detector confidence is higher.

## Varied-panel and provider validation

Quark reran the corrected schema-3 provider sweep as run `20260721-154601` on the Intel image and
OpenVINO 2026.2.1. The automatic panel selected 24 taxonomy-verified images round-robin across
species and added three deterministic hard negatives. Image keys include their stable selection
index, so generic upstream names such as `image.jpg` cannot collapse distinct species into one
comparison row. The comparator also rejects incomplete or duplicated panels and ignores raw
proposals below the most permissive `0.02` policy that production can admit.

| Detector/provider | Median inference | Images / CPU agreement | Result |
|---|---:|---:|---|
| Fast SSD / CPU | 6.5 ms | 27 evaluated; 18/24 real images admitted | Valid CPU fallback. |
| Fast SSD / Intel CPU, GPU, NPU | n/a | compile failed | Remains CPU-only: OpenVINO rejects the artifact's inconsistent `QLinearConv` dequantisation dimensions. |
| Accurate YOLOX / CPU | 32.7 ms | 27 baseline images; 23/24 real images admitted | Valid baseline. |
| Accurate YOLOX / Intel CPU | 14.3 ms | 27/27 exact policy agreement | Valid. |
| Accurate YOLOX / Intel GPU | **10.7 ms** | 27/27 exact policy agreement | Valid and fastest on this sweep. |
| Accurate YOLOX / Intel NPU | 14.5 ms | 27/27 agreement; mean box IoU 0.999 | Valid. |

The same full run downloaded and executed all 12 registry classifiers over 254 images covering 112
species before the provider phase. Every declared classifier/provider combination compiled,
returned finite output, and matched its CPU policy result. The accurate crop runtime therefore
activates on Intel GPU on this host, while the fast quantised artifact remains an honest CPU
fallback rather than advertising an OpenVINO path it cannot compile.

A separate private replay used 30 independent cached events across seven recorded labels, including
distant/mid-distance and edge-of-frame subjects, plus 10 non-overlapping real feeder/foliage
regions and three synthetic negatives. Intel CPU, GPU, and NPU again matched CPU on all 43 cases.
At the safe `0.02` evidence floor, every provider admitted the same 6/30 positive crops and 0/13
negative crops. This proves hardware equivalence and safe threshold behaviour, not sufficient
far-subject recall. Most field labels and reference boxes are automatic/Frigate evidence rather
than owner-labelled ground truth, so the result cannot promote or reject a replacement model.

The low 6/30 admitted-crop count makes the next quality question sharper: a replacement candidate
must recover more distant subjects without creating feeder-clutter false positives, and its crops
must improve downstream species identification rather than detector confidence alone.

### Optimized-path challenger result

After implementing same-frame Frigate guidance and the bounded sliced fallback, Quark rebuilt the
private schema-3 panel and ran the end-to-end challenger over 30 independent positive visits and ten
real feeder/foliage/hardware negative regions. The active classifier was ConvNeXt Large on Intel NPU;
the accurate detector ran on Intel GPU and the fast fallback on CPU.

The optimized detector returned a candidate for 26/30 positives: 24 used `frigate_guided`, two used
`sliced_2x2`, and four ended in `fast_native`. The challenger applies the same additional 18% context
as the production HQ path. Across all 30 cases, seven model crops produced the
same classifier identity as Frigate with at least a `0.02` score gain, so the production guard would
promote them; 23 retained Frigate because the model was missing, changed identity, or did not clear
the gain. Only three visits currently carry owner-manual identities. Direct model-versus-Frigate
comparison on those was 1 win, 1 tie, and 1 loss, which demonstrates why detector output cannot be
authoritative. The production guard blocked the loss, yielding 1 win, 2 ties, and 0 losses.

Six of ten deliberately difficult negative regions produced low-floor detector candidates, but none
of their classifier results reached the active `0.40` minimum. These regions are non-overlapping
with the known event box rather than guaranteed bird-free scenes, so the raw count is diagnostic;
the high-confidence count and the retained full-frame/temporal gates are the safety measures. The
run validates the guarded pathway, not YOLOX superiority. More independent owner labels are still
required before a detector replacement or threshold change.

## External candidate screen

The first screen did not use the Sparrowhawk alone. It combined the private 30-event panel above
with eight committed labelled positives: four feeder captures (Blue Tit, pigeon, and robin) and four
clean references (American Robin, Blue Jay, Mallard, and Rock Pigeon). In total, candidate quality
was exercised on 38 positive images across clean-reference, near/mid/distant feeder, small-subject,
and edge-of-frame geometry plus 10 real feeder/foliage/hardware negative regions. The field panel's
seven recorded labels include Common Wood-Pigeon, Dunnock, Eurasian Blackbird,
Eurasian Collared-Dove, Eurasian Sparrowhawk, Great Thrush, and Unknown Bird.

Both candidates were exported locally from pinned official source revisions as static batch-one
ONNX graphs. The artifacts and private results remain only in the maintainer evaluation area; they
were not added to the registry, images, or GitHub release.

| Candidate | Pinned source | Checkpoint SHA-256 | Static ONNX SHA-256 |
|---|---|---|---|
| D-FINE-N | `Peterande/D-FINE@7fe2f8889f0b7b817f20c315b40fc15a4fb64ae6` | `41973938d2784d38a9836990d805b8392855ebf611aba55f0f7add90e110744c` | `1e026c9143606b2ecad694dbfe82c22a17e35ba561127669a9924d7db840cbea` |
| DEIMv2-N | `Intellindust-AI-Lab/DEIMv2@0fff8d4dcdc272e6cf2d84be31399db471357941` | `2ce67dc3535e345f6ac3f46e735bbc12a93c344aa46cb630f7a047089a88b7e9` | `0d4bc63f8aa633dca8e4d6e0de19d1610dbb0fcc8df39c8f32b636e722703856` |

The table below uses each candidate's most permissive predeclared threshold with zero detections in
the 10 real negative regions. Thresholds are model-specific and not comparable as confidence
probabilities. The current YOLOX row uses its production evidence-only `0.02` floor.

| Model / operating point | Public labelled positives: detected / IoU≥0.3 / IoU≥0.5 | Field positives: detected / IoU≥0.3 / IoU≥0.5 | Field false positives |
|---|---:|---:|---:|
| Current YOLOX-Tiny / `0.02` | 7 / 3 / 2 of 8 | **6 / 4 / 2 of 30** | **0 / 10** |
| D-FINE-N / `0.30` | 7 / 3 / 2 of 8 | 2 / 1 / 0 of 30 | 0 / 10 |
| DEIMv2-N / `0.20` | 8 / 3 / 2 of 8 | 3 / 2 / 0 of 30 | 0 / 10 |

Lowering the candidate floors did not produce a safe win. D-FINE-N at `0.10` reached five field
IoU≥0.3 matches but also detected birds in 4/10 negative regions; at `0.05` it still had five matches
and fired in all 10 negatives. DEIMv2-N at `0.10` reached two matches with 1/10 negatives and at
`0.02` reached five matches with 9/10 negatives. These figures score the highest-confidence bird
box that production would select; the result JSON also preserves any-candidate IoU as a diagnostic
for selection-policy research. Neither candidate clears the localisation/specificity gate,
so running downstream classification on its crops cannot produce promotion evidence and was
deliberately deferred.

| Candidate/provider | Compile | Median field inference | Safe-point CPU agreement | Result |
|---|---:|---:|---:|---|
| D-FINE-N / ONNX CPU | 162.4 ms | 27.8 ms | baseline | Valid. |
| D-FINE-N / Intel CPU | 554.2 ms | **15.7 ms** | 40/40 presence; mean paired top-box IoU 1.000 | Valid. |
| D-FINE-N / Intel GPU | 829.5 ms | 16.5 ms | 40/40 presence; mean paired top-box IoU 0.985 | Valid at the safe point; borderline scores diverge at lower floors. |
| D-FINE-N / Intel NPU | n/a | n/a | compiler process exit 139 | Invalid on the current Quark/OpenVINO stack. |
| DEIMv2-N / ONNX CPU | 191.5 ms | 37.2 ms | baseline | Valid. |
| DEIMv2-N / Intel CPU | 589.6 ms | 16.8 ms | 40/40 presence; mean paired top-box IoU 1.000 | Valid. |
| DEIMv2-N / Intel GPU | 2327.0 ms | **16.4 ms** | 40/40 presence; mean paired top-box IoU 0.992 | Valid at the safe point; borderline scores diverge at lower floors. |
| DEIMv2-N / Intel NPU | n/a | n/a | compiler process exit 139 | Invalid on the current Quark/OpenVINO stack. |

The NPU result was retested with a true static batch-one export after the official dynamic graph
first failed on an unbounded batch dimension; both static graphs still terminated inside the Intel
NPU compiler. This is candidate-specific: the current accurate YOLOX artifact passes on the same
NPU. Quark has no NVIDIA device, so this run makes no CUDA performance claim.

This is a screening result, not a final statistical model comparison. The public boxes are manually
curated, while most private field boxes and labels are same-frame Frigate/automatic evidence rather
than owner ground truth. It is strong enough to reject promotion of these exact artifacts, but the
final detector decision still requires owner-labelled visits and downstream Frigate win/tie/loss
analysis for any candidate that clears this first gate.

## Candidate shortlist

The candidates below use official project results to choose what is worth exporting and testing.
Reported AP and accelerator latency are not YA-WAMF performance claims and are not comparable with
Quark until the exact exported artifacts pass the on-hardware harness.

| Priority | Candidate | Why it is worth testing | Constraint before promotion |
|---:|---|---|---|
| 1 | **D-FINE-N** | 4M parameters, 7 GFLOPs, and 42.8 COCO AP in the official model zoo. Its official N checkpoint and static ONNX export now run on CPU and Intel GPU. | **Screened, not promoted:** no safe field recall gain and current Intel NPU compiler exit. Retain as reproducible negative evidence; do not distribute until weight terms are independently confirmed. |
| 2 | **DEIMv2-N** | 3.6M parameters, 6.8 GFLOPs, and 43.0 COCO AP; its official N checkpoint and static ONNX export now run on CPU and Intel GPU. | **Screened, not promoted:** no safe field recall gain and current Intel NPU compiler exit. Retain as reproducible negative evidence; do not distribute until weight terms are independently confirmed. |
| 3 | **RTMDet-Tiny** | 4.8M parameters, 8.1 GFLOPs, and 41.0 COCO AP; a promising accuracy/size step over YOLOX-Tiny. MMDeploy officially targets ONNX Runtime and OpenVINO. | Use the Apache-licensed MMDetection/MMDeploy route, not the GPL MMYOLO application package, and reproduce post-processing exactly. |
| 4 | **PP-YOLOE+ S** | 7.93M parameters, 17.36 GFLOPs, and 43.7 COCO AP in PaddleDetection's official table, with an official export workflow. | Export and validate without adding Paddle to runtime images; check NMS/output portability and exact weight licence. |
| 5 | **RT-DETRv2-S** | 48.1 COCO AP and official ONNX Runtime, TensorRT, OpenVINO, and sliced-inference support. It is a useful higher-accuracy ceiling. | 20M parameters/60 GFLOPs makes it a likely optional accurate tier, not a universal default. |
| 6 | **RF-DETR Nano** | 48.4 COCO AP at 384×384, official ONNX export, and explicitly Apache-designated Nano weights. | Much larger parameter/download footprint than the first four candidates; benchmark compile time, memory, static batching, and OpenVINO compatibility. |
| 7 | **MegaDetector** | Wildlife-specific animal detector trained on millions of camera-trap images; domain relevance may beat COCO models on partially hidden birds. | The maintained project points to third-party ONNX conversions and detects the broad `animal` class. Do not distribute an unverified conversion; first reproduce/export an artifact with clear provenance. |

YOLOX-S remains a useful benchmark control, but it is not a release candidate today. The official
code is Apache-2.0, while an open upstream question still asks whether the linked pretrained weights
share those redistribution terms. It also failed to improve downstream classification in the first
field replay. Ultralytics YOLO releases are excluded from this redistributable shortlist because
their standard open-source route is AGPL rather than the project's permissive licensing baseline.

Primary sources:

- [Frigate object-detector and current ONNX export guidance](https://docs.frigate.video/configuration/object_detectors/)
- [D-FINE official model zoo](https://github.com/Peterande/D-FINE)
- [RTMDet official results](https://github.com/open-mmlab/mmyolo/blob/main/configs/rtmdet/README.md) and [MMDeploy backends](https://github.com/open-mmlab/mmdeploy/blob/main/docs/en/02-how-to-run/convert_model.md)
- [PaddleDetection PP-YOLOE+ results](https://github.com/PaddlePaddle/PaddleDetection/blob/release/2.8.1/configs/ppyoloe/README.md)
- [DEIMv2 official model zoo](https://github.com/Intellindust-AI-Lab/DEIMv2)
- [RT-DETR official model zoo and deployment support](https://github.com/lyuwenyu/RT-DETR)
- [RF-DETR official model zoo and licence matrix](https://github.com/roboflow/rf-detr)
- [MegaDetector official project](https://github.com/agentmorris/MegaDetector)
- [SAHI sliced-inference reference](https://github.com/obss/sahi)
- [YOLOX official results](https://github.com/Megvii-BaseDetection/YOLOX) and [unresolved pretrained-weight licence question](https://github.com/Megvii-BaseDetection/YOLOX/issues/1865)

## Promotion benchmark

Hardware equivalence is now part of the normal model-evaluation sweep. For each installed exact
crop artifact it selects up to 24 real images round-robin across the downloaded species panel, adds
three deterministic hard negatives, isolates each provider in a subprocess, and compares finite
output, detection presence, top-box IoU, and confidence with CPU. The result is stored under the
separate `crop_detectors` key in schema-3 `device_matrix.json`; it cannot pollute classifier accuracy
or setup-model recommendations. A passing current-image record may select the fastest crop runtime,
with automatic CPU demotion on compile or inference failure.

That sweep establishes hardware agreement only. It does not make a model-quality promotion decision.

The next crop-detector decision must use visit-level ground truth rather than treating several
frames from one event as independent evidence. Build a private Quark manifest with at least:

- 30 manually labelled independent visits across near and distant camera geometry;
- 10 empty or hard-negative scenes, including foliage, reflections, feeder hardware, and motion;
- daylight, low light, occlusion, small birds, large birds, and edge-of-frame subjects;
- the full frame, Frigate box/crop, and source event/time provenance for every case.

For each candidate, preserve the full frame and compare native, evidence-floor, and (where
appropriate) bounded sliced inference. Report:

1. downstream species top-1 correctness and confidence from the active classifier;
2. useful-crop recall at tolerant IoU 0.3, clipping rate, and false detections per empty image;
3. Frigate win/tie/loss counts at the visit level, with confidence intervals;
4. median/p95 crop-detector latency, peak memory, compile time, and artifact size on CPU, Intel GPU,
   Intel NPU, and CUDA where packaged and supported;
5. failures, non-finite output, CPU top-1 disagreement, and fail-soft fallback behaviour.

Promote only when a candidate improves manually labelled downstream identification over Frigate
without a meaningful false-positive or recall regression, stays within the selected tier's resource
budget, and has a reproducible permissively redistributable artifact. A new detector never removes
the full-frame peer, Frigate hint, or original-image fallback.

## Follow-up implementation order

1. Retain the evidence-only `0.02` recovery and collect outcome telemetry through existing candidate
   provenance; do not lower the normal automatic-replacement threshold.
2. The crop benchmark now includes structured Frigate baselines, owner-label provenance, downstream
   classifier outcomes, strategy provenance, latency, and hard-negative counts. Collect enough
   owner-labelled visits and run it before changing the default model contract.
3. D-FINE-N and DEIMv2-N screening is complete and neither exact artifact passes. Export and
   benchmark RTMDet-Tiny next, then PP-YOLOE+ S. Test one higher-accuracy DETR only if the
   lightweight set does not clear the Frigate gate.
4. Bounded 2×2 slicing is implemented only after an unguided native miss. Retain it only if the
   visit-level benchmark shows a net downstream gain that justifies the four extra calls.
