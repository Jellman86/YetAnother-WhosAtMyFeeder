# Upgrade an existing YA-WAMF installation

Keep your configuration, detection history and photographs when updating the image.
This guide describes current repository behaviour; read the release notes and documentation
for the exact tag you install. The `models` release is a rolling asset catalogue, not an
application update.

## Before you update

1. Record the current image tag and deployment file.
2. Back up both persistent mounts, `/config` and `/data`, with YA-WAMF stopped or with
   a consistent storage snapshot. They contain credentials, detection history, the species
   catalogue, model files and retained media. Protect the backup like a password.
3. Keep the same mount paths and user permissions when recreating the container.
4. Read the selected release's **Before you update** notes. An image update can apply
   database migrations during startup. Automatic migration restore points are useful,
   but do not replace a current backup of both mounts.

For a Compose-managed installation, update through the existing project:

```bash
docker compose -f docker-compose.monolith.yml pull
docker compose -f docker-compose.monolith.yml up -d
```

If a Git-managed platform or Unraid owns your stack, use that platform's update
workflow instead. See [Unraid](docs/setup/unraid.md) and
[split-to-monolith migration](docs/setup/migrate-split-to-monolith.md).

## Check the updated installation

1. Wait for the container health check, then open the dashboard.
2. Confirm your saved cameras, recent detections and photographs are present.
3. Open **Settings → Detection → Runtime diagnostics**. Check the image family,
   selected provider, actual active provider and any fallback reason.
4. If model/runtime/hardware validation is stale, let automatic recovery finish or
   run the model compatibility check. Compatibility is not a species-accuracy score.
5. Check **Settings → Health** and the **Jobs** page for failed or waiting work.
   Network errors during a switch/router outage do not by themselves prove a model fault.

Unsuffixed image tags remain the full compatibility image. Optional `-cpu`,
`-intel` and `-cuda` variants keep the same volumes and application code for a given
commit. A same-commit flavour change needs no data migration; it can change the
available providers. See [hardware acceleration](docs/setup/hardware-acceleration.md).

## Retired media switches

Current builds always retain photographs and generated visit media locally, subject
to retention, per-species and size limits. Copies of Frigate's short event clips remain
optional. The old **Media Cache** and **Snapshots** enable switches are retired.

On the first load of an older configuration:

- If either old switch was off, best-available event snapshots are turned off once.
- If the old Media Cache switch was off, full-visit clips are also turned off once.
- An explicit current `MEDIA_CACHE__HIGH_QUALITY_EVENT_SNAPSHOTS` or
  `FRIGATE__RECORDING_CLIP_ENABLED` environment override takes precedence.

This avoids silently enabling expensive media work that the old switches prevented.
Review **Settings → Data → Snapshot quality** and **Settings → Connection → Full-visit clips**
if you want those options on. Save settings once to persist the one-time marker and
remove retired keys from `config.json`. Remove `MEDIA_CACHE__ENABLED` and
`MEDIA_CACHE__CACHE_SNAPSHOTS` from your deployment environment; startup warnings
identify any remaining retired switches.

A `media_cache.retention_days` value of `0` follows detection retention. A
`maintenance.retention_days` value of `0` keeps history indefinitely. Finite history
retention permanently deletes old visual and BirdNET-Go records, except protected
visual records. Size and per-species maximum limits can delete non-favourite media
while retaining detection rows. See [Data settings](docs/setup/configuration.md#data)
before changing limits.

## Models and catalogue-backed names

Updating does not automatically replace your selected classifier. The October models
require an application build containing their integration; published model files alone
cannot enable them in an older image.

Use **Settings → Detection → Model Manager** to download, validate and activate a model.
Registered classifier outputs are held in the species catalogue and bound to the
model checksum, so integrated downloads need no separate `labels.txt`. Custom and
legacy label-file fallback remains available. Do not replace a live species database
with a downloaded catalogue seed. See the
[October model catalogue](docs/features/model-catalogue-2026-10.md).

DINOv2 reads the saved feeder latitude and longitude at runtime. The setup wizard
and **Settings → Integrations → Location** edit the same values. Missing coordinates
use neutral metadata; date and location uncertainty are not supplied. Changing
coordinates reloads classifier workers.

## Authentication on older installations

Password authentication and read-only public access were introduced in v2.6.0.
An existing installation without authentication remains accessible until you enable
it; do that before exposing the UI or API beyond your trusted network.

1. Open **Settings → Security**, set an owner username and password, and enable
   **Authentication**.
2. Select **Apply settings** and confirm you can sign in.
3. Enable **Public Access** only if you want a guest view, then review its separate
   photograph, video, audio and history permissions.

The legacy `YA_WAMF_API_KEY` is still supported but deprecated. Confirm owner-login
access before removing it from the deployment environment and recreating the
container. Do not rely on the first-run endpoint to change an established account:
a completed account decision closes that unauthenticated endpoint.

If you lose the password, follow the
[password reset procedure](docs/features/authentication.md#password-reset). Stop the
app and back up the configuration first; both `auth.password_hash=null` and
`auth.initial_setup_complete=false` are needed to reopen account setup. Clearing
only the password hash does not reopen it.

## Roll back safely

A same-commit image-flavour rollback can reuse the current volumes. An application
version downgrade is different: an older image may not understand newer database,
configuration or model contracts. Do not assume changing only the tag reverses a
migration. Restore the previous image and its matching consistent `/config` and
`/data` backup when a release does not document backwards compatibility. Keep the
current volumes intact until you have verified the restored installation.

## Integrators using AI Naturalist output

Treat analysis text as Markdown. Do not depend on exact headings or paragraph order;
those depend on the configured prompt. Use the documented API and status codes to
distinguish saved analysis from failed provider requests. See the [API reference](docs/api.md).
