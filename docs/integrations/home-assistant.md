# Home Assistant Integration

YA-WAMF provides a custom component for Home Assistant to integrate your bird sightings into your smart home dashboard.

## Installation

### 1. Copy Files
Copy the `custom_components/yawamf` folder from the YA-WAMF repository to your Home Assistant `config/custom_components/` directory.

### 2. Restart
Restart Home Assistant to load the new component.

### Icon Cache Note
Home Assistant may cache integration icons. If the icon does not update after an upgrade, hard-refresh the HA frontend or clear the browser cache.

### 3. Add Integration
Go to **Settings > Devices & Services > Add Integration** and search for "YA-WAMF".

### 4. Configure
Enter the URL of your YA-WAMF instance (e.g., `http://192.168.1.50:9852` or `https://yoursite.example.com`).

### Authentication Notes
If YA-WAMF authentication is enabled and **Public Access** is disabled, Home Assistant must authenticate to the YA-WAMF API.

Supported options in the integration config:
- Username + password (recommended): the integration logs in and uses a short-lived JWT automatically.
- Legacy API key (deprecated): only if you still use the old `X-API-Key` auth mode. YA-WAMF plans to remove API keys.

### Updating the URL
If you change your server address (for example, moving from direct IP to a reverse proxy URL), use:
**Settings → Devices & Services → YA-WAMF → Configure** and update the URL.

### Reverse Proxy Notes
- Use the **public hostname** you configured on the proxy (not the internal container IP).
- Ensure the proxy forwards the `/health` and `/api/stats/daily-summary` endpoints.
- If your proxy enforces HTTPS, use the `https://` URL in Home Assistant.

## Sensors Provided

| Sensor | Description |
|--------|-------------|
| **Last Bird Detected** | The name of the most recent visitor. This sensor now only emits a Home Assistant state update when a new detection event arrives, so repeated visits from the same species can still drive automations reliably. Attributes include camera, confidence, temperature, and weather. |
| **Last Detection Event** | The raw YA-WAMF/Frigate event ID for the most recent detection. Use this as the safest trigger when you want an automation to fire for every new detection, regardless of species. |
| **Last Detection Time** | A proper Home Assistant timestamp entity for the most recent detection time. |
| **Daily Count** | A counter for how many birds have visited since midnight. |
| **Latest Snapshot** | (Optional) A camera entity showing the last detected bird. |

## Automation Example
For automations that should fire on every new detection, prefer the event sensor:

```yaml
alias: "Notify on Every New Bird Detection"
trigger:
  - platform: state
    entity_id: sensor.yawamf_last_detection_event
action:
  - service: notify.mobile_app
    data:
      message: >
        New bird detected:
        {{ state_attr('sensor.yawamf_last_detection_event', 'species') }}
```

If you only care about a specific species, you can still filter on the species name:

```yaml
alias: "Notify on Cardinal"
trigger:
  - platform: state
    entity_id: sensor.yawamf_last_detection_event
condition:
  - condition: template
    value_template: >
      {{ state_attr('sensor.yawamf_last_detection_event', 'species') == 'Northern Cardinal' }}
action:
  - service: notify.mobile_app
    data:
      message: "A Cardinal is at the feeder!"
```
