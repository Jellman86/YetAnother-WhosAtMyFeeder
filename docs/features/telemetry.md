# Telemetry & Usage Metrics

YA-WAMF includes an optional telemetry system designed to help the project understand how the software is used. The project follows a strict **privacy-first** philosophy.

## Default State: Disabled
Telemetry is **disabled by default**. No data is sent unless you explicitly turn it on in the Settings.

Health diagnostics are controlled separately by **Anonymous health diagnostics**. They are also disabled by default and are sent to a separate Cloudflare D1 database from the aggregate usage telemetry.

## Philosophy
Open-source software should be transparent. Only high-level aggregate data is collected, to help answer questions like:
- "Which identification models are most popular (EVA-02, ConvNeXt, or MobileNet)?"
- "Is the BirdNET integration widely used?"
- "What platforms (ARM/x86) should I prioritize for optimization?"
- "Which inference providers, runtimes, and image variants need the most testing?"

## What is Collected?
When enabled, the system sends a lightweight "heartbeat" JSON payload once every 24 hours.

### The Payload
| Field | Example | Purpose |
|-------|---------|---------|
| **Installation ID** | `a1b2c3d4-e5f6...` | A random UUID generated on first run. Allows counting unique active installations without identifying *who* you are. |
| **App Version** | `2.3.0+a0736ed` | Tracks adoption of new releases. |
| **Platform** | `Linux-x86_64` | Informs which Docker architectures to prioritise. |
| **Configuration** | `{ "model_type": "eva02", "birdnet": true }` | Shows which features are most popular. |
| **Runtime** | `{ "inference_provider_active": "intel_cpu", "model_runtime": "onnx" }` | Shows which inference paths are actually in use. |
| **Hardware Capability** | `{ "cuda_available": false, "intel_gpu_available": true }` | Helps prioritize GPU/runtime support without storing device serials or host details. |
| **Deployment** | `{ "image_flavor": "dev", "image_arch": "x86_64" }` | Tracks which Docker image lines and architectures are active. |

## Anonymous Health Diagnostics

When enabled, YA-WAMF sends a second daily report only if backend diagnostics contain warning, error, or critical events. This report is grouped and deduplicated before upload.

Health diagnostics may include:

- issue fingerprints
- component and reason codes
- severity and occurrence counts
- coarse runtime settings such as configured inference provider and execution mode
- enabled integration flags
- sanitized context fields such as queue depth, timeout seconds, provider names, and pressure level

Health diagnostics are stored separately from aggregate telemetry so recurring failures can be grouped without mixing them into feature-adoption metrics.

## What is NEVER Collected?
- ❌ **Your Images or Videos:** Bird images and camera feeds are never transmitted.
- ❌ **Detection Data:** No species names, times, or locations.
- ❌ **Credentials:** No passwords, tokens, or API keys.
- ❌ **Network Info:** No local IP addresses or network topology.
- ❌ **Raw Diagnostics Bundles:** Health diagnostics do not upload owner notes, full logs, camera names, media paths, event IDs, URLs, or raw stack traces.

## User Interface & Transparency

When you enable Telemetry or Anonymous health diagnostics in the UI (**Settings > Connections > Telemetry**), a "Transparency" box appears. This shows you:
1. Your unique Installation ID.
2. The runtime/device/deployment data points being sent.

You can toggle this feature off at any time, and the background reporting service will stop immediately.
