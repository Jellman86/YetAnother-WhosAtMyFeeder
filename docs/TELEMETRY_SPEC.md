# Telemetry Service Specification

## Overview
YA-WAMF includes an optional telemetry service to collect anonymous usage statistics. **Telemetry is disabled by default** and requires explicit opt-in.

## Why Telemetry?
As a solo developer working on this project, telemetry helps me understand if YA-WAMF is solving real problems for the broader bird enthusiast community, or if I'm primarily building for my own use case. Knowing that others find value in this work helps validate the time investment and guides development priorities - it's encouraging to know you're not building in isolation.

Additionally, the data helps to:
- Identify popular hardware platforms to prioritize optimization
- Understand which AI models are most commonly used
- Monitor version adoption rates to ensure users are on stable builds

## Data Collection Policy

### What is Collected?
The heartbeat payload is strictly limited to metadata about the installation and environment:
- **Installation ID**: A random UUID generated once per installation. It is not linked to any personal identity.
- **Application Version**: The current version/build of YA-WAMF.
- **Platform Metadata**: Operating system type, release version, and machine architecture (e.g., Linux x86_64).
- **Configuration Flags**: Enabled features such as BirdNET integration, LLM providers, and Media Caching.
- **Geography**: The approximate country derived from the Cloudflare request header (the IP address itself is **not** stored in the database).

### What is NOT Collected?
- **No Private Data**: No audio recordings, video clips, or snapshots are ever sent.
- **No User Content**: No bird detection transcripts, species names, or scientific data are collected.
- **No PII**: No names, email addresses, IP addresses, or precise locations are stored.

## Technical Details

### Endpoint
- **URL**: `https://yawamf-telemetry.ya-wamf.workers.dev/heartbeat`
- **Frequency**: Once every 24 hours while the application is running.

### Payload Schema
```json
{
  "installation_id": "string (UUID)",
  "version": "string (e.g. 2.0.0)",
  "platform": {
    "system": "string (e.g. Linux)",
    "release": "string",
    "machine": "string"
  },
  "configuration": {
    "model_type": "string",
    "birdnet_enabled": "boolean",
    "birdweather_enabled": "boolean",
    "llm_enabled": "boolean",
    "llm_provider": "string",
    "media_cache_enabled": "boolean"
  }
}
```

## User Control (Opt-In)
Telemetry is **disabled by default** and completely optional. Users who wish to help improve YA-WAMF can opt in at any time via the **Settings > Connections > Telemetry** toggle in the UI. You can also disable it at any time if you change your mind.

On first launch, you may see a friendly banner inviting you to opt in - this can be dismissed and won't appear again.

## Source Code & Transparency
We believe in full transparency regarding the data we collect. You can inspect exactly how the heartbeat is constructed and transmitted in the backend source code:

- **[Telemetry Service (Backend)](../backend/app/services/telemetry_service.py)**: This module handles the generation of the anonymous Installation ID, gathers the metadata defined above, and transmits the payload via HTTPS.

**Note on Repository Privacy**: While the client-side reporting logic is public, the `apps/telemetry-worker` (the receiver) is excluded from the public repository to protect infrastructure secrets such as database IDs and API keys. The receiver is a standard implementation using Cloudflare Workers and D1.
