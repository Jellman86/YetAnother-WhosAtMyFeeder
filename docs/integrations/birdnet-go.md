# BirdNET-Go Integration

YA-WAMF features deep integration with [BirdNET-Go](https://github.com/tbeceele/birdnet-go) for audio-visual correlation. This allows the system to cross-reference what it sees with what it hears.

## How it works
1. **BirdNET-Go** identifies a bird song and publishes the detection to MQTT.
2. **YA-WAMF** stores these audio detections in a short-term memory buffer (5 minutes).
3. When **Frigate** detects a bird visually, YA-WAMF checks its buffer for a matching timestamp (±30s).
4. If a match is found, the detection is marked as **"Verified"** in the UI with an audio badge.

## Setup

### 1. MQTT Topic
In **Settings > Integrations**, ensure the MQTT topic matches your BirdNET-Go configuration. 
- **Modern BirdNET-Go:** Use the base topic (e.g., `birdnet`). 
- **Legacy / Custom:** Use the specific text topic (e.g., `birdnet/text`).

> ℹ️ **Note:** YA-WAMF will automatically reconnect to your MQTT broker if you change the topic in the UI.

### 2. Sensor Mapping
For correlation to work, YA-WAMF needs to know which audio sensor belongs to which camera.
1. Observe the **Recent Audio** widget on the dashboard.
2. Note the **Sensor ID** displayed in the top-right of the audio entries (e.g., `rtsp_42182153`).
3. Go to **Settings > Integrations > Sensor Mapping**.
4. Type that ID next to the corresponding Frigate camera name.

### 3. Dynamic Sensor IDs (Wildcard)
If your audio source (like a re-streaming camera) generates a new Sensor ID every time it restarts, you can use a **wildcard** to match *any* audio detection to a specific camera.

- In the **Sensor Mapping** field, simply enter: `*`
- This tells YA-WAMF: "Any audio detection that happens at the same time as this camera's visual detection is a match, regardless of the sensor name."

> ⚠️ **Important:** For correlation to work, your **Timezone (TZ)** must be synced across all containers. See the [Getting Started](../setup/getting-started.md#🌍-the-importance-of-timezone-tz) guide for more details.

## 🛠 Technical Details

YA-WAMF is compatible with multiple BirdNET message formats:
- **CamelCase (Original):** `comName`, `score`, `ts`
- **PascalCase (New BirdNET-Go):** `CommonName`, `Confidence`, `Source -> id`

The system ignores "Sound Level" messages (`birdnet/soundlevel`) and focuses only on valid species identifications.

## Dashboard Widget
The dashboard includes a "Recent Audio" widget that shows the most recent standalone detections from BirdNET-Go, even if no visual event occurred. This can be toggled on/off in the settings.
