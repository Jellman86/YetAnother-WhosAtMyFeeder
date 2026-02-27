# Troubleshooting & Diagnostics

If you are experiencing issues with detections or integrations, use the built-in diagnostic tools.

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
2.  **Verify Timezone (TZ):** Run `docker exec -it yawamf-backend date` and compare it to the time on your host. If they differ, audio correlation will fail because events won't align. Ensure all containers (Frigate, BirdNET, YA-WAMF) have the same `TZ` environment variable.
3.  **Buffer Window:** Correlation only works for events within your configured `audio_correlation_window_seconds` (default ±300 seconds).

## 🌐 Network Connectivity
Since YA-WAMF runs in a Docker network, it must be able to reach your other services. You can test this from inside the backend container:

```bash
# Test connection to Frigate
docker exec yawamf-backend curl -s http://frigate:5000/api/version

# Test connection to MQTT (if mosquitto has a healthcheck/api)
docker exec yawamf-backend ping -c 1 mosquitto
```

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
    docker compose exec yawamf-backend sh -lc 'id && ls -ld /config /data && touch /data/.perm_test && rm -f /data/.perm_test'
    ```
6.  **Check logs for remaining denials:**
    ```bash
    docker compose logs yawamf-backend | rg -n "Permission denied|EACCES"
    ```

If step 5 fails, the most common cause is editing one path but mounting a different host path in Portainer. Fix ownership on the actual mounted source path shown in the stack volume mapping.

## ⚡ GPU Acceleration Diagnostics (CUDA / OpenVINO)

YA-WAMF exposes acceleration diagnostics in **Settings > Detection** and `GET /api/classifier/status`.

### What to check first (UI)

In **Settings > Detection** look at:

- `CUDA` badge
- `OpenVINO` badge
- `Intel GPU` badge
- `Selected provider`
- `Active provider`
- `Fallback reason`
- `OpenVINO diagnostics` block (shown when OpenVINO is unavailable, or when the GPU plugin fails)

This usually tells you whether the problem is:

- missing runtime/library support
- device pass-through (`/dev/dri`)
- group permissions
- provider fallback at runtime

### Quick API check

```bash
curl -sS http://yawamf-backend:8000/api/classifier/status
```

Key fields:

- `cuda_provider_installed` vs `cuda_available`
  - `true` / `false` means the CUDA-capable ONNX Runtime wheel is installed, but no usable NVIDIA GPU is available to the container
- `openvino_available`
- `openvino_devices`
- `intel_gpu_available`
- `fallback_reason`
- `openvino_import_error`
- `openvino_probe_error`
- `openvino_gpu_probe_error`
- `dev_dri_present`, `dev_dri_entries`, `process_groups`

### Intel iGPU (OpenVINO) checklist

1. **Confirm `/dev/dri` is mounted**
   ```bash
   docker exec yawamf-backend sh -lc 'ls -l /dev/dri'
   ```
2. **Confirm container user/group can access the device nodes**
   ```bash
   docker exec yawamf-backend sh -lc 'id && ls -ln /dev/dri'
   ```
   The backend user/group list must include the numeric GIDs shown on `/dev/dri/card0` and `/dev/dri/renderD128` (often `video`/`render`, but IDs vary by host).
3. **Check OpenVINO GPU plugin errors**
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
docker restart yawamf-backend
```

The script creates a timestamped backup of the original model before replacement.

### NVIDIA CUDA checklist

1. **Confirm CUDA status fields**
   - `cuda_provider_installed: true`
   - `cuda_available: true`
2. **Confirm container GPU passthrough is configured**
   - Docker host has **NVIDIA Container Toolkit** installed
   - Backend container is started with NVIDIA GPU access (`gpus: all` or equivalent runtime settings)
3. **If `cuda_provider_installed=true` but `cuda_available=false`**
   - The CUDA-capable ONNX Runtime wheel is present, but YA-WAMF could not access a real NVIDIA CUDA device.
4. **If `cuda_available=true` but `Active provider` falls back to CPU**
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
1.  **Clear Browser Cache:** Svelte 5 updates sometimes require a hard refresh (`Ctrl + F5`).
1.  **Check API Reachability:** Open `Settings` or hit `/api/version` directly. If `/api/*` calls fail (401/404/500/502), the UI can appear empty. This is commonly a reverse-proxy routing issue (make sure `/api` routes to the backend).
1.  **Check SSE Connection:** YA-WAMF uses Server-Sent Events for live updates. Look for a green "Live" badge in the header. If it says "Offline", check your reverse proxy (Nginx/Traefik) allows long-lived connections and keeps headers.
1.  **Logs:** Check for 404 or 500 errors in the frontend console (`F12` in your browser).
1.  **PWA/Service Worker:** If you installed the PWA, stale cached assets can survive refreshes. Try a hard refresh, or clear site data for the domain.

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
docker compose logs yawamf-backend -f
```
Look for lines like:
- `Processing MQTT event`: Backend saw a bird event.
- `Saved detection`: A bird was successfully identified and stored.
- `Taxonomy lookup`: The system is fetching names from iNaturalist.
