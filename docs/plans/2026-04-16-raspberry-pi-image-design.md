# Raspberry Pi ARM64 Image Design

**Date:** 2026-04-16
**Status:** Approved
**Scope:** Raspberry Pi support via a dedicated monolithic ARM64 image

## Summary

YA-WAMF will add **best-effort Raspberry Pi 4/5 ARM64 support** by publishing a **separate monolithic image** instead of changing the main `yawamf-monalithic` artifact. The new image should clearly signal a narrower support envelope and avoid changing the meaning of the primary x86-oriented image while Pi hardware is not available for direct maintainer validation.

Recommended image naming:

- `ghcr.io/jellman86/yawamf-monalithic-rpi:latest`
- `ghcr.io/jellman86/yawamf-monalithic-rpi:vX.Y.Z`

## Goals

- Publish a monolith-only Raspberry Pi image for `linux/arm64`
- Keep the main monolithic image and release flow stable
- Document expected performance, limitations, and setup guidance for Pi users
- Avoid introducing split ARM images

## Non-Goals

- No Raspberry Pi support for the legacy split deployment
- No claim of full hardware validation until tested on real Pi hardware
- No attempt to support CUDA or Intel iGPU acceleration on Pi
- No change to the main `yawamf-monalithic` image tag behavior in this phase

## Chosen Approach

### 1. Separate image, monolith only

Publish a dedicated ARM64-only monolith image rather than a multi-arch manifest under the main image name.

Why:

- clearer support boundary
- easier rollback
- safer while hardware validation is unavailable
- avoids changing default deployment semantics for existing users

### 2. CPU-only ONNX Runtime on ARM64

The backend dependency set should switch from `onnxruntime-gpu` to `onnxruntime` on ARM64. This matches ONNX Runtime's official guidance for Arm-based CPUs.

Implication:

- ARM64 image remains functional for CPU/TFLite/CPU-ORT inference
- GPU-specific execution providers stay unavailable on Pi, by design

### 3. Arch-gated runtime setup in Docker

The monolith Dockerfile currently installs Intel GPU/OpenCL runtime packages unconditionally. On ARM64, those steps must be skipped cleanly.

Implication:

- one Dockerfile can continue to serve both the main monolith and the Pi build path
- ARM64 build stays small and avoids incompatible package setup

### 4. Dedicated CI build job

The GitHub Actions workflow should add a dedicated monolith-RPi build/push job rather than converting the main image job into a multi-arch release.

Recommended publishing scope:

- build on version tags
- allow manual `workflow_dispatch`
- avoid building Pi images on every `dev` push unless later explicitly desired

## Docs Strategy

Add a dedicated setup page:

- `docs/setup/raspberry-pi.md`

That page should cover:

- supported hardware scope: Pi 4/5, ARM64 OS
- recommended storage: SSD strongly preferred over microSD
- expected limitations: CPU-only inference, slower large models
- recommended settings and model choices
- explicit "best-effort, not hardware-validated by maintainer yet" notice
- image name and pull/run examples

Also add links from:

- `README.md`
- `docs/index.md`

## Risk Notes

### Primary risk

The image can be built and published without real Pi hardware, but runtime behavior on actual Pi boards remains only indirectly validated.

### Mitigation

- label the support level clearly in docs
- keep the artifact separate from the main image
- verify ARM64 image build success in CI
- if possible, smoke-test container startup under `linux/arm64` emulation in CI or local `buildx` checks

## Acceptance Criteria

- ARM64 monolith image builds successfully in CI as a separate artifact
- `backend/requirements.txt` installs CPU ONNX Runtime on ARM64
- monolith Dockerfile skips Intel GPU runtime setup on ARM64
- docs clearly explain how to use the Pi image and what to expect
- main monolith image behavior remains unchanged

## References

- ONNX Runtime install docs: https://onnxruntime.ai/docs/install/
- ONNX Runtime Python getting started: https://onnxruntime.ai/docs/get-started/with-python.html
- Docker multi-platform GitHub Actions docs: https://docs.docker.com/build/ci/github-actions/multi-platform/
