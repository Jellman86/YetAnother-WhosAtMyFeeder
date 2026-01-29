# Telemetry & Usage Metrics

YA-WAMF includes an optional telemetry system designed to help me understand how the software is used. I follow a strict **privacy-first** philosophy.

## Default State: Disabled
Telemetry is **disabled by default**. No data is sent unless you explicitly turn it on in the Settings.

## Philosophy
I believe open-source software should be transparent. I only collect high-level aggregate data to help answer questions like:
- "How many people are using the new EVA-02 model vs the older MobileNet?"
- "Is the BirdNET integration widely used?"
- "What platforms (ARM/x86) should I prioritize for optimization?"

## What is Collected?
When enabled, the system sends a lightweight "heartbeat" JSON payload once every 24 hours.

### The Payload
| Field | Example | Purpose |
|-------|---------|---------|
| **Installation ID** | `a1b2c3d4-e5f6...` | A random UUID generated on first run. Allows me to count unique active installations without knowing *who* you are. |
| **App Version** | `2.3.0+a0736ed` | Helps me track adoption of new releases. |
| **Platform** | `Linux-x86_64` | Helps me decide which Docker architectures to build. |
| **Configuration** | `{ "model_type": "eva02", "birdnet": true }` | Helps me understand which features are popular. |

## What is NEVER Collected?
- ❌ **Your Images or Videos:** I never see your birds or your camera feeds.
- ❌ **Detection Data:** I don't collect species names, times, or locations.
- ❌ **Credentials:** No passwords, tokens, or API keys.
- ❌ **Network Info:** No local IP addresses or network topology.

## User Interface & Transparency

When you enable Telemetry in the UI (**Settings > Connections > Telemetry**), a "Transparency" box appears. This shows you:
1. Your unique Installation ID.
2. The exact data points being sent.

You can toggle this feature off at any time, and the background reporting service will stop immediately.
