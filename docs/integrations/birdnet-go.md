# BirdNET-Go Integration

YA-WAMF features deep integration with [BirdNET-Go](https://github.com/tphakala/birdnet-go) for audio-visual correlation. This allows the system to cross-reference what it sees with what it hears.

## How it works
1. **BirdNET-Go** identifies a bird song and publishes the detection to MQTT.
2. **YA-WAMF** stores these audio detections in its recent in-memory correlation buffer and persists them to the audio detection history.
3. When **Frigate** detects a bird visually, YA-WAMF checks its buffer inside the configured
   audio-correlation window (five minutes by default).
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

For cameras with microphones, BirdNET-Go supports multiple named RTSP audio sources. Enable audio
in each camera (AAC is the most interoperable choice), add and test each RTSP stream in BirdNET-Go,
and give it a stable name that matches the corresponding Frigate camera where practical. Map that
configured source name in YA-WAMF; current BirdNET-Go releases publish a stable `sourceName` as well
as the runtime `sourceId`. This is easier to maintain than copying a generated hash and lets every
camera contribute independent audio context. See BirdNET-Go's
[RTSP/multiple-source guide](https://github.com/tphakala/birdnet-go/wiki/BirdNET%E2%80%90Go-Guide#live-audio-streaming).

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

### Filtering low-confidence detections
By default YA-WAMF stores every BirdNET-Go detection it receives. To drop noisy low-confidence detections at ingest, set **Minimum audio confidence** (`frigate.audio_min_confidence`, `0.0`–`1.0`). Detections below the threshold are neither buffered for correlation nor written to history. The default `0.0` stores everything. BirdNET-Go also has its own confidence and dynamic-threshold controls upstream; this setting is an additional YA-WAMF-side floor.

## Audio history and visual matches

The dashboard includes a "Recent Audio" widget that shows the live in-memory detections from
BirdNET-Go, even if no visual event occurred. The dashboard and leaderboard both link to the full
Audio History view, which reads persisted BirdNET detections and provides date-window, species,
source, and confidence filters plus top-species, source, and hourly activity summaries. This audio
history stays separate from the visual feeder leaderboard so "heard" detections do not inflate
"seen" detections.

An audio-history row shows a visual-match icon only when YA-WAMF finds a completed, non-hidden,
automatic video classification with the same scientific name, inside the configured correlation
window, and on the camera associated with that BirdNET source. Manual tags are deliberately
excluded: the icon means the independent video classifier agreed with the audio evidence. The icon
opens that exact visual detection; guest users receive links only inside their configured public
event-history window.

Detection details also look up persisted BirdNET history when you open them. This catches audio
that reached YA-WAMF after the visual event's initial correlation attempt. A matching species is
still labelled as confirmed only when the correlation rules agree; other sounds inside the same
configured time and source window appear as nearby audio context instead.

YA-WAMF normalizes incoming BirdNET timestamps to UTC before storing them. This keeps correlation,
history filters, retention, and leaderboard windows correct when BirdNET-Go publishes local-offset
timestamps (including daylight-saving changes) while Frigate events are stored as UTC. Existing
audio history is normalized automatically during the database upgrade.
