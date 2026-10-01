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

### Community Applications

In **Apps**, search for **YA-WAMF**, confirm that the repository is
`ghcr.io/jellman86/yawamf-monalithic`, and select **Install**. The listing provides
the template, app icon and project/support links.

### Manual template import

If the listing is unavailable, save the published template locally. The
**Docker → Add Container → Template** control selects local templates; it does
not accept a remote URL. From the Unraid terminal:

```sh
install -d /boot/config/plugins/dockerMan/templates-user
template=/boot/config/plugins/dockerMan/templates-user/my-YA-WAMF.xml
test ! -e "$template" &&
  curl -fL --output /tmp/yawamf-template.xml \
    https://raw.githubusercontent.com/Jellman86/YetAnother-WhosAtMyFeeder/main/unraid/yawamf.xml &&
  install -m 0644 /tmp/yawamf-template.xml "$template"
```

Use this command for a new installation. For an existing installation, keep its
saved template and edit that container so your paths, ports and device settings
are retained.

1. Go to **Docker → Add Container**.
2. In **Template**, select **YA-WAMF** under **User templates**.
3. Review these fields:
   - **WebUI Port**: host port for the UI (default `9852`; the container listens on `8080`).
   - **Config**: `/config` mapped to `/mnt/user/appdata/ya-wamf/config`.
   - **Data**: `/data` mapped to `/mnt/user/appdata/ya-wamf/data` (SQLite history, models and cached media). Keep it on fast storage.
4. Click **Apply**.

The template runs as uid `99` / gid `100` (`nobody:users`) via `--user 99:100`.
Unraid creates missing mapped directories with this ownership. Existing
directories must already permit this user to write; importing a template does
not repair their permissions. If needed, stop YA-WAMF and correct ownership on
only its **Config** and **Data** directories. The image does not honour
`PUID`/`PGID` variables.

## Expected result

Unraid pulls `ghcr.io/jellman86/yawamf-monalithic:latest` and starts the full
compatibility container. First startup can take several minutes while the
database and species catalogue are prepared. Open **WebUI** or
`http://<your-unraid-ip>:9852/`, then complete the first-run wizard.

In **Frigate & MQTT connection**, enter the Frigate API URL and MQTT broker
address, port and credentials, then test both connections. Use LAN addresses,
for example `http://192.168.1.10:5000`, or hostnames reachable from the container.
The default Docker **bridge** network does not resolve container names such as
`frigate` or `mqtt`; those names require a shared user-defined network. For a
Frigate API that requires authentication, provide its URL and token together
(see [Frigate](../integrations/frigate.md)). Later changes belong in
**Settings → Connection**.

The current template leaves connection settings in the app. Older installs
may still have `FRIGATE__FRIGATE_URL` in their saved Unraid template; it overrides
the saved Frigate URL on restart. To move an existing install to in-app settings,
first note that URL, remove the variable from the container's edit form, apply
the change, and save the URL in **Settings → Connection**. Keep intentional
environment overrides if you manage configuration externally.

Authentication is disabled initially. Set an admin password during setup or
under **Settings → Security** before exposing the service beyond a trusted
network. See [Authentication & Access](../features/authentication.md).

## Optional: hardware acceleration

The template deliberately starts with the full compatibility image and does not
pin an inference provider. Four separate controls are involved:

| Control | Where to set it in Unraid | What it means |
|---|---|---|
| Image family | **Repository** tag | Which inference runtimes are installed |
| Device/runtime access | Advanced container settings | Which host accelerator the container can see |
| Selected provider | **Settings → Detection** inside YA-WAMF | The user's preferred provider, normally `Auto` |
| Active provider | YA-WAMF runtime diagnostics | What actually ran after model, packaging, and hardware checks |

The available stable Repository tags are:

| Repository tag | Packaged providers | Intended host |
|---|---|---|
| `latest` | CPU, CUDA, Intel CPU/GPU/NPU | Compatibility and initial setup |
| `latest-cpu` | CPU | Hosts without an accelerator |
| `latest-intel` | CPU and Intel OpenVINO | Intel GPU or NPU hosts |
| `latest-cuda` | CPU and NVIDIA CUDA | NVIDIA hosts |

Start with `latest`. Once the installation is healthy, edit only the tag portion
of **Repository** if you want a smaller image; keep the same `/config` and `/data`
paths. Pinned releases use the same suffix, such as `v2.21.1-intel`.

Do not add `YAWAMF_IMAGE_FLAVOR` to the template. It is read-only identity baked
into each image, and overriding it does not install a runtime. Also avoid adding
`CLASSIFICATION__INFERENCE_PROVIDER` for an ordinary interactive installation:
that environment variable overrides the in-app value on every container start,
so a provider changed in Settings would appear to save but revert after a
restart. Use it only when you intentionally manage immutable settings outside
the application.

See [Hardware Acceleration](hardware-acceleration.md) for the complete provider
contract, diagnostics, and rollback path.

### Intel GPU or NPU

To run inference on an Intel GPU or NPU, add the device yourself (the template
does not add one, so it never passes an empty `--device` to Docker). In the
container's edit view, switch to **Advanced view**, click **Add another Path,
Port, Variable, Label or Device**, and add:

- Config Type **Device**, Value `/dev/dri` — Intel integrated GPU (`intel_gpu`), or
- Config Type **Device**, Value `/dev/accel/accel0` — Intel Core Ultra "AI Boost" NPU (`intel_npu`).

Add only the device you actually have. Then pick the provider under
**Settings → Detection → Inference Provider**. GPU/NPU access can also require
supplementary host groups. Look up the numeric group owning the render or
accelerator device, then append `--group-add <gid>`
to **Extra Parameters**, preserving `--user 99:100`. See
[Hardware Acceleration](hardware-acceleration.md) for the full detail and fallback
behaviour.

### NVIDIA CUDA

1. Install Unraid's
   [**NVIDIA Driver** plugin](https://forums.unraid.net/topic/98978-plugin-nvidia-driver/)
   and confirm `nvidia-smi` works in an Unraid terminal. Keep the GPU available
   to the host rather than binding it exclusively to VFIO.
2. Keep the full `latest` Repository tag for compatibility testing, or change it
   to `latest-cuda` for the smaller CUDA image.
3. Follow the NVIDIA Driver plugin's current container-runtime instructions for
   your Unraid release. The established Docker-runtime path is to enable
   **Advanced view**, append `--runtime=nvidia` to **Extra Parameters**, keeping
   the existing `--user 99:100`, and add:
   - `NVIDIA_VISIBLE_DEVICES` with the GPU UUID shown by the plugin (or `all` when
     deliberately exposing every GPU), and
   - `NVIDIA_DRIVER_CAPABILITIES=compute,utility`.
   Newer Unraid/NVIDIA toolkit releases may offer CDI device selection instead;
   use one exposure method, not both.
4. Start the container, leave the in-app provider on **Auto** initially, and
   check **Settings → Detection → Runtime diagnostics**. It must show a `full` or
   `cuda` image, CUDA under **Packaged**, the GPU as available, and CUDA as
   **Active** during supported-model inference.

The NVIDIA runtime variables expose hardware; they do not select YA-WAMF's
inference provider. If CUDA cannot initialize or the active model does not
support it, YA-WAMF retains the provider preference and falls back to CPU with a
diagnostic reason.

## If it fails

- **Blank page or connection refused:** the container may still be starting or
  applying model changes — wait a moment and retry. Check the container log in
  Unraid.
- **No detections:** confirm the **Frigate URL** is reachable from the container
  and that Frigate is publishing to MQTT. See
  [Diagnostics](../troubleshooting/diagnostics.md).

For all settings once you are in, see the [Configuration Guide](configuration.md).
