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

The template runs the container as `nobody:users` (uid `99` / gid `100`) via
`--user 99:100`, which matches Unraid's default appdata ownership — so `/config`
and `/data` are writable without any `chown`. If you point appdata at a share with
different ownership, either set it to `99:100` or run the Unraid **Docker Safe New
Permissions** tool. (The image does not honour `PUID`/`PGID` environment variables,
so the run-as user is set with `--user` instead.)

## Expected result

Unraid pulls `ghcr.io/jellman86/yawamf-monalithic:latest` and starts the
full compatibility container. When its health check passes, click the container's **WebUI** icon (or
browse to `http://<your-unraid-ip>:9852/`) and you should see the dashboard.
Authentication is disabled by default for first-time setup — set a password under
**Settings → Security** before exposing it beyond your trusted network.

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
paths. Pinned releases use the same suffix, such as `v3.0.0-intel`.

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
**Settings → Detection → Inference Provider**. GPU/NPU access can also require the
container user to be in the host `render` group — see
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
   **Advanced view**, add `--runtime=nvidia` to **Extra Parameters**, and add:
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
