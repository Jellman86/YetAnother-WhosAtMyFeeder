# MQTT Broker Setup

YA-WAMF receives bird detection events from Frigate over MQTT. Both applications need to be connected to the same broker. This guide walks through running [Eclipse Mosquitto](https://mosquitto.org/) in Docker alongside Frigate and YA-WAMF.

> If you already have a working Mosquitto instance, skip to [Connecting YA-WAMF](#connecting-ya-wamf).

---

## 1. Add Mosquitto to Your Stack

Add the following service to your `docker-compose.monolith.yml` (or your existing compose file):

```yaml
services:
  mosquitto:
    image: eclipse-mosquitto:latest
    container_name: mosquitto
    restart: unless-stopped
    networks:
      - bird_network          # must match Frigate and YA-WAMF
    ports:
      - "1883:1883"           # MQTT
    volumes:
      - ./mosquitto/config:/mosquitto/config
      - ./mosquitto/data:/mosquitto/data
      - ./mosquitto/log:/mosquitto/log
    environment:
      - TZ=Europe/London      # match your other containers
```

For service names such as `mosquitto` to resolve, put the containers on the same
user-defined Docker network. Check Frigate's network with `docker network ls` and set
`DOCKER_NETWORK` in `.env` to match. Different hosts/networks can also use reachable
LAN addresses and permitted MQTT ports; sharing one Docker network is not required
when you use those addresses. Do not expose an anonymous broker to the internet.

When merging the service above into the supplied Compose file, declare its shared
network too:

```yaml
networks:
  bird_network:
    external: true
    name: ${DOCKER_NETWORK:-yawamf_default}
```

The external network must already exist. If only containers use this broker,
you can omit the host `ports:` mapping.

---

## 2. Create the Configuration File

Create the config directory and a minimal `mosquitto.conf`:

```bash
mkdir -p mosquitto/config mosquitto/data mosquitto/log
```

### Option A — No Authentication (simplest, trusted LAN only)

`mosquitto/config/mosquitto.conf`:

```
listener 1883
allow_anonymous true
persistence true
persistence_location /mosquitto/data/
log_dest file /mosquitto/log/mosquitto.log
```

### Option B — Username/Password Authentication (recommended)

`mosquitto/config/mosquitto.conf`:

```
listener 1883
allow_anonymous false
password_file /mosquitto/config/passwd
persistence true
persistence_location /mosquitto/data/
log_dest file /mosquitto/log/mosquitto.log
```

Then create the password file. Run this from your stack directory — it starts a temporary Mosquitto container to generate the file safely:

```bash
docker run --rm -it \
  -v "$(pwd)/mosquitto/config:/mosquitto/config" \
  eclipse-mosquitto:latest \
  mosquitto_passwd -c /mosquitto/config/passwd YOUR_USERNAME
```

You will be prompted to enter and confirm a password. Replace `YOUR_USERNAME` with a name of your choice (e.g. `frigate`).

> To add a second user later, omit the `-c` flag (which would overwrite the file):
> `mosquitto_passwd /mosquitto/config/passwd ANOTHER_USER`

---

## 3. Configure Frigate

In your `frigate/config/config.yml`, add the MQTT section:

```yaml
mqtt:
  enabled: true
  host: mosquitto        # service name in your compose file
  port: 1883
  topic_prefix: frigate  # YA-WAMF listens on frigate/events
  # Only needed for Option B (authenticated):
  user: YOUR_USERNAME
  password: YOUR_PASSWORD
```

> To use Frigate's environment substitution, explicitly set
> `password: "{FRIGATE_MQTT_PASSWORD}"` in its configuration and pass that environment
> variable to the Frigate container. Merely defining it does not replace a literal password.

---

## 4. Connecting YA-WAMF

Set these variables in your `.env`:

```env
MQTT_SERVER=mosquitto
MQTT_PORT=1883

# Only needed for Option B (authenticated):
MQTT_AUTH=true
MQTT_USERNAME=YOUR_USERNAME
MQTT_PASSWORD=YOUR_PASSWORD
```

Or pass them directly as environment variables in your compose file:

```yaml
environment:
  - FRIGATE__MQTT_SERVER=mosquitto
  - FRIGATE__MQTT_PORT=1883
  # Only for authenticated brokers:
  - FRIGATE__MQTT_AUTH=true
  - FRIGATE__MQTT_USERNAME=YOUR_USERNAME
  - FRIGATE__MQTT_PASSWORD=YOUR_PASSWORD
```

---

## 5. Start and Verify

Start (or restart) your stack:

```bash
docker compose -f docker-compose.monolith.yml up -d
```

Then check the YA-WAMF logs to confirm it connected:

```bash
docker compose -f docker-compose.monolith.yml logs yawamf | grep -i mqtt
```

You should see something like:

```
Connected to MQTT topic=frigate/events
```

To also confirm Mosquitto is healthy:

```bash
docker compose -f docker-compose.monolith.yml logs mosquitto | tail -20
```

You should see `Opening ipv4 listen socket on port 1883` and no error lines.

### Quick connection test from the UI

In **Settings → Connection**, select **Test Connection**. The staged dialog checks
**Frigate API**, then **MQTT broker publish**, using the values currently visible in
the form. A passed MQTT stage proves the isolated client connected and published;
it does not prove Frigate is publishing real bird events or that a camera is selected.
Save changes with **Apply settings**, then verify a real event arrives.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `Connection refused` in YA-WAMF logs | Wrong hostname or port | Confirm `MQTT_SERVER` matches the Mosquitto container name and that both are on the same Docker network |
| `Not authorised` in logs | Auth mismatch | Check `MQTT_USERNAME`/`MQTT_PASSWORD` in `.env` match the credentials in the passwd file; confirm `MQTT_AUTH=true` is set |
| YA-WAMF connects but receives no events | Frigate not publishing | Check `docker logs frigate` for MQTT errors; confirm `topic_prefix: frigate` in Frigate's config |
| `Connection refused` from Frigate | Frigate on a different network | Use a shared user-defined network for service names, or a reachable LAN broker address and port |
| Password file errors at Mosquitto startup | Wrong ownership or permissions | Run `sudo chown 1883:1883 mosquitto/config/passwd && sudo chmod 0600 mosquitto/config/passwd` — 1883 is the mosquitto UID inside the container |

### Checking which network containers are on

```bash
docker inspect mosquitto | grep -A5 Networks
docker inspect frigate   | grep -A5 Networks
docker inspect yawamf-monalithic | grep -A5 Networks
```

All three should show the same network name.
