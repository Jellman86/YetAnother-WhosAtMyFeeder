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

## Missed Detections (Backfill)
If the Backfill tool is skipping events you expected to see, check the **Skipped Breakdown** table in the settings page after a scan.

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
docker compose logs backend -f
```
Look for lines like:
- `Processing MQTT event`: Backend saw a bird event.
- `Saved detection`: A bird was successfully identified and stored.
- `Taxonomy lookup`: The system is fetching names from iNaturalist.
