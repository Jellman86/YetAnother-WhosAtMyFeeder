# Configuration

Most settings in YA-WAMF can be managed directly through the web UI. These settings are stored in `/config/config.json`.

## Connection Settings
Settings for communicating with your NVR and messaging broker.

| Setting | Description |
|---------|-------------|
| **Server URL** | The URL of your Frigate instance. Used to fetch snapshots and video clips. |
| **MQTT Broker** | The hostname of your MQTT broker. |
| **Port** | MQTT port (default 1883). |
| **Authentication** | Toggle if your broker requires a username and password. |
| **Active Cameras** | Select which Frigate cameras YA-WAMF should monitor for bird events. |

## Detection Settings
Fine-tune how AI identifications are handled.

| Setting | Description |
|---------|-------------|
| **Confidence Threshold** | The minimum score (0-1) required to label a specific species. Detections below this but above the floor are labeled "Unknown Bird". |
| **Min Confidence Floor** | Absolute floor. Anything below this is ignored completely as a false positive. **Note:** Trusted Frigate sublabels bypass this check. |
| **Trust Frigate Sublabels** | If Frigate has already identified a species (via its own sublabel feature), YA-WAMF will skip its local AI and use that label instead. |
| **Blocked Labels** | A list of species or objects to ignore entirely (e.g., "background"). |

## Integration Settings
Configure third-party services.

- **BirdNET-Go:** Configure the MQTT topic and map Frigate cameras to audio sensor IDs.
- **BirdWeather:** Enter your Station Token to contribute detections to the BirdWeather community.
- **AI Insights:** Connect Google Gemini or OpenAI to get behavioral analysis of your visitors.

## Data Management
- **Retention Policy:** Choose how long to keep sightings in your history.
- **Media Cache:** Toggle local caching of snapshots and video clips to reduce load on Frigate and speed up the UI.
- **Taxonomy Repair:** Manually trigger a sync to normalize all species names using iNaturalist data.
