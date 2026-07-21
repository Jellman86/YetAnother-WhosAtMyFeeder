# Crop-detector candidate review

Date: 2026-07-21  
Status: Evidence-recovery fix implemented; replacement model not yet selected

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
Sliced inference remains a benchmark variant and is not enabled in production.

## Candidate shortlist

The candidates below use official project results to choose what is worth exporting and testing.
Reported AP and accelerator latency are not YA-WAMF performance claims and are not comparable with
Quark until the exact exported artifacts pass the on-hardware harness.

| Priority | Candidate | Why it is worth testing | Constraint before promotion |
|---:|---|---|---|
| 1 | **D-FINE-N** | 4M parameters, 7 GFLOPs, and 42.8 COCO AP in the official model zoo. The project has an ONNX exporter, and current Frigate documentation independently demonstrates the same exporter with S/M/L Objects365→COCO weights. | Confirm the N export rather than assuming the S/M/L recipe, add a strict output adapter, pin source revision/checksum, verify weight terms, then measure ONNX/OpenVINO providers on Quark. |
| 2 | **DEIMv2-N** | 3.6M parameters, 6.8 GFLOPs, and 43.0 COCO AP; Pico is an even smaller 1.5M/5.2-GFLOP fallback. Current Frigate docs include DEIMv2 ONNX export guidance. | Newer deployment surface with less field history; require static-shape ONNX, bounded memory, and provider conformance before wider testing. |
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
2. Extend the crop benchmark so external detector adapters, Frigate baselines, empty scenes,
   downstream classifier outcomes, and per-provider latency share one versioned result format.
3. Export and benchmark D-FINE-N first, then DEIMv2-N, RTMDet-Tiny, and PP-YOLOE+ S. Test one
   higher-accuracy DETR only if the lightweight set does not clear the Frigate gate.
4. Consider bounded slicing only for large frames whose native detector result is uncertain, and
   only if the visit-level benchmark shows a net downstream gain that justifies the extra calls.
