# Privacy Policy

YA-WAMF is a self-hosted application. I believe your data belongs to you.

## Data Collection

*   **Images:** The application downloads and stores snapshots from your local Frigate instance. Local species classification stays on your server. Optional integrations can send media outside it: AI Naturalist can send selected frames to the configured LLM provider, notifications can attach photos, and an owner-reviewed iNaturalist submission uploads its photograph. Enable those features only for destinations you intend to share with. Retained media defaults to `/config/media_cache` (or the configured `MEDIA_CACHE_DIR`); favourite archives default to `/config/archive`.
*   **Database:** Detection metadata (species, score, time) is stored locally in `speciesid.db`.
*   **Telemetry:** Anonymous usage telemetry and anonymous health diagnostics are separate,
    optional settings and are disabled by default. When enabled, the app sends configuration and
    runtime capability summaries or sanitized diagnostic codes; it never sends camera names,
    hostnames, URLs, credentials, images, video, or raw diagnostic messages. The receiver stores a
    one-way hash of the random installation ID, suppresses public cohorts smaller than three
    installations, and applies bounded retention. Turning both telemetry settings off requests
    deletion from both telemetry databases; after confirmation, the local random identity is
    rotated so a later opt-in cannot be linked to the former history.

## Third-Party Services

*   **Frigate:** This application interacts with your local Frigate NVR. Please refer to Frigate's documentation regarding its data handling.
*   **Local models:** ONNX Runtime, OpenVINO and TensorFlow Lite classification run locally. Downloading model weights contacts the configured release host; inference does not upload the image to the model author.
*   **Optional services:** LLM analysis, notification channels, BirdWeather, enrichment providers and owner-reviewed exports have separate data-sharing boundaries. BirdWeather reports species, confidence, time and configured location; eBird/iNaturalist lookups can use configured location. Review the [integration guides](docs/index.md#-integrations) and [telemetry privacy boundaries](docs/features/telemetry.md) before enabling them.
*   **Public access:** Guests can see only the history and media permitted by **Settings → Security**. Sharing photographs, video, audio or camera names is an explicit owner decision.
*   **Support bundles:** An owner-requested diagnostics file is downloaded locally and is not automatically sent to the project. Review the file and your notes before attaching it publicly.

## User Responsibility

*   Retention and explicit deletion can permanently remove local records and ordinary media. Favourite protection and retention floors have limits; see [Favourites](docs/features/favourites.md). Local deletion does not remove a copy already sent to an external service.
*   You are responsible for securing access to your instance (e.g., using a VPN or reverse proxy with authentication).
*   Please respect local privacy laws regarding video surveillance and storage.
