# Yet Another WhosAtMyFeeder (YA-WAMF)

A bird classification system that works with [Frigate NVR](https://frigate.video/) to identify the birds visiting your feeder.

![YA-WAMF Dashboard](dashboard-preview.png)

## About This Project

This is a personal project I started to experiment with AI-assisted coding. I noticed the original [WhosAtMyFeeder](https://github.com/mmcc-xx/WhosAtMyFeeder) wasn't being maintained anymore and thought it would be a fun way to learn while building something useful.

The whole thing has been built with help from AI coding assistants - it's been an interesting way to see what's possible with these tools. If you spot any rough edges, that's probably why!

## What It Does

When Frigate detects a bird at your feeder, YA-WAMF:
1. Grabs the snapshot image
2. Runs it through an advanced AI model (MobileNetV2, ConvNeXt, or EVA-02)
3. Shows you what species it thinks it is
4. Keeps track of all your visitors in a nice dashboard
5. Proxies video clips from Frigate with full streaming and seeking support

**Advanced Features:**
- **Elite Accuracy:** Support for state-of-the-art **EVA-02 Large** models (~91% accuracy).
- **Fast Path Efficiency:** Skip local AI and use Frigate's sublabels directly to save CPU.
- **Deep Video Analysis:** Scan entire video clips frame-by-frame for the perfect identification.
- **Wildlife Classifier:** Identify squirrels, foxes, and other non-bird visitors.

## How It Works

Here's the flow from bird to identification:

```
┌─────────────┐     MQTT Event      ┌─────────────┐
│   Frigate   │ ─────────────────>  │  YA-WAMF    │
│   (NVR)     │   "bird detected"   │  Backend    │
└─────────────┘                     └──────┬──────┘
                                           │
                                           v
                                    ┌──────────────┐
                                    │ Fast Path:   │
                                    │ Use Frigate  │
                                    │ Sublabels?   │
                                    └──────┬───────┘
                                           │
                                     (No)  v  (Yes)
                                    ┌──────────────┐
                                    │  AI Engine   │
                                    │ (TFLite/ONNX)│
                                    └──────┬───────┘
                                           │
                                           v
                                    ┌──────────────┐
                                    │ Save to DB & │
                                    │ Update UI    │
                                    └──────────────┘
```

**Step by step:**

1. **Frigate spots a bird** - Your camera picks up movement, Frigate's object detection identifies it as a bird
2. **MQTT message sent** - Frigate publishes an event to `frigate/events` on your MQTT broker
3. **YA-WAMF receives the event** - The backend is subscribed to that MQTT topic and picks up the message
4. **Efficiency Check** - If "Trust Frigate Sublabels" is enabled and Frigate already has a label, we use it instantly.
5. **Classification runs** - Otherwise, the image goes through a local model (TFLite or ONNX) trained on bird species.
6. **Results stored** - If the confidence is high enough, the detection gets saved to the database.
7. **Dashboard updates** - The frontend gets a real-time update via Server-Sent Events (SSE).

## Getting Started with Docker Compose

### What You'll Need

- Docker and Docker Compose installed
- Frigate already running with MQTT enabled
- Your MQTT broker details (usually mosquitto running alongside Frigate)

### Setup Steps

**1. Create a directory and grab the compose file:**

```bash
mkdir ya-wamf && cd ya-wamf
curl -O https://raw.githubusercontent.com/Jellman86/YetAnother-WhosAtMyFeeder/main/docker-compose.yml
curl -O https://raw.githubusercontent.com/Jellman86/YetAnother-WhosAtMyFeeder/main/.env.example
```

**2. Create your environment file:**

```bash
cp .env.example .env
```

**3. Edit the .env file with your settings:**

```env
# The Docker network where Frigate and your MQTT broker live
# (check with: docker network ls)
DOCKER_NETWORK=frigate

# Your Frigate instance
FRIGATE_URL=http://frigate:5000

# Your MQTT broker (usually 'mosquitto' if running in Docker)
MQTT_SERVER=mosquitto
MQTT_PORT=1883

# If your MQTT needs authentication
MQTT_AUTH=true
MQTT_USERNAME=mqtt_user
MQTT_PASSWORD=secret_password

# Your timezone
TZ=Europe/London
```

**4. Make sure the external network exists:**

The containers need to join the same Docker network as your Frigate/MQTT setup. Check your network name:

```bash
docker network ls
```

Look for whatever network your Frigate containers are using.

**5. Create the data directories:**

```bash
mkdir -p config data/models
```

The directory structure:
- `config/` - Configuration files (config.json)
- `data/` - Persistent data
  - `data/models/` - Downloaded ML models (persists across container updates)

**6. Start it up:**

```bash
docker compose up -d
```

**7. Open the dashboard:**

Go to `http://localhost:9852` in your browser (or your server's IP address).

**8. Download the bird model:**

On first run, you'll need to download the classification model. Go to Settings in the web UI and click the download button. The model is saved to `data/models/` and will persist across container updates - you only need to download it once.

### Checking It's Working

```bash
# Check container status
docker compose ps

# Check backend logs
docker compose logs backend

# You should see something like:
# MQTT config: auth=True port=1883 server=mosquitto
# Connected to MQTT topic=frigate/events
```

### Troubleshooting

**MQTT connection errors?**
- Make sure `DOCKER_NETWORK` is set to the right network name
- Check that your MQTT server hostname is correct
- Verify MQTT credentials if authentication is enabled

**Frontend not loading?**
- Check the frontend container is healthy: `docker compose ps`
- Look at frontend logs: `docker compose logs frontend`

**No detections appearing?**
- Make sure Frigate is detecting birds and publishing to MQTT
- Check the backend logs for incoming events
- Verify the classification model was downloaded

## Configuration

Most settings can be changed through the web UI under Settings. They get saved to `config/config.json`.

| Setting | What it does | Default |
|---------|--------------|---------|
| Frigate URL | Where to fetch snapshots from | http://frigate:5000 |
| MQTT Server | Your MQTT broker hostname | mqtt |
| Classification Threshold | How confident the model needs to be (0-1) | 0.7 |
| Trust Frigate Sublabels | Skip local AI if Frigate has an identification | Enabled |
| AI Model | Choose between MobileNet (Fast), ConvNeXt (High), or EVA-02 (Elite) | MobileNet |

## Tech Stack

- **Backend:** Python 3.12, FastAPI, SQLite
- **Frontend:** Svelte 5, Tailwind CSS
- **ML Engine:** ONNX Runtime & TensorFlow Lite
- **Messaging:** MQTT for Frigate events, SSE for live UI updates

## Video Playback & Bandwidth

YA-WAMF includes a robust video proxy that streams clips directly from Frigate. This supports:
- **Instant Playback:** Starts playing immediately without waiting for the whole file.
- **Seeking:** You can jump to any part of the video (scrubbing) thanks to HTTP Range support.
- **Bandwidth Control:** If you are on a metered connection or want to reduce load, you can disable "Fetch Video Clips" in the Settings. This prevents the backend from fetching heavy video files.

## Wildlife Classification (Optional)

Sometimes non-birds show up at your feeder - squirrels, raccoons, foxes, and more. YA-WAMF includes an optional wildlife classifier to identify these visitors.

**Setup:**
1. Go to **Settings** in the web UI
2. Find the **Wildlife Classifier** section
3. Click **Download Wildlife Model** (one-time ~50MB download)

**Usage:**
- When viewing any detection, click the **Identify Animal** button
- The classifier will suggest what animal it might be
- Click a result to apply it as the species label

**Model Details:**
- Uses MobileNet V2 trained on ImageNet (1001 classes)
- Fast CPU inference (~14MB model)
- Includes common backyard animals: squirrels, foxes, rabbits, raccoons, deer, skunks, and more

## Help the Project Improve! 🧪

This project is in active development, and your feedback is incredibly valuable! If you are using YA-WAMF, please help the project by:

1.  **Testing**: Try out all the features (video playback, classification, settings, etc.) and see how it performs in your environment.
2.  **Reporting Issues**: If you find a bug, something doesn't look right, or you have a suggestion for an improvement, please **[open an issue on GitHub](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues)**.
3.  **Sharing Success**: Let us know if it's working well for you!

## Contributing

Feel free to open PRs if you have improvements to share. Just keep in mind this is a hobby project maintained in spare time.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Thanks To

- The original [WhosAtMyFeeder](https://github.com/mmcc-xx/WhosAtMyFeeder) project for the idea
- [Frigate](https://frigate.video/) for being such a great NVR
- [BirdNET-Go](https://github.com/tbeceele/birdnet-go) for the excellent audio classification integration
- **Ben Jordan** on YouTube for his inspiring [bird detection video](https://youtu.be/hCQCP-5g5bo?si=r__2KjXi6KPGM5FF)
- The AI assistants that helped build this thing
