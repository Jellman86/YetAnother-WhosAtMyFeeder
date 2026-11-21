# Python upgrade readiness: 3.12 to 3.13, and why not 3.15

Date: 13 November 2026. Base: `dev`. Host for the hardware checks: Quark (Intel iGPU on the
i915 driver at `/dev/dri/renderD128`, Intel NPU at `/dev/accel/accel0`, no NVIDIA GPU).

Dependabot proposed moving both images from `python:3.12-slim` to `python:3.15-slim`
(#866 for the monolith `Dockerfile`, #867 for `backend/Dockerfile`). This review answers
three questions: can the images run Python 3.15, what is the furthest version that is safe
today, and why did the backend tests time out on #866.

## 1. Summary

- **Python 3.15 cannot be built for any flavor today.** `tensorflow-cpu`, `onnxruntime`,
  `onnxruntime-gpu`, `openvino`, `ai-edge-litert` and `h5py` publish no `cp315` wheels, on
  x86_64 or aarch64. `pip` fails at the first of them. Neither Dependabot pull request built
  an image, so CI never saw this.
- **Python 3.14 is not fully supported either.** Every package has a `cp314` wheel except
  the stable `tensorflow-cpu` (2.21.0 stops at `cp313`). `pip` then silently installs the
  release candidate `tensorflow-cpu 2.22.0rc0` with `keras-nightly`. That is a pre-release
  ML runtime in every amd64 image. The arm64 `rpi` flavor alone would be clean on 3.14, but
  running one flavor on a different Python from the rest doubles the test surface for no
  benefit to anyone's feeder.
- **Python 3.13 is fully supported and is what this change moves to.** All five flavors
  resolve to exactly the same package versions as on 3.12, from stable wheels only.
- **The #866 timeout had nothing to do with Python 3.15.** The CI job installs Python with
  `setup-python` and ran on 3.12.15. All 6956 tests passed in 475.34 s; the regression gate
  then hit its 480 s budget while coverage was finishing. `dev` raised that budget to 600 s
  in `b80b9ca2`. The same commit range on #867 passed because its runner was a little
  faster.
- **On real hardware the 3.12 and 3.13 images give identical answers.** Across seven model
  artifacts on CPU, OpenVINO CPU, the Intel GPU and the NPU, every top-1 species matched and
  the largest difference in any probability was 0.0 (the arrays are bit-identical).

## 2. Wheel matrix

Method: `uv pip compile --only-binary :all:` for each Python version, platform and flavor,
then the published wheel tags for every compiled distribution in those resolutions read
from PyPI, then real installs (section 3). `Y` means a wheel exists for that CPython ABI
(an `abi3` or `py3-none` platform wheel counts for every version it covers). Pure-Python
distributions are omitted because they install everywhere.

| Distribution | Version | x86_64 3.12 | 3.13 | 3.14 | 3.15 | aarch64 3.12 | 3.13 | 3.14 | 3.15 |
|---|---|---|---|---|---|---|---|---|---|
| tensorflow-cpu | 2.21.0 (stable) | Y | Y | - | - | n/a | n/a | n/a | n/a |
| tensorflow-cpu | 2.22.0rc0 (pre-release) | Y | Y | Y | - | n/a | n/a | n/a | n/a |
| ai-edge-litert | 2.1.6 (pinned) | Y | Y | Y | - | Y | Y | Y | - |
| ai-edge-litert | 2.3.0 (latest) | Y | Y | Y | - | Y | Y | Y | - |
| onnxruntime | 1.32.0 | Y | Y | Y | - | Y | Y | Y | - |
| onnxruntime-gpu | 1.26.0 (CUDA 12 window) | Y | Y | Y | - | n/a | n/a | n/a | n/a |
| onnxruntime-gpu | 1.32.0 (latest) | Y | Y | Y | - | Y | Y | Y | - |
| openvino | 2026.4.1 | Y | Y | Y | - | Y | Y | Y | - |
| h5py (TensorFlow dependency) | 3.14.0 | Y | Y | - | - | Y | Y | - | - |
| h5py | 3.16.0 (latest) | Y | Y | Y | - | Y | Y | Y | - |
| pyyaml | 6.0.3 | Y | Y | Y | - | Y | Y | Y | - |
| numpy | 2.5.4 | Y | Y | Y | Y | Y | Y | Y | Y |
| opencv-python-headless | 4.10.0.84 (`<4.11`) | Y | Y | Y | Y | Y | Y | Y | Y |
| pillow | 13.0.0 | Y | Y | Y | Y | Y | Y | Y | Y |
| pydantic-core | 2.50.4 | Y | Y | Y | Y | Y | Y | Y | Y |
| uvloop | 0.23.0 | Y | Y | Y | Y | Y | Y | Y | Y |
| httptools | 0.9.0 | Y | Y | Y | Y | Y | Y | Y | Y |
| cryptography | 50.0.2 | Y | Y | Y | Y | Y | Y | Y | Y |
| bcrypt | 5.0.0 | Y | Y | Y | Y | Y | Y | Y | Y |
| cffi | 2.1.1 | Y | Y | Y | Y | Y | Y | Y | Y |
| grpcio | 1.85.1 | Y | Y | Y | Y | Y | Y | Y | Y |
| protobuf | 7.36.2 | Y | Y | Y | Y | Y | Y | Y | Y |
| ml-dtypes | 0.6.0 | Y | Y | Y | Y | Y | Y | Y | Y |
| optree | 0.20.0 | Y | Y | Y | Y | Y | Y | Y | Y |
| sqlalchemy | 2.1.8 | Y | Y | Y | Y | Y | Y | Y | Y |
| watchfiles | 1.3.0 | Y | Y | Y | Y | Y | Y | Y | Y |
| websockets | 17.4 | Y | Y | Y | Y | Y | Y | Y | Y |
| wrapt, markupsafe, charset-normalizer, libclang | resolved versions | Y | Y | Y | Y | Y | Y | Y | Y |
| nvidia-*-cu12 (CUDA 12, cuDNN 9 userspace) | resolved versions | Y | Y | Y | Y | n/a | n/a | n/a | n/a |

`n/a` marks a distribution the flavor does not install on that architecture
(`tensorflow-cpu` and the CUDA packages are amd64 only; arm64 uses `ai-edge-litert`).

Resolution per flavor, binary wheels only:

| Flavor | Platform | 3.12 | 3.13 | 3.14 | 3.15 |
|---|---|---|---|---|---|
| cpu | x86_64 | resolves | resolves, same versions | resolves only with `tensorflow-cpu 2.22.0rc0`, `keras-nightly` | fails: `tensorflow-cpu` |
| intel | x86_64 | resolves | resolves, same versions | as cpu | fails: `tensorflow-cpu` (then `onnxruntime`, `openvino`) |
| cuda | x86_64 | resolves | resolves, same versions | as cpu | fails: `tensorflow-cpu` (then `onnxruntime-gpu`) |
| full | x86_64 | resolves | resolves, same versions | as cpu | fails: `tensorflow-cpu` (then `onnxruntime-gpu`, `openvino`) |
| rpi | aarch64 | resolves | resolves, same versions | resolves, stable wheels | fails: `ai-edge-litert` (then `onnxruntime`) |

The only version difference between the 3.12 and 3.13 resolutions is none at all: the two
lock outputs for each flavor are identical line for line.

## 3. Real installs

- `uv pip install -r backend/requirements.txt` into fresh 3.12 and 3.13 environments on
  x86_64: both install TensorFlow 2.21.0, ONNX Runtime GPU 1.26.0, OpenVINO 2026.4.1, NumPy
  2.5.4, OpenCV 4.10.0 and Pillow 13.0.0, and import them.
- `pip install --dry-run --only-binary :all:` of the full flavor under a real CPython 3.14:
  succeeds, and chooses `tensorflow_cpu-2.22.0rc0`, `keras-nightly-3.16.0.dev2026111303`
  and `h5py-3.15.1`.
- The same under a real CPython 3.15.2: `ERROR: No matching distribution found for
  tensorflow-cpu`. Asked for one at a time, `onnxruntime`, `openvino>=2026.4.1`,
  `ai-edge-litert==2.1.6` and `h5py` each fail the same way.
- Images built from the monolith `Dockerfile` on `python:3.13-slim` (Debian 13, Python
  3.13.18): `intel`, `cuda`, `cpu` and `full` for amd64, and `rpi` for arm64 under QEMU.
  The `intel` image was also built on `python:3.12-slim` (Python 3.12.16) from the
  unchanged `dev` Dockerfile as the baseline. Both `intel` images report the same versions:
  TensorFlow 2.21.0, ONNX Runtime 1.32.0, OpenVINO 2026.4.1, NumPy 2.5.4, OpenCV 4.10.0,
  Pillow 13.0.0, pydantic-core 2.50.4, uvloop 0.23.0, httptools 0.9.0, cryptography 50.0.2,
  bcrypt 5.0.0.

## 4. Why #866's backend tests timed out

The job log for the failed run shows:

```
6956 passed, 54 skipped, 5437 warnings in 475.34s (0:07:55)
Regression gate timed out after 480s: ['/opt/hostedtoolcache/Python/3.12.15/x64/bin/python', '-m', 'coverage', 'run', '-m', 'pytest', 'tests/', ...]
```

So the interpreter was 3.12.15 (CI never used the Dockerfile's Python), every test passed,
and the 480 s subprocess deadline in `run_regression_gate.py` expired during coverage
teardown. Other green runs of the same suite that week took 356 s to 519 s on GitHub's
runners, so a 480 s budget was already inside the normal spread. Commit `b80b9ca2` raised
it to 600 s. There is no hang, and nothing in asyncio, subprocess or multiprocessing is
involved.

The suite was still run under both interpreters here to look for a real difference:

| Run | Python | Result | pytest time | Host load at start |
|---|---|---|---|---|
| Host venv | 3.12.13 | 7435 passed, 54 skipped | 594.57 s | 7 |
| Host venv | 3.13.14 | 7435 passed, 54 skipped | 565.87 s | 47 |
| Inside `intel` image | 3.12.16 | 7434 passed, 55 skipped | 694.83 s | 8 |
| Inside `intel` image | 3.13.18 | 7434 passed, 55 skipped | 730.39 s | 10 |

Quark was shared with the live deployment and other test runs throughout, so these wall
times carry roughly ten percent of noise; 3.13 was faster in one pair and slower in the
other. The slowest single test is 6 to 8 seconds on both, with no test that stalls on one
interpreter and not the other. The image runs skip one more test than the host runs and
collect the same total.

Two things about running the suite inside a production image are worth knowing, and
neither is a Python issue. The image sets `YAWAMF_IMAGE_FLAVOR` and `DB_PATH`, which change
provider admission in 44 tests, so those variables must be unset. And three tests in
`tests/pure/test_native_profile_probe_child.py` fail when pytest's parent is PID 1, because
`probe_native_profile.main()` reads the real `os.getppid()`; running pytest under a shell
below `tini` avoids it.

## 5. Hardware verification on Quark

All runs used disposable `docker run --rm` containers with `--device /dev/dri --device
/dev/accel --group-add 105` (the host's `render` group), a 6 GB memory limit and no network.
Models came from the project's `models` release through `model_manager.download_model`,
with their checksums verified, into a private cache. The live installation's data was not
read.

Each model and provider ran in its own child process through
`scripts/run_model_hardware_gate.probe_exact_artifact`, which is the production
preprocessing and inference path. The eight committed real images under
`backend/tests/fixtures/crop_detector_images` were the inputs (crop detectors add three
synthetic negatives). The probe was extended only to keep every raw output vector, so the
two Python versions could be compared number for number.

Tolerance stated in advance: top-1 species identical on every image and every probability
within 1e-4. Observed: identical top-1 everywhere and a largest absolute difference of 0.0.

| Model | Provider (device) | Images | Top-1 same, 3.12 vs 3.13 | Largest probability difference | Top-1 score range | Median latency ms, 3.12 to 3.13 | Agrees with CPU baseline |
|---|---|---|---|---|---|---|---|
| mobilenet_v2_birds (TFLite) | cpu | 8 | 8/8 | 0 | 0.4365 to 1.0000 | 19.2 to 16.9 | yes |
| bird_crop_detector | cpu | 11 | 11/11 | 0 (confidence and box) | n/a | 31.1 to 54.0 | yes |
| bird_crop_detector_accurate_yolox_tiny | cpu | 11 | 11/11 | 0 | n/a | 198.4 to 212.0 | yes |
| bird_crop_detector_accurate_yolox_tiny | intel_cpu | 11 | 11/11 | 0 | n/a | 123.9 to 105.2 | yes |
| bird_crop_detector_accurate_yolox_tiny | intel_gpu (iGPU) | 11 | 11/11 | 0 | n/a | 100.6 to 88.8 | yes |
| bird_crop_detector_accurate_yolox_tiny | intel_npu (NPU) | 11 | 11/11 | 0 | n/a | 84.3 to 78.8 | yes |
| eu_medium_focalnet_b | cpu | 8 | 8/8 | 0 | 0.0093 to 0.9138 | 229.6 to 214.0 | yes |
| eu_medium_focalnet_b | intel_cpu | 8 | 8/8 | 0 | 0.0093 to 0.9138 | 516.3 to 554.6 | yes |
| eu_medium_focalnet_b | intel_gpu (iGPU) | 8 | 8/8 | 0 | 0.0093 to 0.9138 | 154.3 to 153.5 | yes |
| eu_medium_focalnet_b | intel_npu (NPU) | 8 | 8/8 | 0 | 0.0093 to 0.9137 | 94.1 to 95.2 | yes |
| flexivit_il_all | cpu | 8 | 8/8 | 0 | 0.1290 to 0.9166 | 53.4 to 45.4 | yes |
| flexivit_il_all | intel_cpu | 8 | 8/8 | 0 | 0.1290 to 0.9166 | 61.2 to 49.9 | yes |
| flexivit_il_all | intel_npu (NPU) | 8 | 8/8 | 0 | 0.1293 to 0.9161 | 22.0 to 23.3 | yes |
| small_birds/eu | cpu | 8 | 8/8 | 0 | 0.0736 to 0.8784 | 148.1 to 145.3 | yes |
| small_birds/eu | intel_cpu | 8 | 8/8 | 0 | 0.0736 to 0.8784 | 49.1 to 75.3 | yes |
| small_birds/na | cpu | 8 | 8/8 | 0 | 0.1251 to 0.8449 | 16.1 to 10.1 | yes |
| small_birds/na | intel_cpu | 8 | 8/8 | 0 | 0.1251 to 0.8449 | 13.6 to 13.0 | yes |

The devices were really exercised: the worker logs record `OpenVINO model loaded
successfully device=GPU` and `device=NPU`, and within one Python version the NPU's
probabilities differ from ONNX Runtime CPU by up to 6.4e-3 while the GPU differs by 9.5e-7,
which is what different hardware produces. Latency moved in both directions with host load
and is not a signal. For `eu_medium_focalnet_b` the eight top-1 answers on 3.13 were
Eurasian blue tit 0.8557, Eurasian blue tit 0.8528, Unknown 0.8430, European robin 0.9049,
American robin 0.9138, Eurasian jay 0.0093, Mallard 0.7851 and Feral pigeon 0.9037, the
same as on 3.12.

The 3.13 `full` image repeated the same seventeen model and provider runs, including the
iGPU and the NPU, and all were valid and agreed with their CPU baseline.

### Application startup

Each image was started with its real entrypoint on an empty `/data` and `/config`, with no
MQTT broker or Frigate reachable.

| Image | Python | Healthy after | Migrations | Catalogue | Classify a real image through `/api/classifier/classify` |
|---|---|---|---|---|---|
| intel, baseline | 3.12.16 | 15 s | head `c1d734b9e201`, integrity ok | seeded, head `a9e72c4d103b` | background 0.986726, House Sparrow 0.013274 |
| intel | 3.13.18 | 15 s | same | same | identical |
| full | 3.13.18 | 15 s | same | same | identical |
| cuda | 3.13.18 | 15 s | same | same | identical |
| cpu | 3.13.18 | 15 s | same | same | identical |
| rpi (arm64, emulated), baseline | 3.12.16 | 90 s | same | same | background 0.973451, House Sparrow 0.017699 |
| rpi (arm64, emulated) | 3.13.18 | 101 s | same | same | identical to the 3.12 rpi image |
| split backend (`backend/Dockerfile`) | 3.13.18 | 37 s | same | same | no predictions: this image bundles no model |

`/health` and `/ready` both answered, `/ready` reported no startup warnings, and
`/api/classifier/status` on the Intel images listed the OpenVINO devices CPU, GPU and NPU.
The only errors in the logs were the expected MQTT reconnect attempts.

### Flavors that could not be fully exercised here

- **cuda.** The 3.13 image builds, imports `onnxruntime-gpu 1.26.0` with
  `CUDAExecutionProvider` listed and the CUDA 12 and cuDNN 9 packages present,
  `onnxruntime.preload_dlls()` succeeds, all seven models run on its CPU provider and the
  app starts. **It was not run on a GPU: Quark has no NVIDIA hardware.** The wheel versions
  are the same as on 3.12, so the risk is low, but the first CUDA host to pull the image is
  the first real test.
- **rpi (arm64).** Built for `linux/arm64` on both 3.12 and 3.13 and run under QEMU
  emulation. Both import `ai-edge-litert 2.1.6` and `onnxruntime 1.32.0`, start healthy and
  classify the same image identically. Six model artifacts (the TFLite default, both crop
  detectors, `flexivit_il_all` and both `small_birds` regions) gave bit-identical output on
  3.12 and 3.13. `eu_medium_focalnet_b` exceeded the 300 s limit under emulation on 3.13 and
  was skipped on 3.12, so it has no arm64 result. **No real Raspberry Pi was used.** The
  arm64 scores differ slightly from amd64 (0.9735 against 0.9867 for the same image) on
  both Python versions, because LiteRT on arm64 is a different interpreter build from
  TensorFlow on amd64; that is not new.
- **Split backend image (`backend/Dockerfile`).** Built on 3.13 and started: healthy
  in 37 s, both migration streams at head, TensorFlow 2.21.0, ONNX Runtime GPU 1.26.0 and
  OpenVINO 2026.4.1 import, and OpenVINO lists CPU and GPU. It installs exactly the `full`
  requirement set that was exercised above. Its classify call returned an empty list because
  this image has never bundled `model.tflite` (only the monolith downloads it); that was not
  compared against a 3.12 build of the same image.

## 6. What 3.13 changes for the code

- Python 3.13 removed the "dead batteries" modules (`cgi`, `crypt`, `imghdr`, `audioop`,
  `telnetlib` and the rest of PEP 594). None is imported by `backend/`, `scripts/`,
  `tests/` or `custom_components/`.
- The images use the standard build, not the free-threaded one, so nothing about the GIL
  changes.
- Ruff's `target-version` moves to `py313`; `ruff check .` and `ruff format --check .` are
  clean with no source changes.
- The base image stays on Debian 13, so the Intel compute runtime, IGC and NPU driver
  packages pinned in the Dockerfile install unchanged and were the ones exercised above.

## 7. Recommendation

1. Move both Dockerfiles, both workflows, Ruff and the documentation to Python 3.13
   together. This change does that, and adds
   `test_python_version_is_the_same_in_every_image_ci_job_and_lint_target` so a base-image
   bump on its own now fails CI instead of passing on an interpreter the image will not run.
2. Leave #866 and #867 unmerged. With the lock-step test in place their CI will fail for
   the right reason. Consider a Dependabot `ignore` for `python` versions `>= 3.14` on the
   two Docker entries until the conditions below are met; that is the owner's call because
   it closes those two pull requests.
3. Revisit 3.14 when a stable `tensorflow-cpu` ships `cp314` wheels (2.22.0 is at release
   candidate), and 3.15 when `tensorflow-cpu`, `onnxruntime`, `onnxruntime-gpu` inside the
   CUDA 12 window, `openvino` and `ai-edge-litert` all publish `cp315` wheels. The check is
   one command per flavor:
   `uv pip compile --python-version 3.15 --only-binary :all: requirements-base.txt requirements-provider-<flavor>.txt`.
4. The image build is the only place a missing wheel shows up, and it runs after merge. A
   pull-request job that resolves each flavor's requirements against the Dockerfile's
   Python would close that gap cheaply; it is not part of this change.

## 8. Not verified

- CUDA inference on an NVIDIA GPU (no such hardware on Quark).
- The `rpi` image on a real Raspberry Pi; it ran under QEMU emulation only.
- The larger models (`convnext_large_inat21`, `rope_vit_b14_inat21`, `eva02_large_inat21`,
  `medium_birds`, the RF-DETR crop detector) were left out to keep GPU and NPU time short
  on a host shared with the live deployment. They use the same runtimes and wheels as the
  models that were run.
- Sustained load, video classification and long-running memory behaviour under 3.13. The
  suite covers their logic; no soak test was run.
