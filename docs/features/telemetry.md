# Telemetry & Usage Metrics

YA-WAMF includes an optional telemetry system designed to help the project understand how the software is used. The project follows a strict **privacy-first** philosophy.

## Default State: Disabled
Telemetry is **disabled by default**. No data is sent unless you explicitly turn it on in the Settings.

## Philosophy
Open-source software should be transparent. Only high-level aggregate data is collected, to help answer questions like:
- "Which identification models are most popular (EVA-02, ConvNeXt, or MobileNet)?"
- "Is the BirdNET integration widely used?"
- "What platforms (ARM/x86) should I prioritize for optimization?"

## What is Collected?
When enabled, the system sends a lightweight "heartbeat" JSON payload once every 24 hours.

### The Payload
| Field | Example | Purpose |
|-------|---------|---------|
| **Installation ID** | `a1b2c3d4-e5f6...` | A random UUID generated on first run. Allows counting unique active installations without identifying *who* you are. |
| **App Version** | `2.3.0+a0736ed` | Tracks adoption of new releases. |
| **Platform** | `Linux-x86_64` | Informs which Docker architectures to prioritise. |
| **Configuration** | `{ "model_type": "eva02", "birdnet": true }` | Shows which features are most popular. |

## What is NEVER Collected?
- ❌ **Your Images or Videos:** Bird images and camera feeds are never transmitted.
- ❌ **Detection Data:** No species names, times, or locations.
- ❌ **Credentials:** No passwords, tokens, or API keys.
- ❌ **Network Info:** No local IP addresses or network topology.

## User Interface & Transparency

When you enable Telemetry in the UI (**Settings > Connections > Telemetry**), a "Transparency" box appears. This shows you:
1. Your unique Installation ID.
2. The exact data points being sent.

You can toggle this feature off at any time, and the background reporting service will stop immediately.
