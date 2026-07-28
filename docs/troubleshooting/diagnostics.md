# Troubleshooting & Diagnostics

If you are experiencing issues with detections or integrations, use the built-in diagnostic tools.

## Container startup takes time

The monolithic container serves the YA-WAMF web shell before the backend is ready. During startup,
the service screen shows the current phase and phase-based progress while YA-WAMF:

1. checks which inference hardware is available
2. loads the selected bird model and runs its bounded accelerator self-test when applicable
3. prepares the detection database
4. starts event, media, notification, and maintenance services

This is not the full hardware-validation sweep. YA-WAMF runs that larger, multi-model comparison
only when you start it from setup or diagnostics. The synthetic accelerated-versus-CPU startup
benchmark is also off by default unless you set `CLASSIFIER_RUNTIME_BENCHMARK_ENABLED=true`.

To inspect the same non-sensitive status outside the browser:

```bash
curl -fsS http://localhost:9852/startup-status.json
```

The progress percentage represents completed startup phases, not an elapsed-time estimate. If the
screen reports a startup issue or switches to **Not responding**, check the container health and
startup logs; the UI keeps a failed startup distinct from normal model-loading work.

`model_unavailable` is recoverable: the web/backend startup continues so an owner can open the
setup wizard, keep the bundled MobileNet fallback, or download and validate another model. It does
not mean a missing classifier was reported as ready. Published images are gated by a model-load and
inference smoke test, so seeing this phase on a clean image should be treated as a model/storage
problem and included in a diagnostic bundle.

## MQTT Pipeline
If detections aren't appearing, verify the MQTT connection:
1. Go to **Settings > Integrations**.
2. Click **Test MQTT Pipeline**.
3. Check the backend logs. You should see "Published MQTT message".
4. Use an external tool like `mosquitto_sub` to verify the message reached the broker:
   ```bash
   mosquitto_sub -h localhost -t "yawamf/test" -v
   ```

## 🔊 Audio Correlation Issues
If Birds are appearing on the dashboard but never have the **"Verified"** audio badge:

1.  **Check Sensor ID:** Verify that the Sensor ID in the **Recent Audio** widget matches your mapping in Settings.
2.  **Verify Timezone (TZ):** Run `docker exec -it yawamf-monalithic date` (or `yawamf-backend` for the legacy split deployment) and compare it to the time on your host. If they differ, audio correlation will fail because events won't align. Ensure all containers (Frigate, BirdNET, YA-WAMF) have the same `TZ` environment variable.
3.  **Buffer Window:** Correlation only works for events within your configured `audio_correlation_window_seconds` (default ±300 seconds).

## 🌐 Network Connectivity
Since YA-WAMF runs in a Docker network, it must be able to reach your other services. You can test this from inside the container:

```bash
# Test connection to Frigate (monolithic deployment)
docker exec yawamf-monalithic curl -s http://frigate:5000/api/version

# Test connection to MQTT
docker exec yawamf-monalithic ping -c 1 mosquitto
```

Replace `yawamf-monalithic` with `yawamf-backend` if you are on the legacy split deployment.

If these fail, verify that all services are on the same `DOCKER_NETWORK` in your `.env` file.

## 🔒 Permission Issues
If you see `PermissionError` in your backend logs or the container fails to start after an update:

1.  **Get exact UID/GID values to use:**
    ```bash
    id -u
    id -g
    ```
2.  **Set `.env` values to match those exact numbers:**
    ```env
    PUID=1000
    PGID=1000
    ```
3.  **Fix host directory ownership/permissions:**
    ```bash
    mkdir -p config data
    sudo chown -R "${PUID}:${PGID}" config data
    sudo chmod -R u+rwX,g+rwX config data
    ```
4.  **Verify your compose/stack mounts and user are correct:**
    ```yaml
    services:
      backend:
        user: "${PUID}:${PGID}"
        volumes:
          - ./config:/config
          - ./data:/data
    ```
5.  **Test write access from inside the running container:**
    ```bash
    # Monolithic deployment:
    docker compose exec yawamf sh -lc 'id && ls -ld /config /data && touch /data/.perm_test && rm -f /data/.perm_test'
    # Legacy split deployment:
    # docker compose exec yawamf-backend sh -lc 'id && ls -ld /config /data && touch /data/.perm_test && rm -f /data/.perm_test'
    ```
6.  **Check logs for remaining denials:**
    ```bash
    # Monolithic deployment:
    docker compose -f docker-compose.monolith.yml logs yawamf | grep -n "Permission denied\|EACCES"
    # Legacy split deployment:
    # docker compose logs yawamf-backend | grep -n "Permission denied\|EACCES"
    ```

If step 5 fails, the most common cause is editing one path but mounting a different host path in Portainer. Fix ownership on the actual mounted source path shown in the stack volume mapping.

## ⚡ Inference acceleration diagnostics

YA-WAMF exposes image, runtime, and device diagnostics under
**Settings → Detection → Runtime diagnostics** and at
`GET /api/classifier/status`.

### What to check first (UI)

Check these in order:

- **Image** — the packaged runtime family (`full`, `cpu`, `intel`, `cuda`, or `rpi`)
- **Packaged** — providers intentionally included in that image
- **CUDA**, **OpenVINO**, **Intel GPU**, and **Intel NPU** — runtime/device probe results
- **Selected** — the saved provider preference
- **Active** and **Backend** — what the loaded model is actually using
- **Fallback** or the image/provider mismatch warning
- **OpenVINO diagnostics** — shown when OpenVINO is unavailable or a device plugin fails

This usually tells you whether the problem is:

- an image that does not package the selected runtime
- missing runtime/library support inside a matching image
- device pass-through (`/dev/dri`)
- group permissions
- provider fallback at runtime

### Quick API check

From the host (monolithic deployment):

```bash
curl -fsS http://localhost:9852/api/classifier/status
```

From inside the Docker network or within the container (monolithic):

```bash
docker exec yawamf-monalithic curl -fsS http://127.0.0.1:8000/api/classifier/status
```

Legacy split deployment (from the Docker network):

```bash
curl -fsS http://yawamf-backend:8000/api/classifier/status
```

Key fields:

- `image_flavor`, `packaged_inference_providers`, and `image_flavor_warning`
- `host_available_providers` (packaged providers that passed runtime/device probes,
  before model compatibility is applied)
- `available_providers` (packaged providers that passed runtime/device probes and
  are globally safe or currently validated for the active model)
- `provider_preference_order` (the active provider followed by its concrete
  runtime-recovery path)
- `active_model_candidate_providers`, `active_model_validated_providers`, and
  `validated_provider_preference_order`
- `cuda_provider_installed` vs `cuda_available`
  - `true` / `false` means the CUDA-capable ONNX Runtime wheel is installed, but no usable NVIDIA GPU is available to the container
- `openvino_available`
- `openvino_devices`
- `intel_gpu_available` and `intel_npu_available`
- `active_model_id`, `selected_provider`, and `active_provider`
- `host_device_eligibility`
- `fallback_reason`
- `model_config_warnings`
- `openvino_import_error`
- `openvino_probe_error`
- `openvino_gpu_probe_error`
- `dev_dri_present`, `dev_dri_entries`, `process_groups`

`image_flavor_warning: selected_provider_not_packaged` means the saved provider
does not belong to this image. YA-WAMF keeps that saved selection intact and
uses an actually available fallback. Switch to the full or matching provider image using the
[safe flavor procedure](../setup/hardware-acceleration.md#switch-safely-between-flavors);
do not try to install packages into the running container.

Provider validation is installation- and model-specific. The global registry separates safe
providers from reviewed candidates; the sweep only tests candidates that the running image
packages and the host probe exposes. Schema-4 evidence is tied to the model checksum, inference
package versions, kernel, architecture, visible accelerator identity, and image flavour. Evidence
left by a different artifact, runtime, host, kernel, or flavour is rejected and the model returns
to its globally safe baseline until revalidated. A remaining `model_config_warnings` entry is
therefore actionable: repair or download the model again in **Settings → Detection → Model
Manager**, or include it in a diagnostics bundle when asking for help.

### Intel iGPU (OpenVINO) checklist

Replace `yawamf-monalithic` below with `yawamf-backend` if you are on the legacy split deployment.

1. **Confirm the image packages OpenVINO.** **Image** must be `full` or `intel`,
   and **Packaged** must include `intel_gpu`. If not, switch image before
   debugging the device.
2. **Confirm `/dev/dri` is mounted**
   ```bash
   docker exec yawamf-monalithic sh -lc 'ls -l /dev/dri'
   ```
3. **Confirm container user/group can access the device nodes**
   ```bash
   docker exec yawamf-monalithic sh -lc 'id && ls -ln /dev/dri'
   ```
   The backend user/group list must include the numeric GIDs shown on `/dev/dri/card0` and `/dev/dri/renderD128` (often `video`/`render`, but IDs vary by host).
4. **Check OpenVINO GPU plugin errors**
   - If `openvino_gpu_probe_error` mentions `libOpenCL.so.1`, the image is missing OpenCL runtime libraries.
   - If it reports no supported devices, the Intel GPU userspace/driver stack is not available to the container.

### ConvNeXt OpenVINO model patch (unsupported ONNX sequence ops)

If `convnext_large_inat21` fails with:

- `SequenceEmpty`
- `SequenceInsert`
- `ConcatFromSequence`

you can generate an OpenVINO-compatible ONNX variant with:

```bash
cd backend
python3 scripts/patch_convnext_openvino_model.py \
  --model /data/models/convnext_large_inat21/model.onnx \
  --replace
docker restart yawamf-monalithic
```

(Use `docker restart yawamf-backend` if you are on the legacy split deployment.)

The script creates a timestamped backup of the original model before replacement.

### NVIDIA CUDA checklist

1. **Confirm the image packages CUDA.** **Image** must be `full` or `cuda`, and
   **Packaged** must include `cuda`.
2. **Confirm CUDA status fields**
   - `cuda_provider_installed: true`
   - `cuda_available: true`
3. **Confirm container GPU passthrough is configured**
   - Docker host has **NVIDIA Container Toolkit** installed
   - Backend container is started with NVIDIA GPU access (`gpus: all` or equivalent runtime settings)
4. **If `cuda_provider_installed=true` but `cuda_available=false`**
   - The CUDA-capable ONNX Runtime wheel is present, but YA-WAMF could not access a real NVIDIA CUDA device.
5. **If `cuda_available=true` but `Active` falls back to CPU**
   - YA-WAMF now validates the actual ONNX Runtime session providers and will report a CPU fallback if the session initializes without `CUDAExecutionProvider`.

### Startup Health Signals
Use these endpoints and lifecycle logs to quickly pinpoint startup failures:

- `GET /health`: includes `startup_warnings` and sets `status=degraded` if a non-fatal startup phase failed.
- `GET /ready`: returns `200` only when backend startup is ready for traffic; returns `503` with details when DB or startup phases are not ready.
- Backend logs now emit per-phase lifecycle events:
  - `Lifecycle phase starting`
  - `Lifecycle phase completed`
  - `Lifecycle phase failed`

If startup fails, search logs for `phase=` to identify the exact failing step (`db_init`, `telemetry_start`, `auto_video_classifier_start`, etc.).

## 🖥 UI Issues
If the dashboard is blank or buttons don't work:

1. **Refresh once:** YA-WAMF revalidates its application document after every deploy and recovers
   automatically from most stale page chunks. If a tab stayed open through several updates, refresh it.
2. **Check API reachability:** Open **Settings** or request `/api/version` directly. If `/api/*`
   calls fail with `401`, `404`, `500`, or `502`, the UI can appear empty. Make sure the reverse
   proxy routes `/api` to the backend.
3. **Check the live connection:** YA-WAMF uses Server-Sent Events (SSE) for live updates. If the
   header says **Offline**, confirm the reverse proxy allows long-lived responses and preserves
   the forwarding headers.
4. **Check page-file requests:** Browser developer tools should show fingerprinted `/assets/*`
   files returning `200` (or a cached response), with JavaScript and CSS compressed. Repeated `404`
   responses usually mean an upstream proxy cached `index.html`; configure that proxy to revalidate
   HTML while allowing the bundled YA-WAMF cache headers on fingerprinted assets.
5. **Check the console:** A failed page download now shows an in-place retry. If retry continues to
   fail, inspect the browser console for the requested asset URL and the HTTP status.
6. **Reset an installed PWA only as a last resort:** If an old installed Progressive Web App (PWA)
   remains stale after a normal refresh, clear the site's data once and reopen it.

## Frigate "Event Not Found" Detections

If a detection shows `video_classification_error: event_not_found` or the **Errors** page shows diagnostic entries with `reason_code: event_not_found` or `reason_code: precheck_cache_bypass`, see the dedicated explanation:

→ [Frigate "Event Not Found" Explained](frigate-event-not-found.md)

## Missed Detections (Backfill)
If the Backfill tool is skipping events you expected to see, check the **Skipped Breakdown** table in the settings page after a scan.

**Audio context note:** Backfill reprocesses **Frigate** events only. BirdNET-Go audio confirmations are not backfilled unless you have a separate historical audio source to import. After a database reset, audio context will only appear for new detections once BirdNET-Go is running again.

| Reason | Explanation |
|--------|-------------|
| **Already in Database** | The event ID already exists and the AI score was not improved by this scan. |
| **Below Confidence Threshold** | The AI identified a bird but the score was lower than your "Threshold" setting. |
| **Below Minimum Floor** | The score was so low it was discarded as a potential false positive. |
| **Filtered (Blocked Label)** | The species is on your Blocklist. |
| **Frigate Snapshot Missing** | Frigate returned a 404 or empty file for the snapshot request. |

## Logs
For deep inspection, view the container logs:
```bash
# Monolithic deployment:
docker compose -f docker-compose.monolith.yml logs yawamf -f
# Legacy split deployment:
# docker compose logs yawamf-backend -f
```
Look for lines like:
- `Processing MQTT event`: Backend saw a bird event.
- `Saved detection`: A bird was successfully identified and stored.
- `Taxonomy lookup`: The system is fetching names from iNaturalist.
