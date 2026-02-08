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
| **Last Bird Detected** | The name of the most recent visitor. Attributes include camera, confidence, temperature, and weather. |
| **Daily Count** | A counter for how many birds have visited since midnight. |
| **Latest Snapshot** | (Optional) A camera entity showing the last detected bird. |

## Automation Example
You can use the sensors to trigger automations, like flashing a light when a Cardinal arrives:

```yaml
alias: "Notify on Cardinal"
trigger:
  - platform: state
    entity_id: sensor.yawamf_last_bird
    to: "Northern Cardinal"
action:
  - service: notify.mobile_app
    data:
      message: "A Cardinal is at the feeder!"
```
