# Garden motion sampling comparison, 27 October 2026

## Decision

Keep live collection at three samples per window and preserve the existing
thresholds. Nine samples recover a proposal missed by three in the separate
0.5-threshold diagnostic, but **neither policy produces a candidate at Quark's
0.63 collection threshold** on this input. This is evidence of a sampling limit,
not qualification of denser collection or a reason to lower confidence.

The [machine-readable evidence](2026-10-27-garden-motion-sampling.json) contains
the source URLs, licences, checksums, decoder receipts and complete worker results.
It contains no photographs or production records.

## Input and limits

The input is the previously explored INBO MUNTJAC_ANTWERP v2 event
`a793a344-9f37-4d7e-8969-924b51e2b6dc`, externally labelled
`Erinaceus europaeus`. Its human annotation declares a classification probability
of **0.5** and behaviour `onduidelijk`; treat it as a tagged example, not verified
species truth or an independently annotated animal box.

All 20 public 1920 × 1080 JPEG packets were copied into a ten-second, 2 fps MJPEG
montage. The original timestamps contain duplicates and two bursts spanning
15 seconds. The montage preserves image order and compressed packets, **not the
original camera timing**. Each replay verified that all 20 remuxed frames decoded
identically to the montage before inference. JPEG video and still-image decoders
can differ, so this run's bound RGB/tensor hashes and scores are distinct evidence
from the [earlier still-image experiment](2026-10-24-garden-automatic-accelerators.md).

Source: [INBO v2 archive](https://ipt.inbo.be/archive.do?r=muntjac_antwerp&v=2),
MUNTJAC_ANTWERP, Bram D'hondt, Jim Casaer and contributors, INBO. Metadata is
CC0 1.0 and public media is CC BY 4.0. Per-image URLs and hashes are in the
evidence file. No source photographs were added to the repository.

## Execution

The published CPU image at revision `babc6235196b6193bf4e943291a3d2e309418c47`
ran its own `replay_garden_motion.py` and packaged worker on a separate x86_64
WSL2 development host. The immutable platform digest was
`sha256:5f2630f6d9b3c445534a491f003a9f89074ce24bbe1339e90fd6ce73c9d98508`.
Cedar matched the committed bundle checksum. Python was 3.12.16, OpenCV 4.10.0
and ONNX Runtime 1.31.1; the successful proposal reported `CPUExecutionProvider`.
A checksum-verified portable FFmpeg 7.0.2 supplied the tool's external prerequisite.
The application code and model were not overlaid or modified.

Each policy ran alone in a disposable, read-only container with two CPUs, a
4 GiB memory cap, no network or GPU access and a 45-second external deadline.
Only the public input, read-only model, FFmpeg and private output directory were
mounted. The application entrypoint, database, configuration and notifications
were not started. All four runs exited zero without OOM; owned containers were
removed. Caps are configured limits, not measured peak resource consumption.

An earlier bounded Quark attempt stopped and reaped its worker when production
Garden work started. Its settings and both existing native incident records were
preserved. A first isolated attempt lacked FFmpeg and stopped before inference;
a fresh run supplied that prerequisite. Neither attempt is a model result.

## Results

Frame indices below are zero-based, measured by the packaged decoder:

- Three samples: **2, 10, 18**.
- Nine samples: **2, 4, 6, 8, 10, 12, 14, 16, 18**.

| Animal threshold | Three samples | Nine samples |
| --- | --- | --- |
| 0.63, unchanged Quark setting | No candidate; 1.751 s | No candidate; 3.814 s |
| 0.5, separate earlier diagnostic setting | No candidate; 1.748 s | Candidate in frame 4; 3.949 s |

Times include model loading, sampled-frame decoding and inference, as measured
by the worker replay. They exclude container startup and the separate complete
remux verification. These are single runs on another CPU host, not Quark latency,
sustained-load capacity or a throughput comparison.

At 0.5, the nine-sample proposal scored **0.606804** and covered the bottom-border
region at normalized XYWH `(0.313223, 0.927895, 0.095000, 0.041022)`. Its
still-motion ratio was **4.394**, above the unchanged 1.4 floor. All nine requested
samples decoded and all nine distinct frames were inferred. Frame 4 is absent
from the three-frame sample. This proposal remains below 0.63 and establishes
neither a correct species name nor another individual.

## Required next evidence

Before promoting denser collection, freeze an independent panel of original
recordings with trustworthy timing and reviewed animal locations. Include brief
animals, people with and without animals, empty scenes, fixtures, rain and infrared
noise. Score whole-window collection and person vetoes, not only the best animal
box. Preserve the Frigate person-history veto, bird priority and the worker deadline.

Denser sampling changes adjacent-frame differences in the still-motion filter.
One passing proposal does not show equivalent fixture rejection or privacy
behaviour. The existing synthetic tests cover added-sample person vetoes, failed
samples and duplicate seeks; this native comparison adds no real person or weather
control panel. Do not tune thresholds against this previously explored event.

Species naming, saved crops and grouped-visit acceptance remain separate from
detector sampling. Independent two-bird and duplicate-part counting validation
under [#734](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues/734)
is still required. The Quark GPU hang remains deferred; no GPU/NPU replay,
qualification or quarantine reset was performed here.
