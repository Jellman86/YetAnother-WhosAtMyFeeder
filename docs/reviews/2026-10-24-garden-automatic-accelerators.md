# Automatic Garden accelerator selection and a hedgehog sampling follow-up

Automatic Garden checks now follow the Detection device preference, with their
own CPU comparison before using an accelerator. Bird-model validation does not
qualify SpeciesNet. Explicit preferences remain explicit; Auto considers the
providers packaged by the image, skipping failed profiles on later captures.

## Execution and failure boundaries

- Native work remains in disposable, supervised children. CPU reference and
  accelerator execution run sequentially, while bird inference and cameras are idle.
- The first accelerator result must identify the requested device, return finite
  normalized probabilities, agree with the CPU presence/person decision, and stay
  within 0.03 absolute probability difference. A CPU top-class margin of at least
  0.05 requires the same winner. These are numerical checks, not accuracy evidence.
- Positive evidence is bounded to 32 profiles in memory and expires at restart.
  It binds the installed model, taxonomy package, image flavor, host/device/runtime
  signature and CPU-reference runtime. It is not copied from an offline report.
- Negative evidence is persisted through the existing native quarantine. The
  accelerator's own runtime and weights identify its negative profile; changing
  the taxonomy or the CPU-reference runtime cannot release that evidence.
- A failed accelerator check uses the already proven CPU result, or launches a
  CPU worker after the failing worker has been reaped. Unreaped cleanup halts
  Garden. Native CPU faults are quarantined before another device can start.
- Person vetoes, naming thresholds, owner overrides, history and collection rules
  are unchanged. Motion scans still use CPU. Manual checks still use the requested
  device and fail instead of silently switching.

An automatic check can compile and load the model twice on first use. Shared
GPU/NPU memory and contention with bird work remain relevant. Compilation is not
warm inference latency. A restart intentionally requires another comparison.

## Native hardware evidence

A bounded Linux test used an Intel Core Ultra 5 235T with Intel integrated graphics
and Intel AI Boost NPU, OpenVINO 2026.4.1 and ONNX Runtime 1.26.0. Released Cedar,
SpeciesNet 4.0.3a and 4.0.3b weights were checksum-verified. Eight real public-panel
inputs ran twice per model on ONNX CPU, OpenVINO CPU, Intel GPU and NPU: 192
inferences across 12 model/provider combinations.

All combinations returned finite outputs and passed the fixed CPU-agreement
criteria. Execution devices were `CPUExecutionProvider`, `CPU`, `GPU.0` and `NPU`.
There were no top-class or presence-decision changes on these inputs. The largest
classifier probability difference was 0.019194 for GPU and 0.012087 for NPU;
minimum matched detector-box IoU was 0.991846 and 0.992879 respectively.

| Model | ONNX CPU warm median | Intel GPU warm median | NPU warm median |
| --- | ---: | ---: | ---: |
| Cedar | 430 ms | 66 ms | 39 ms |
| SpeciesNet crop 4.0.3a | 207 ms | 45 ms | 35 ms |
| SpeciesNet whole 4.0.3b | 206 ms | 42 ms | 38 ms |

A subsequent test exercised automatic selection through the normal supervised
photo-worker method: CPU reference then NPU, reuse of NPU validation for the next
image, CPU reference then GPU, reuse of GPU validation, and explicit CPU. All eight
child executions completed with the requested device. Test configuration and
quarantine stayed in a private workspace. No production settings, model eligibility,
history or jobs were changed.

In that small supervised-worker test, explicit CPU checks took 1.51–1.53 seconds.
The first NPU/GPU checks, including their CPU reference, took about ten seconds;
subsequent checks took 2.13 and 2.56 seconds. Faster accelerator kernels therefore
do not establish faster end-to-end checks with disposable model loads. No queue
speed improvement is claimed.

These are small native tests with private runtime-library paths, not qualification
of a newly published container, CUDA, sustained driver stability, production video
supervision or concurrent MQTT load. Initial test-harness dependency/decoder/cache
errors were retained separately and are not hardware failures. CUDA still needs
its own real-device evidence for this new automatic selection path.

## Hedgehog: sampling and border preprocessing

A separate public-panel case used the human-labelled `Erinaceus europaeus` event
`a793a344-9f37-4d7e-8969-924b51e2b6dc` from the INBO MUNTJAC_ANTWERP dataset.
Its full event contains **20 frames across two bursts**, not ten. The fixed
first/middle/last sample contained no detector candidate.

A post-hoc check of all 20 source frames found animal detections in zero-based
frames **4, 5, 6 and 8**, at the unchanged 0.5 threshold, with scores 0.572–0.658.
The partial animal is at the bottom image border. All four detections were absent
from the original three-frame sample. This diagnoses a sampling limitation;
it is not evidence that Cedar failed throughout the event.

The whole-image 4.0.3b preprocessing trims the top and bottom of these images,
excluding the animal's border position. Its highest class was blank on every
frame. Detector crops supplied to 4.0.3a instead returned **animal** on all four
frames. Their highest species/taxon guesses were eastern cottontail or the rabbit
and hare family, at 0.35–0.59 confidence. Those guesses disagree with the source
hedgehog label and are below both the default 0.8 naming threshold and its allowed
minimum of 0.7, so they do not justify an automatic species name.

This follow-up does not rescore the frozen three-frame panel or change thresholds,
preprocessing, sampling defaults or species rules. Denser event sampling and
additional independently localized hedgehog examples are the useful next evidence;
relaxing confidence would not fix the species uncertainty.

[Dataset and attribution](https://wildlifecamera.eu/datasets/): INBO
MUNTJAC_ANTWERP, CC0 metadata and CC BY 4.0 public media. Only media marked public
were used. Photos remain outside the application repository.
