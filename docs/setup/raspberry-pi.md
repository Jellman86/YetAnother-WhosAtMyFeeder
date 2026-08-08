# Raspberry Pi (ARM64) Setup

YA-WAMF now ships a dedicated Raspberry Pi monolith image:

- `ghcr.io/jellman86/yawamf-monalithic-rpi`

This image is intended for Raspberry Pi 4 and Raspberry Pi 5 systems running a
64-bit ARM OS. It uses the same monolithic deployment layout as the x86 images,
reports the `rpi` image flavor, and explicitly installs the CPU dependency set. It uses Google's
standalone LiteRT interpreter for TFLite models and includes a checksum-verified MobileNet V2
fallback, so a fresh image can classify without first downloading a large model.
It does not inherit CUDA, OpenVINO, or Intel GPU/NPU userspace packages.

> [!WARNING]
> Raspberry Pi support is currently a best-effort path. CI starts the ARM64 image under QEMU and
> runs a real MobileNet inference before publishing a mutable tag, but it has not yet been
> hardware-validated by the maintainer on a physical Raspberry Pi.

## Supported Scope

- Raspberry Pi 4 or 5
- 64-bit Raspberry Pi OS or another ARM64 Linux distribution
- Monolithic deployment only
- CPU inference only

The standard `ghcr.io/jellman86/yawamf-monalithic` repository remains the x86-64
path. Its full, CPU, Intel and CUDA tag choices are documented in
[Hardware Acceleration](hardware-acceleration.md).

## Hardware Expectations

- Prefer a Raspberry Pi 5 if you have the choice
- Use an SSD for `/data` if possible
- Keep expectations conservative for large ONNX models
- Treat this as an event-driven feeder workflow, not a high-throughput inference box

Practical guidance:

- MobileNetV2 / TFLite is the safest choice on Pi hardware
- RoPE ViT-B14 may work on Raspberry Pi CPU, especially on a Pi 5, but it is not yet validated on physical Pi hardware in this project and should be treated as an experimental step up from MobileNetV2
- Smaller ONNX CPU models can work, but they will be slower than x86-64
- Large ONNX models such as ConvNeXt are not recommended
- EVA-02 is not recommended on Raspberry Pi CPU
- NVIDIA CUDA and Intel OpenVINO acceleration are not available on Raspberry Pi

## Install

Follow the normal monolith setup from [Getting Started](getting-started.md), but start from the Raspberry Pi example env file:

```bash
cp .env.rpi.example .env
```

That example already includes the ARM64 image override and conservative Pi tuning. If you prefer to edit your existing `.env` instead, set:

```env
YAWAMF_MONALITHIC_IMAGE=ghcr.io/jellman86/yawamf-monalithic-rpi
YAWAMF_MONALITHIC_TAG=latest
```

Then start the stack as normal:

```bash
docker compose -f docker-compose.monolith.yml up -d
```

If you want to pin a release instead of following `latest`, use a current version tag such as:

```env
YAWAMF_MONALITHIC_TAG=v2.17.0
```

## Recommended Pi Settings

These are conservative defaults for lower-powered ARM systems:

```env
CLASSIFIER_IMAGE_MAX_CONCURRENT=1
CLASSIFIER_IMAGE_ADMISSION_TIMEOUT_SECONDS=1.0
```

Recommended starting point:

- Provider: `Auto` (the Pi image resolves this to CPU)
- First model to try: `MobileNet V2`; it is bundled and selected automatically when it is the
  effective fallback
- Next step on Raspberry Pi 5 only: `RoPE ViT-B14` if you want better wildlife-wide accuracy and can tolerate slower inference
- Avoid initially: `ConvNeXt Large`, `EVA-02 Large`, and other heavier video-centric workflows
- If Frigate already classifies well, enable `Trust Frigate Sublabels` to save Pi CPU time
- Leave Deep Video Analysis off initially, then enable it later only if the system stays responsive

Optional trade-off if you want to reduce disk and CPU pressure:

```env
FRIGATE__CLIPS_ENABLED=false
```

That disables clip fetching and some video-heavy workflows.

The monolith Compose file explicitly passes all three variables above into the container. A `.env`
file only supplies Compose interpolation values; misspelled or unreferenced names do not become
container settings.

## First-run model check

The setup wizard shows the model the classifier actually loaded, not merely a saved selection whose
files are missing. MobileNet V2 is available offline. If you choose another model, the wizard can
download it with visible progress and then run the same image/hardware validation used by Model
Evaluation.

You should see the selected model pass CPU validation before **Continue** becomes available. If the
download or validation fails, keep MobileNet selected, retry from the same step, and review
**Diagnostics → Model evaluation** for the detailed provider result.

## Known Limitations

- No NVIDIA CUDA acceleration
- No Intel OpenVINO acceleration
- Slower ONNX inference than x86-64 systems
- No maintainer hardware validation yet
- Published performance figures are intentionally withheld until the physical-device pass is
  complete

If you hit a Pi-specific issue, include:

- Pi model
- OS and architecture (`uname -m`)
- storage type (microSD vs SSD)
- selected classification model
- YA-WAMF image tag

That will make it much easier to separate ARM64 packaging bugs from normal runtime issues.
