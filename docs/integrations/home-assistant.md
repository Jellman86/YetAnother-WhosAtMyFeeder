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

### Sidebar Proxy
The integration can expose YA-WAMF through the Home Assistant sidebar. Enable
**Show YA-WAMF in the Home Assistant sidebar** in the integration options. Home
Assistant authenticates the browser session, then the custom component proxies
requests to the configured YA-WAMF URL using the credentials stored in the
integration. The sidebar uses those stored credentials, so access to it can carry
their YA-WAMF owner permissions; it is not automatically reduced to guest access.
Only enable it for a Home Assistant audience you trust with those permissions.

The same YA-WAMF frontend bundle works for both standalone access and the Home
Assistant sidebar. The app detects the Home Assistant ingress path at runtime,
and the integration rewrites root asset links while proxying the page.

Changing the URL or credentials in the integration options takes effect in the
sidebar straight away; no Home Assistant restart is needed. If YA-WAMF starts
rejecting the stored credentials, Home Assistant shows a **Reconfigure** prompt
on the integration asking for new ones.

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
| **Bird Count (24h)** | How many detections there were in the last 24 hours. It is a rolling window, not a count since midnight, so it can go down as old visits age out. |
| **Latest Snapshot** | (Optional) A camera entity showing the last detected bird. |

## Weather and light from your own sensors

This direction is separate from the custom component above: here YA-WAMF reads from Home
Assistant. Open **Settings → Integrations → Home Assistant weather**, switch it on, and enter
the URL YA-WAMF can reach and a long-lived access token (Home Assistant profile, **Security**,
**Long-lived access tokens**).

| Field | What it does |
|-------|--------------|
| **Weather entity** | The general weather source, such as `weather.home`. |
| **Per-reading sensor overrides** | One sensor each for temperature, wind speed, wind direction, cloud cover, precipitation, rain and snowfall. An override outranks the weather entity for its one reading. |
| **Illuminance entity** | Optional. A light sensor, such as `sensor.feeder_illuminance`, whose reading in lux is stored with each new detection. |

Once a weather entity or an override is named, those sensors replace the forecast for live
weather, and a sensor that cannot answer leaves its reading unknown.

### Illuminance entity

A lux sensor near the feeder records the light a bird was actually seen in, which the time of
day and the cloud cover can only suggest.

- **What is accepted.** A sensor whose state is a number and whose unit is `lx`, or whose
  device class is `illuminance` with no other unit. The value must be between 0 and
  200,000 lx. Nothing is converted, so a sensor reporting in another unit is rejected.
- **What is stored.** The reading goes into the detection's `illuminance_lux` field when the
  detection is first saved. It is never changed afterwards: not by a later frame of the same
  visit, not by changing or removing the entity, and not by a weather backfill. Detections
  from before you named the sensor keep no light level.
- **When there is no reading.** `unknown`, `unavailable`, a value that is not a number, a value
  out of range, an entity that is not an illuminance sensor, or Home Assistant not answering
  all store no light level. YA-WAMF never estimates one from the forecast, the sun or the
  cloud cover. A detection that reaches YA-WAMF more than five minutes after it happened
  (a replayed backlog, for example) also stores none, because the reading would describe the
  wrong moment.
- **Weather is unaffected.** With only an illuminance entity named, and no weather entity or
  override, weather still comes from the forecast provider.
- **Freshness.** Readings are shared for up to 30 seconds, as weather readings are, so two
  detections in the same half minute can carry the same value.

**Fetch a live reading** tests the fields as typed, before you save. The light level has its
own line in the result: either the measured value in lux, or the reason there is none.

The stored value appears in a detection's **Conditions** row ("Light 1,240 lx"), in the API as
`illuminance_lux` on every detection (`null` when none was measured), and in the
[eBird export](ebird.md#exporting-to-ebird)'s species comment. There are no charts or filters
by light level yet.

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
