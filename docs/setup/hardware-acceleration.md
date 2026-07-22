# Hardware acceleration

Run bird classification on a GPU or NPU instead of the CPU, so inference is
faster or more power-efficient and the CPU stays free for the rest of your stack.

## Outcome

You choose an image containing the required runtime, pass the matching device
into the container, and select an inference provider in the UI. YA-WAMF runs the
classifier on that accelerator and falls back to CPU if the device or a specific
model is not usable.

## Prerequisites

- A host accelerator YA-WAMF supports: an Intel integrated GPU (`/dev/dri`), an
  Intel Core Ultra NPU / "AI Boost" (`/dev/accel`), or an NVIDIA GPU (CUDA).
- Permission to pass host devices into the container (Docker Compose `devices:`
  and, usually, `group_add:`).

Changing the provider only affects inference. It never touches your detection
history or configuration, and an unusable device falls back to CPU rather than
failing classification.

## Choose an image flavor

The default unsuffixed image remains the broad compatibility build. Smaller
provider-family images avoid downloading runtimes your host cannot use:

| Host | Stable tag | Development tag | Packaged providers |
|---|---|---|---|
| Compatibility/testing | `latest` | `dev` | CPU, CUDA, OpenVINO CPU/GPU/NPU |
| CPU only | `latest-cpu` | `dev-cpu` | ONNX CPU |
| Intel | `latest-intel` | `dev-intel` | ONNX CPU, OpenVINO CPU/GPU/NPU |
| NVIDIA | `latest-cuda` | `dev-cuda` | ONNX Runtime CUDA and CPU |

Set the existing tag variable in `.env`; the image repository and Compose file do
not change:

```env
YAWAMF_MONALITHIC_TAG=latest-intel
```

`MONALITHIC` is the established spelling in this public variable. Keep that
spelling so an existing `.env` continues to control the Compose image tag.

Pinned releases use the same suffix, for example `v2.14.0-intel`. Unsuffixed
`latest`, `dev`, `main`, release and commit tags always mean `full`, so existing
installs keep their current runtime. Switching flavor is non-destructive because
every image uses the same `/config` and `/data` volume contract.

An image flavor states what is **packaged**, not what the host can execute. Intel
devices still need device passthrough and host support; NVIDIA still needs its
driver and Container Toolkit. **Settings → Detection → Runtime diagnostics** is
the source of truth for what is actually available and active.

## Switch safely between flavors

All flavors from one commit contain the same application code and use the same
`/config` and `/data` mounts. Config, detection history, cached media, and models
therefore stay outside the image. A flavor switch must change **only the image
tag**; do not create new mount paths or copy data into the container filesystem.

1. Keep the application version constant while testing. For example, switch
   `dev` → `dev-intel`, or `v2.14.0` → `v2.14.0-intel`. Immutable commit tags are
   even safer for comparisons: `<sha>`, `<sha>-cpu`, `<sha>-intel`, and
   `<sha>-cuda` are built from exactly the same source.
2. Record the current tag. Export a configuration backup from **Settings → Data
   → Setup, backup & maintenance tools → Configuration Backup** and protect it
   like a credential because it contains secrets. This export does not include
   `/data`; use your normal stopped-volume or storage snapshot procedure as an
   additional precaution for production data.
3. Change only `YAWAMF_MONALITHIC_TAG`, pull the selected image, and recreate the
   existing `yawamf` service with the existing Compose project.
4. Check **Settings → Detection → Runtime diagnostics**. Confirm **Image**,
   **Packaged**, **Selected**, and **Active** before comparing inference.
5. To roll back, restore the recorded tag and recreate the same service. No
   config import or database rollback is required for a same-commit flavor
   switch.

An explicitly selected provider is never rewritten merely because the current
image cannot package it. YA-WAMF reports the mismatch, uses the available CPU
fallback, and keeps the selection intact for the next compatible image. This
full → CPU → full round trip, including byte-identical application config,
model artifact and model sidecar plus SQLite integrity, is a required CI gate
before mutable image tags are promoted.

On a Git-managed deployment platform, make the tag change through that
platform's stack workflow. Do not edit or pull the managed Compose project
directly on the Docker host.

## Providers

Set the provider at **Settings → Detection → Inference Provider**. The values map
to `classification.inference_provider` (`auto|cpu|cuda|intel_gpu|intel_cpu|intel_npu`,
also settable via the `CLASSIFICATION__INFERENCE_PROVIDER` environment variable):

| UI label | Value | Image flavor | Host device | Notes |
|---|---|---|---|---|
| Auto | `auto` | any | — | Chooses the best packaged and available path, preferring Intel GPU, then CUDA, then CPU. |
| CPU (ONNX Runtime) | `cpu` | any | none | Always packaged; the safe fallback. |
| NVIDIA CUDA | `cuda` | `full` or `cuda` | NVIDIA GPU | Needs the NVIDIA Container Toolkit on the host. |
| Intel GPU (OpenVINO) | `intel_gpu` | `full` or `intel` | `/dev/dri` | Integrated Arc/UHD graphics. |
| Intel CPU (OpenVINO) | `intel_cpu` | `full` or `intel` | none | OpenVINO on the CPU. |
| Intel NPU (OpenVINO) | `intel_npu` | `full` or `intel` | `/dev/accel/accel0` | Core Ultra "AI Boost" NPU. |

`Auto` is recommended unless you have a reason to pin a device.

The selector is capability-aware. It only offers providers that are included in
the running image, pass the host runtime/device probe, and are declared compatible
with the active model. Options begin with the active provider and its concrete
recovery sequence; any remaining valid manual alternatives follow. The UI prints
the recovery sequence separately so the order is not confused with a list of
providers that `Auto` will necessarily try.

The setup wizard applies the same contract to the model currently selected in the
wizard, even before that model is activated. This prevents the previous active
model from hiding a valid accelerator or exposing one the replacement cannot use.

Changing to a narrower image or model does not silently rewrite an explicit saved
choice. That choice remains visible but disabled, with guidance to select `Auto`
or another available provider. This preserves a deliberate device pin across a
temporary image-flavor switch while preventing an unavailable provider from being
selected again.

## Validate this host

The **Setup wizard**, guided Model Manager flow, and **Settings → Detection → Device
compatibility** use the same provider-validation engine. Candidates are the exact
intersection of:

1. providers packaged by the running image;
2. providers whose runtime and device probe succeeds on this host; and
3. providers declared compatible with the selected model.

Each candidate is compiled and executed in an isolated child process so a native
CUDA, GPU, or NPU failure cannot restart the application. The compatibility sweep
uses up to 12 taxonomy-verified bird images, requires finite output, compares every
accelerator's top prediction with the CPU baseline, and records median inference
latency. The fastest passing candidate is reported without treating a merely
installed runtime as working hardware.

The resulting matrix is image-aware: `cpu`/`rpi` test CPU, `cuda` tests ONNX CPU and
CUDA, `intel` tests ONNX CPU plus the detected OpenVINO targets, and `full` tests all
applicable targets. In particular, OpenVINO CPU in the full image does not suppress
CUDA validation. Switching flavors keeps the underlying history but filters it
through an exact per-model image-flavor record, so even a provider name shared by
two flavors must be revalidated after the switch. Stale Intel, CUDA, or CPU evidence
cannot authorize a model in a different runtime image.

Published images fail closed when their expected runtime is missing: a bundled live
fallback cannot be mistaken for successful validation of the selected ONNX model.

## Smallest working path (Intel iGPU or NPU)

1. Use the full compatibility image or select the Intel image in `.env`:

   ```env
   YAWAMF_MONALITHIC_TAG=latest-intel
   ```

2. Check which accelerators the host exposes:

   ```bash
   ls -l /dev/dri /dev/accel
   ```

3. In `docker-compose.monolith.yml`, uncomment the device lines for what you have:

   ```yaml
   devices:
     - /dev/dri:/dev/dri                 # Intel GPU  → intel_gpu
     - /dev/accel/accel0:/dev/accel/accel0   # Core Ultra NPU → intel_npu
   group_add:
     - "44"    # video (example)
     - "107"   # render (example — covers both /dev/dri and /dev/accel on most distros)
   ```

   Match the group IDs to your host (`getent group render video`); the numbers
   above are examples.

4. Recreate the container:

   ```bash
   docker compose up -d
   ```

5. Open **Settings → Detection**, set **Inference Provider** to your device (or
   leave it on **Auto**), and save.

## Expected result

Under **Settings → Detection**, the accelerator status pills reflect what YA-WAMF
found. For example **Intel NPU: Auto-detected · verified ✓** means the NPU was
detected and has passed validation for the loaded model. A device that is present
but not yet proven for the current model shows **unverified**.

Open **Advanced model manager** to inspect the active model. **Current runtime**
shows the provider that is running now, and **Automatic order** lists its verified
fallbacks in the order YA-WAMF will try them. **Best fit** describes the model's
accuracy and use case; it does not claim which device is active.

If it fails, the pill shows **Not detected** — recheck the `devices:` and
`group_add:` entries and that the host driver is installed.

## Intel NPU specifics

The NPU is validated per model, not enabled blanket:

- YA-WAMF only runs a model on the NPU when that model is marked NPU-validated
  (compiles, produces finite output, and its top-k agrees with the CPU baseline).
  The `rope_vit_b14` classifier and accurate YOLOX-Tiny crop detector are validated on Arrow Lake;
  classifiers compare top-k output while crop detectors compare admitted detection presence,
  geometry, and confidence.
- The NPU is stricter than the GPU on some operations, so not every model is
  NPU-viable. When a model cannot compile on the selected device, YA-WAMF keeps
  the model installed and runs inference on the OpenVINO CPU fallback, and the
  Model Manager states which fallback is in use.
- The payoff is power and thermal efficiency (freeing the iGPU/CPU), not
  necessarily lower latency.

The ordinary compatibility check probes only providers declared for the model. A maintainer's
full-registry discovery sweep may probe an undeclared NPU/GPU in an isolated child process to find
stale metadata. A successful discovery is visible in the downloadable matrix but is not selectable
until the registry and release sidecar have been reviewed and updated; a failed or crashing probe
cannot take down the main backend.

The `full` and `intel` images ship OpenVINO and the NPU user-mode (Level-Zero)
driver. If OpenVINO enumerates only `CPU` with `/dev/accel/accel0` passed in,
check the host kernel/driver boundary and container permissions. The `cpu` and
`cuda` images deliberately do not contain OpenVINO.

## NVIDIA CUDA

Set **Inference Provider** to **NVIDIA CUDA**, install the NVIDIA Container
Toolkit on the host, and pass the GPU per the CUDA example in
`docker-compose.monolith.yml`. Use the `full` or `cuda` image; both include the
CUDA/cuDNN userspace runtime for ONNX Runtime. The `cpu` and `intel` images do
not advertise CUDA and report `selected_provider_not_packaged` if CUDA is
explicitly selected.

On Unraid, use the image-tag and NVIDIA Driver plugin workflow in the dedicated
[Unraid setup guide](unraid.md#nvidia-cuda). Do not translate the Compose-only
`YAWAMF_MONALITHIC_TAG` into a container environment variable; edit the Unraid
Repository tag instead.

## Next steps

- Confirm the active backend and per-device diagnostics under
  **Settings → Detection → Runtime diagnostics**.
- See [`configuration.md`](configuration.md) for all detection settings and
  [`../troubleshooting/diagnostics.md`](../troubleshooting/diagnostics.md) if
  inference is falling back unexpectedly.
