# Hardware acceleration

Run bird classification on a GPU or NPU instead of the CPU, so inference is
faster or more power-efficient and the CPU stays free for the rest of your stack.

## Outcome

You choose an inference provider in the UI, pass the matching device into the
container, and YA-WAMF runs the classifier model on that accelerator — falling
back to CPU automatically if the device or a specific model is not usable.

## Prerequisites

- A host accelerator YA-WAMF supports: an Intel integrated GPU (`/dev/dri`), an
  Intel Core Ultra NPU / "AI Boost" (`/dev/accel`), or an NVIDIA GPU (CUDA).
- Permission to pass host devices into the container (Docker Compose `devices:`
  and, usually, `group_add:`).

Changing the provider only affects inference. It never touches your detection
history or configuration, and an unusable device falls back to CPU rather than
failing classification.

## Providers

Set the provider at **Settings → Detection → Inference Provider**. The values map
to `classification.inference_provider` (`auto|cpu|cuda|intel_gpu|intel_cpu|intel_npu`,
also settable via the `CLASSIFICATION__INFERENCE_PROVIDER` environment variable):

| UI label | Value | Host device | Notes |
|---|---|---|---|
| Auto | `auto` | — | Prefers Intel GPU, then CUDA, then CPU. |
| CPU (ONNX Runtime) | `cpu` | none | Always available; the safe default. |
| NVIDIA CUDA | `cuda` | NVIDIA GPU | Needs the NVIDIA Container Toolkit on the host. |
| Intel GPU (OpenVINO) | `intel_gpu` | `/dev/dri` | Integrated Arc/UHD graphics. |
| Intel CPU (OpenVINO) | `intel_cpu` | none | OpenVINO on the CPU. |
| Intel NPU (OpenVINO) | `intel_npu` | `/dev/accel/accel0` | Core Ultra "AI Boost" NPU. |

`Auto` is recommended unless you have a reason to pin a device.

## Smallest working path (Intel iGPU or NPU)

1. Check which accelerators the host exposes:

   ```bash
   ls -l /dev/dri /dev/accel
   ```

2. In `docker-compose.monolith.yml`, uncomment the device lines for what you have:

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

3. Recreate the container:

   ```bash
   docker compose up -d
   ```

4. Open **Settings → Detection**, set **Inference Provider** to your device (or
   leave it on **Auto**), and save.

## Expected result

Under **Settings → Detection**, the accelerator status pills reflect what YA-WAMF
found. For example **Intel NPU: Auto-detected · verified ✓** means the NPU was
detected and has passed validation for the loaded model. A device that is present
but not yet proven for the current model shows **unverified**.

If it fails, the pill shows **Not detected** — recheck the `devices:` and
`group_add:` entries and that the host driver is installed.

## Intel NPU specifics

The NPU is validated per model, not enabled blanket:

- YA-WAMF only runs a model on the NPU when that model is marked NPU-validated
  (compiles, produces finite output, and its top-k agrees with the CPU baseline).
  The `rope_vit_b14` model is validated on Arrow Lake (f16, top-5 matching CPU).
- The NPU is stricter than the GPU on some operations, so not every model is
  NPU-viable. When a model cannot compile on the selected device, YA-WAMF keeps
  the model installed and runs inference on the OpenVINO CPU fallback, and the
  Model Manager states which fallback is in use.
- The payoff is power and thermal efficiency (freeing the iGPU/CPU), not
  necessarily lower latency.

The container image ships the OpenVINO NPU plugin; the NPU user-mode (Level-Zero)
driver is installed best-effort in the image. If OpenVINO enumerates only `CPU`
with `/dev/accel/accel0` passed in, the host is missing the NPU driver.

## NVIDIA CUDA

Set **Inference Provider** to **NVIDIA CUDA**, install the NVIDIA Container
Toolkit on the host, and pass the GPU per the CUDA example in
`docker-compose.monolith.yml`. The image already includes the CUDA/cuDNN
userspace runtime for ONNX Runtime.

## Next steps

- Confirm the active backend and per-device diagnostics under
  **Settings → Detection → Runtime diagnostics**.
- See [`configuration.md`](configuration.md) for all detection settings and
  [`../troubleshooting/diagnostics.md`](../troubleshooting/diagnostics.md) if
  inference is falling back unexpectedly.
