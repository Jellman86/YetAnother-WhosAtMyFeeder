# Integration Testing Requests

Some third-party account flows still need end-to-end verification with real credentials. CUDA has been tested on an RTX 4070 with the published `dev-cuda` image; that evidence covers the tested models and workload, not every classifier or driver. See [Known gaps](ISSUES.md) for the current evidence and remaining work.

If you can test any of the items below, please open a GitHub issue with results. Thank you.

## What To Include In A Test Report

- Which integration you tested (Gmail OAuth, Outlook OAuth, Telegram, Pushover, iNaturalist, CUDA inference provider)
- Whether you were on `dev` images or a tagged release
- The exact error message shown in the UI (if any)
- Redacted backend logs around the failure (remove tokens, emails, chat IDs)
- Your SMTP provider + port if testing password SMTP (587 vs 465 matters)

## Email OAuth (Gmail)

Goal: connect OAuth and send an email via SMTP XOAUTH2.

Checklist:
1. Configure Gmail OAuth Client ID/Secret in Settings.
2. Click Connect Gmail and complete the OAuth flow.
3. Confirm the connected email is shown in Settings.
4. Click Send Test Email.
5. Re-test after the provider-reported access-token expiry to confirm refresh works. Use a disposable account when deliberately manipulating token state.

Notes:
- SMTP XOAUTH2 typically requires the full mail scope (`https://mail.google.com/`).

## Email OAuth (Outlook / Microsoft 365)

Goal: connect OAuth and send an email via SMTP XOAUTH2, including refresh tokens.

Checklist:
1. Configure Microsoft OAuth Client ID/Secret in Settings.
2. Click Connect Outlook and complete the OAuth flow.
3. Confirm the connected email is shown in Settings.
4. Click Send Test Email.
5. Wait for access token expiry and re-test to confirm refresh works.

Notes:
- This uses Microsoft identity platform v2.0 with delegated SMTP permission scope.

## Email (Password SMTP)

Goal: send an email via traditional SMTP with STARTTLS/TLS.

Checklist:
1. Configure SMTP host, port, from/to, username/password.
2. If your provider uses port 587, ensure TLS/STARTTLS is enabled.
3. Click Send Test Email.

If it fails, include:
- Port number (587 or 465)
- Whether TLS/STARTTLS toggle was enabled

## Telegram Bot API Notifications

Goal: send a Telegram notification (with and without a snapshot).

Checklist:
1. Configure bot token and chat ID in Settings.
2. Click Send Test Notification (Telegram).
3. Verify message formatting when species/camera contains special characters.
4. Trigger a real detection notification if possible (snapshot and no-snapshot paths).

Notes:
- Telegram has message length limits (caption vs message body). If you hit truncation, please report what content caused it.

## Pushover Notifications

Goal: send a Pushover notification (with and without a snapshot).

Checklist:
1. Configure Pushover User Key and API Token in Settings.
2. Click Send Test Notification (Pushover).
3. Trigger a real detection notification if possible (snapshot and no-snapshot paths).
4. Confirm message title/body fields render as expected in the Pushover app.

If it fails, include:
- Whether test send failed immediately or timed out
- Redacted response/error from backend logs
- Whether snapshot attachments were enabled

## iNaturalist Submissions

Goal: connect OAuth and submit a detection as an observation, including photo upload.

Checklist:
1. Enable iNaturalist integration and configure Client ID/Secret.
2. Click Connect iNaturalist and complete OAuth.
3. Open a detection modal and load the iNaturalist draft panel.
4. Review the species, photograph and location, then submit only an observation you intend to publish to that account.
5. Confirm the observation exists on your iNaturalist account and the photo upload succeeded.

Notes:
- iNaturalist requires "App Owner" approval before you can create OAuth apps, which is why this has been hard to test without community help.

## NVIDIA CUDA Inference Provider

Goal: extend CUDA validation on real NVIDIA hardware beyond the tested accurate crop detector and RoPE ViT-B/14. Use the strict [model/provider gate](docs/development/testing.md#mandatory-local-modelprovider-gate) first; provider compatibility does not measure species accuracy.

Checklist:
1. Use the unsuffixed full image or the matching `-cuda` image. Confirm **Settings → Detection → Runtime diagnostics** shows `cuda` under **Packaged**; the CPU, Intel, and Raspberry Pi images do not contain the CUDA runtime.
2. Ensure the container runtime exposes your NVIDIA GPU (`nvidia-smi` works in the backend container). The host must provide NVIDIA driver/runtime passthrough even when CUDA userspace is packaged in the image.
3. Under **Settings → Detection → Inference Provider**, select **NVIDIA CUDA** (or **Auto** if CUDA is the preferred available path on your host).
4. Choose an installed model that passed the strict gate and its on-host validation. Test additional families separately; larger models can have different memory and driver requirements.
5. Confirm `/api/classifier/status` reports `image_flavor` as `full` or `cuda`, lists `cuda` in `packaged_inference_providers`, and reports CUDA as available and active during inference.
6. Run at least one live detection and one manual reclassification; confirm both complete without fallback errors.
7. If possible, restart containers and re-verify CUDA still initializes and remains selected.

If it fails, include:
- Output from `/api/classifier/status`
- Backend logs around model initialization/provider fallback
- `nvidia-smi` output from host and backend container (redacted if needed)

## MQTT Liveness Soak Regression (Issue #22)

Goal: validate sustained Frigate + BirdNET MQTT ingestion continuity and detect Frigate-stall/BirdNET-active regressions.

Use a disposable YA-WAMF instance, database, media directory and MQTT broker. These harnesses
publish synthetic events and can save history, start jobs and trigger outbound notifications or
reports. Disable external notification, BirdWeather and Frigate write-back integrations in that
test instance. Do not point the publisher at a live feeder broker. Read-only Frigate media can
supply replay inputs without granting the test instance write access.

Harness (run from the repository root):

1. Run `scripts/run_issue22_soak.py` using the backend virtual environment.
2. The harness publishes synthetic MQTT traffic and polls `/health`.
3. It writes:
   - `samples.ndjson` (per-poll data/errors)
   - `summary.json` (pass/fail + reasons + stall incidents)

Quick example:

```bash
backend/.venv/bin/python scripts/run_issue22_soak.py \
  --backend-url http://127.0.0.1:9852 \
  --mqtt-host 127.0.0.1 \
  --mqtt-port 1883 \
  --duration-seconds 1800 \
  --poll-interval-seconds 5
```

When reporting results, include:

1. Command used (redact tokens/secrets).
2. `summary.json` status + failure reasons (if any).
3. Relevant `samples.ndjson` window around any reported stall incident.

If natural feeder traffic is quiet, prefer replay mode against a reachable Frigate API:

1. Pass `--frigate-api-url <base_url>`.
2. Supply the disposable instance's owner JWT through `SOAK_AUTH_TOKEN`, avoiding secrets in shell history and command-line arguments.
3. Use `--replay-unsaved-frigate-limit 1` to replay a real unsaved Frigate bird event with snapshot.
4. Disable continuous synthetic publishers with `--disable-frigate-publisher --disable-birdnet-publisher` when you want a clean persistence-only proof.

## Issue #33 Fixture Replay and Stall Regression

Goal: guard the historical issue `#33` failure modes with example images and a
controlled MQTT stall:

- live Frigate/BirdNET ingest should keep completing events under load
- live snapshot classification should not drop from admission timeouts
- maintenance video analysis should not trip the video circuit
- a Frigate-topic pause should not stop BirdNET liveness or leave Frigate stuck after resume

Harness:

1. Run `scripts/run_issue33_harness.py` from the repository root using the backend virtual environment and the same disposable boundaries as the liveness soak.
2. Prefer `--stress-profile issue33-fixture-replay` when you want repeatable example-image load.
3. Prefer `--stress-profile issue33-stall-probe --scenario mqtt-no-frigate-resume` when you want the lower-pressure MQTT pause/resume check.
4. Use MQTT credentials if your broker requires authentication, and redact them in reports.

Supply the disposable instance password through `SOAK_PASSWORD` and broker password through
`SOAK_MQTT_PASSWORD` when required. Keep captured environment values and output private.

Fixture replay example:

```bash
backend/.venv/bin/python scripts/run_issue33_harness.py \
  --backend-url http://127.0.0.1:9852 \
  --stress-profile issue33-fixture-replay \
  --scenario combined \
  --username <owner_username> \
  --mqtt-host 127.0.0.1 \
  --mqtt-port 1883 \
  --mqtt-username <mqtt_username> \
  --fixture-image-dir <directory_with_example_images>
```

Stall-probe example:

```bash
backend/.venv/bin/python scripts/run_issue33_harness.py \
  --backend-url http://127.0.0.1:9852 \
  --stress-profile issue33-stall-probe \
  --scenario mqtt-no-frigate-resume \
  --username <owner_username> \
  --mqtt-host 127.0.0.1 \
  --mqtt-port 1883 \
  --mqtt-username <mqtt_username>
```

When reporting results, include:

1. Command used (redact tokens, passwords, and owner credentials).
2. `summary.json` status + `evaluation.failure_reasons`.
3. `event_started_delta`, `event_completed_delta`, `event_dropped_delta`, `live_image_admission_timeouts_delta`, `classify_snapshot_overloaded_delta`, `video_failure_count_delta`, and `video_circuit_open_observed`.
4. For stall-probe runs, also include `frigate_stall_effective`, `topic_liveness_reconnects_delta`, and the configured backend Frigate-topic stale threshold.

Note: if the backend's Frigate-topic stale threshold is still the production
default of 1800 seconds, a 900 second stall-probe validates pause/resume health
but does not force a stale-topic reconnect unless the threshold is lowered or
the run is extended past the threshold.
