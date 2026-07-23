# Raspberry Pi ARM64 assessment

**Reviewed:** 2026-07-21
**Support level:** Best-effort until the physical-device exit pass is complete

This assessment records what the dedicated Raspberry Pi image proves today, what is deliberately
excluded, and what must still be measured before YA-WAMF claims official Pi support. Code, tests,
and the published image contract remain the source of truth.

## Current runtime contract

- Image: `ghcr.io/jellman86/yawamf-monalithic-rpi`
- Platform: `linux/arm64`
- Deployment: monolith only, with the same `/config` and `/data` paths as x86 images
- Inference providers: CPU only
- ONNX runtime: CPU `onnxruntime`
- TFLite runtime: `ai-edge-litert==2.1.6`
- Offline fallback: MobileNet V2 bird classifier, labels, and model sidecar downloaded during the
  image build from pinned inputs and verified with SHA-256

CUDA, Intel OpenVINO GPU/NPU, and Raspberry Pi VideoCore acceleration are not packaged or advertised
by the `rpi` flavor. The provider UI derives its choices from the image, host, and model
intersection, so those unavailable providers do not appear as usable choices.

## What CI proves

The Raspberry Pi job builds and pushes an immutable commit-SHA canary before any mutable tag. QEMU
then starts that exact ARM64 image and checks:

1. Docker health and backend readiness both succeed.
2. The image reports `YAWAMF_IMAGE_FLAVOR=rpi`.
3. `/api/classifier/status` reports a loaded model, an effective model id, and a real label set.
4. A generated RGB image reaches `/api/classifier/classify` and returns predictions.
5. Only after those checks pass is `dev`, `main`, a version tag, or `latest` promoted.

This catches architecture, dependency, model-loading, label, web-routing, and basic inference
regressions. It is not evidence of physical-device speed, thermals, or storage durability.

## First-run and configuration behaviour

Every image contains the small MobileNet fallback, so the backend can classify on a clean install
without network access. Classifier status reports both the saved model id and the effective model id
when fallback is necessary. The setup wizard selects the effective installed model, can download a
different model with bounded progress/error handling, and requires hardware validation before that
model can be enabled.

The Pi example uses:

```env
CLASSIFIER_IMAGE_MAX_CONCURRENT=1
CLASSIFIER_IMAGE_ADMISSION_TIMEOUT_SECONDS=1.0
```

`docker-compose.monolith.yml` passes both values into the container. It also passes
`FRIGATE__CLIPS_ENABLED`, allowing an operator to disable clip workflows deliberately. An SSD is
recommended for `/data`; no unmeasured latency claim is treated as fact.

## Remaining risks and exit criteria

Official support remains blocked on a Raspberry Pi 4 and/or Pi 5 physical test that records:

- clean first start and upgrade with existing `/config` and `/data` preserved;
- MobileNet plus one practical ONNX model load, inference latency, and memory use;
- sustained event ingestion and classification without runaway queueing;
- thermal behaviour and throttling during a representative soak;
- UI responsiveness while classification and media caching are active;
- microSD versus SSD behaviour, with SSD used for the recommended result;
- restart recovery, database integrity, and model persistence;
- Frigate snapshot and optional clip workflows at the documented conservative settings.

Measured results should be added to this assessment and the setup guide. Until then, the UI and
documentation must continue to say **best-effort**, not supported or performance-validated.
