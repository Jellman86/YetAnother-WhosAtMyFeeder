# Unraid

Install YA-WAMF on Unraid from a Docker template, so the container, ports, and
paths are filled in for you and the web UI is one click away.

## Outcome

YA-WAMF runs as a single Unraid Docker container, its config and data on
persistent appdata paths, reachable at `http://<your-unraid-ip>:9852/`.

## Prerequisites

- A reachable **Frigate** instance publishing events over **MQTT** — YA-WAMF is
  driven by Frigate events and does nothing useful without them. See
  [Frigate](../integrations/frigate.md) and [MQTT Broker](mqtt-broker.md).
- Somewhere to store appdata (the default is `/mnt/user/appdata/ya-wamf`).

YA-WAMF's UI and API are administrative surfaces. If you expose them outside your
LAN, put them behind an authenticated reverse proxy — see
[Reverse Proxy](reverse-proxy.md) and [Authentication & Access](../features/authentication.md).

## Install with the template

1. In the Unraid web UI, go to **Docker → Add Container**.
2. In **Template**, paste the template URL:

   ```
   https://raw.githubusercontent.com/Jellman86/YetAnother-WhosAtMyFeeder/main/unraid/yawamf.xml
   ```

3. The fields populate from the template. Review these:
   - **WebUI Port** — host port for the UI (default `9852`; the container listens on `8080`).
   - **Config** — `/config` → `/mnt/user/appdata/ya-wamf/config`.
   - **Data** — `/data` → `/mnt/user/appdata/ya-wamf/data` (SQLite detections database and cached media; this grows with your retention window, so keep it on fast storage).
   - **Frigate URL** — set this to your Frigate instance, e.g. `http://192.168.1.10:5000`.
4. Click **Apply**.

## Expected result

Unraid pulls `ghcr.io/jellman86/yawamf-monalithic:latest` and starts the
container. When its health check passes, click the container's **WebUI** icon (or
browse to `http://<your-unraid-ip>:9852/`) and you should see the dashboard.
Authentication is disabled by default for first-time setup — set a password under
**Settings → Security** before exposing it beyond your trusted network.

## Optional: hardware acceleration

To run inference on an Intel GPU or NPU, add the device yourself (the template
does not add one, so it never passes an empty `--device` to Docker). In the
container's edit view, switch to **Advanced view**, click **Add another Path,
Port, Variable, Label or Device**, and add:

- Config Type **Device**, Value `/dev/dri` — Intel integrated GPU (`intel_gpu`), or
- Config Type **Device**, Value `/dev/accel/accel0` — Intel Core Ultra "AI Boost" NPU (`intel_npu`).

Add only the device you actually have. Then pick the provider under
**Settings → Detection → Inference Provider**. GPU/NPU access can also require the
container user to be in the host `render` group — see
[Hardware Acceleration](hardware-acceleration.md) for the full detail and fallback
behaviour.

## If it fails

- **Blank page or connection refused:** the container may still be starting or
  applying model changes — wait a moment and retry. Check the container log in
  Unraid.
- **No detections:** confirm the **Frigate URL** is reachable from the container
  and that Frigate is publishing to MQTT. See
  [Diagnostics](../troubleshooting/diagnostics.md).

For all settings once you are in, see the [Configuration Guide](configuration.md).
