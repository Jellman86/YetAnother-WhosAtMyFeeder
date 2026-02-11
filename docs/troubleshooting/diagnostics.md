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
3.  **Buffer Window:** Correlation only works for events within ±30 seconds of each other.

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

1.  **Check Ownership:** Ensure the `config` and `data` directories on your host are owned by the user running the containers (default UID 1000).
    ```bash
    sudo chown -R 1000:1000 config data
    ```
2.  **Verify .env:** Ensure `PUID` and `PGID` are set correctly in your `.env` file to match your host user.
3.  **Docker Logs:** Check for explicit permission denied messages:
    ```bash
    docker logs yawamf-backend | grep "Permission denied"
    ```

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
