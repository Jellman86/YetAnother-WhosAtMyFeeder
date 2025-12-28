# Implementation Plan: Home Assistant Integration for YA-WAMF

## 1. Overview
The goal is to create a **Home Assistant Custom Integration** that allows users to monitor their bird feeder directly within Home Assistant. This enables automations (e.g., sending a mobile notification with an image when a rare bird is seen) and rich dashboard displays.

## 2. Integration Strategy
- **Type**: Custom Component (`custom_components/yawamf/`).
- **Communication**: 
  - **Polling**: Via a `DataUpdateCoordinator` calling the YA-WAMF REST API (`/api/events`).
  - **Real-time**: Listen to the same MQTT topic as YA-WAMF (`frigate/events`) for immediate detection triggers.
- **Authentication**: Support for optional API tokens (if implemented in the future) or simple unauthenticated local access.

## 3. Proposed Entities

### Sensors
- **Last Detection**: A sensor containing the species name of the most recent visitor.
  - *Attributes*: confidence score, camera name, frigate event ID, timestamp.
- **Daily Count**: Total number of birds seen today.
- **Species Counter**: Individual sensors for common species (e.g., `sensor.yawamf_blue_tit_count`).

### Camera / Image
- **Last Bird Snapshot**: A `camera` entity that always shows the image of the most recent detection.
- **Live Stream**: Optional proxying of the Frigate stream via YA-WAMF logic.

### Media Source
- Integrate with the **Home Assistant Media Browser** to allow users to browse and play cached video clips from the YA-WAMF backend directly on HA-compatible media players.

## 4. Technical Architecture

### File Structure
```
custom_components/yawamf/
├── __init__.py          # Integration setup
├── manifest.json        # Metadata & requirements (e.g., httpx)
├── const.py             # Constants (DOMAIN, URLs)
├── config_flow.py       # UI for adding the integration (URL, MQTT settings)
├── coordinator.py       # Centralized data fetching logic
├── sensor.py            # Species & count sensors
├── camera.py            # Snapshot display
└── media_source.py      # Video clip browsing
```

### Data Flow
1. **Config Flow**: User enters the YA-WAMF Backend URL (e.g., `http://192.168.1.50:8946`).
2. **Setup**: Integration initializes an internal API client.
3. **Coordinator**: Every 30 seconds (configurable), fetches `GET /api/events?limit=1`.
4. **Updates**: When a new event ID is detected:
   - Update `sensor.last_bird`.
   - Fire a `yawamf_bird_detected` event in Home Assistant (useful for user automations).
   - Update the `camera` entity snapshot URL.

## 5. Automation Examples
Users will be able to create powerful automations like:
```yaml
alias: "Notify on Rare Bird"
trigger:
  - platform: state
    entity_id: sensor.yawamf_last_bird
condition:
  - condition: template
    value_template: "{{ state_attr('sensor.yawamf_last_bird', 'score') > 0.9 }}"
action:
  - service: notify.mobile_app_iphone
    data:
      title: "New Visitor!"
      message: "A {{ states('sensor.yawamf_last_bird') }} is at the feeder!"
      data:
        image: "http://YAWAMF_IP:8946/api/frigate/{{ state_attr('sensor.yawamf_last_bird', 'event_id') }}/snapshot.jpg"
```

## 6. Implementation Phases

### Phase 1: MVP (REST + Sensors)
- Implement `config_flow` and `coordinator`.
- Create the "Last Bird" sensor with metadata attributes.
- Support basic configuration via the UI.

### Phase 2: Visuals (Camera)
- Implement the `camera` platform to show the latest snapshot.
- Add support for displaying the Frigate score and sub-label in attributes.

### Phase 3: Media Browser (Clips)
- Implement `media_source.py`.
- Expose the `/clips/` directory from YA-WAMF to the HA Media Browser.

### Phase 4: Polish & HACS
- Add unique icons for different bird categories.
- Prepare the repository for easy installation via **HACS** (Home Assistant Community Store).
