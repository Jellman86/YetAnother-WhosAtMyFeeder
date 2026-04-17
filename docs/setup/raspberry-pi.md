# Raspberry Pi (ARM64) Setup

YA-WAMF now ships a dedicated Raspberry Pi monolith image:

- `ghcr.io/jellman86/yawamf-monalithic-rpi`

This image is intended for Raspberry Pi 4 and Raspberry Pi 5 systems running a 64-bit ARM OS. It uses the same monolithic deployment layout as the main image, but the ARM64 build skips x86-only GPU runtime setup and uses CPU ONNX Runtime instead of the CUDA package.

> [!WARNING]
> Raspberry Pi support is currently a best-effort path. The image is built in CI, but it has not yet been hardware-validated by the maintainer on a physical Raspberry Pi.

## Supported Scope

- Raspberry Pi 4 or 5
- 64-bit Raspberry Pi OS or another ARM64 Linux distribution
- Monolithic deployment only
- CPU inference only

The standard `ghcr.io/jellman86/yawamf-monalithic` image remains the recommended path for x86-64 hosts, especially if you rely on NVIDIA CUDA or Intel OpenVINO acceleration.

## Hardware Expectations

- Prefer a Raspberry Pi 5 if you have the choice
- Use an SSD for `/data` if possible
- Keep expectations conservative for large ONNX models
- Treat this as an event-driven feeder workflow, not a high-throughput inference box

Practical guidance:

- MobileNetV2 / TFLite is the safest choice on Pi hardware
- Smaller ONNX CPU models can work, but they will be slower than x86-64
- Large ONNX models such as ConvNeXt are not recommended
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

If you want to pin a release instead of following `latest`, use a version tag such as:

```env
YAWAMF_MONALITHIC_TAG=v2.9.13
```

## Recommended Pi Settings

These are conservative defaults for lower-powered ARM systems:

```env
CLASSIFICATION_IMAGE_MAX_CONCURRENT=1
CLASSIFIER_IMAGE_ADMISSION_TIMEOUT_SECONDS=1.0
```

Optional trade-off if you want to reduce disk and CPU pressure:

```env
FRIGATE__CLIPS_ENABLED=false
```

That disables clip fetching and some video-heavy workflows.

## Known Limitations

- No NVIDIA CUDA acceleration
- No Intel OpenVINO acceleration
- Slower ONNX inference than x86-64 systems
- No maintainer hardware validation yet

If you hit a Pi-specific issue, include:

- Pi model
- OS and architecture (`uname -m`)
- storage type (microSD vs SSD)
- selected classification model
- YA-WAMF image tag

That will make it much easier to separate ARM64 packaging bugs from normal runtime issues.
