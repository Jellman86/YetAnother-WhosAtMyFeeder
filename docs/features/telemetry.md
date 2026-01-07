# Telemetry & Usage Metrics

YA-WAMF includes an optional telemetry system designed to help us understand how the software is used. We follow a strict **privacy-first** philosophy.

## Default State: Disabled
Telemetry is **disabled by default**. No data is sent unless you explicitly turn it on in the Settings.

## Philosophy
We believe open-source software should be transparent. We only collect high-level aggregate data to help answer questions like:
- "How many people are using the new EVA-02 model vs the older MobileNet?"
- "Is the BirdNET integration widely used?"
- "What platforms (ARM/x86) should we prioritize for optimization?"

## What is Collected?
When enabled, the system sends a lightweight "heartbeat" JSON payload once every 24 hours.

### The Payload
| Field | Example | Purpose |
|-------|---------|---------|
| **Installation ID** | `a1b2c3d4-e5f6...` | A random UUID generated on first run. Allows us to count unique active installations without knowing *who* you are. |
| **App Version** | `2.3.0+a0736ed` | Helps us track adoption of new releases. |
| **Platform** | `Linux-x86_64` | Helps us decide which Docker architectures to build. |
| **Configuration** | `{ "model_type": "eva02", "birdnet": true }` | Helps us understand which features are popular. |

## What is NEVER Collected?
- ❌ **Your Images or Videos:** We never see your birds or your camera feeds.
- ❌ **Detection Data:** We don't collect species names, times, or locations.
- ❌ **Credentials:** No passwords, tokens, or API keys.
- ❌ **Network Info:** No local IP addresses or network topology.

## Transparency
When you enable Telemetry in the UI (**Settings > Appearance > Telemetry**), a "Transparency" box appears. This shows you:
1. Your unique Installation ID.
2. The exact data points being sent.

You can toggle this feature off at any time, and the background reporting service will stop immediately.
