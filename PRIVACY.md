# Privacy Policy

YA-WAMF is a self-hosted application. I believe your data belongs to you.

## Data Collection

*   **Images:** The application downloads and stores snapshots from your local Frigate instance. These images remain on your server (in the `/data` volume) and are **never** uploaded to any cloud service by this software.
*   **Database:** Detection metadata (species, score, time) is stored locally in `speciesid.db`.
*   **Telemetry:** This application **does not** collect or transmit any usage telemetry or analytics.

## Third-Party Services

*   **Frigate:** This application interacts with your local Frigate NVR. Please refer to Frigate's documentation regarding its data handling.
*   **TensorFlow Lite:** Inference runs locally on your CPU/EdgeTPU. No data is sent to Google.

## User Responsibility

*   You are responsible for securing access to your instance (e.g., using a VPN or reverse proxy with authentication).
*   Please respect local privacy laws regarding video surveillance and storage.
