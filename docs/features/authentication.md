# Authentication & Access Control

Enable authentication to protect your settings and history with an owner login. You can also
turn on a separate read-only public view to share your detections.

## Overview

- **Owner:** Full access to settings, management, reclassification, and AI tools.
- **Guest (Public):** Read-only access to the dashboard and events (if enabled). No access to settings or actions that incur cost (like AI analysis).
- **Disabled:** Full access for everyone (default for backward compatibility, but not recommended for exposed instances).

## Enabling Authentication

By default, authentication is **disabled** to allow easy first-time setup. To enable it:

1.  Navigate to **Settings → Security**.
2.  Set a strong password.
3.  Enable **Authentication**.
4.  (Optional) Enable **Public Access** if you want to share your dashboard.

On a fresh installation, YA-WAMF opens the guided setup automatically because
`auth.initial_setup_complete` is false and no password exists. The account step
lets you create the owner account or explicitly continue without authentication
on a trusted network. You do not need to set `AUTH__ENABLED=true` to display the
wizard. Creating the password and owner session is one first-run operation: the
`POST /api/auth/initial-setup` response contains a bearer token, which the UI stores
before it loads the now owner-protected setup state. Concurrent first-run claims are
serialized, and a failed config write restores the previous in-memory auth state.

Choosing either password-protected or trusted-network mode sets
`initial_setup_complete`. The unauthenticated endpoint then refuses every later
request, including on an auth-disabled installation, preventing it from becoming
an account-takeover path. After setup, you can reopen the non-destructive wizard from
**Settings → Setup wizard** in the Settings navigation.

## Quick Start (Recommended)

1. **Enable Authentication** and set a strong password.
2. **Enable Public Access** only if you want a read‑only guest view.
3. **Set Trusted Proxy Hosts** if you are behind a reverse proxy (see below).
4. **Save** and refresh the UI to confirm the login prompt appears.

## Password Reset

Currently, there is no email-based "Forgot Password" flow. If you lose your password, you must reset it manually via the server file system.

1. Access your server through SSH or direct access.
2. Stop YA-WAMF so it cannot overwrite the file while you edit it.
3. Back up the mapped `config/config.json` file.
4. In the `auth` object, set `password_hash` to `null` and
   `initial_setup_complete` to `false`.
5. Start YA-WAMF again.
6. Open the web UI. The setup wizard will ask you to create a new owner password.

Both fields are required. Clearing only `password_hash` on an installation that
has already completed setup does not reopen the wizard.

**Example `config.json` edit:**

```json
{
  "auth": {
    "enabled": true,
    "username": "admin",
    "password_hash": null,
    "initial_setup_complete": false
  }
}
```

## Public Access (the guest view)

Public Access lets anyone with the link browse your detections while the settings and every
management action stay behind your login.

![Settings → Security: an Authentication card with the enable switch, admin username and a saved password shown as ***REDACTED***, beside a Public Access card with separate switches for enabling public access, showing camera names, sharing audio, and sharing photographs](../images/settings-security.png)

- **Enable:** in **Settings → Security**, turn on **Enable public access**.
- Guests cannot change settings, delete, hide, or reclassify detections, or start new AI
  Naturalist analysis. They can read analysis you have already run.
- Guests are rate-limited (default **30 requests per minute**) to prevent abuse.

### What a guest can see

Each switch is enforced at the server, not merely hidden in the interface, and a guest is told a
medium is not shared rather than shown a broken image or an error.

| Control | Default | What it decides |
|---|---|---|
| **Show camera names** | On | Whether camera labels appear, or are blanked out. |
| **Share audio with visitors** | On | BirdNET-Go detections, spectrograms, and audio clips. Off means no audio surfaces at all. |
| **Share photographs with visitors** | On | Snapshots and thumbnails. Off means visitors see placeholders instead of images. |
| **Share video with visitors** | On | Clip playback. |
| **Allow clip downloads** | **Off** | Whether a guest can save a clip file, rather than only stream it. |
| **Show AI conversation threads** | **Off** | Whether guests can read the AI Naturalist conversation, not just the summary. |
| **History window** | Follow retention | How far back the public detection list reaches, capped at 365 days. In custom mode, `0` means today only. |
| **Media window** | Follow retention | How far back snapshots and clips are served, capped at 365 days. In custom mode, `0` means today only. |
| **Location precision** | **Approximate** | How precisely guest-facing features may use your configured location. |

**With the default Keep Everything retention policy, both public windows cover 365 days.**
The stored seven-day values apply only when you select custom windows. Check both windows
before sharing your URL.

Location precision defaults to **Approximate**. Choose **Exact** only if you want
guest-facing features to use your precise feeder location.

Guests can never request the current live frame from a camera. Header camera previews and
`/api/frigate/camera/{camera}/latest.jpg` always require owner access, even when camera names and
historical media are shared.

### Before you share the link

1. **Enable authentication** even though public access is read-only. Without it, everyone is an
   owner.
2. **Limit the history and media windows** to the shortest span you are happy to publish.
3. **Hide camera names** unless you want them public.
4. **Leave clip downloads off** unless someone actually needs the files.
5. **Set Trusted Proxy Hosts** so `X-Forwarded-*` headers cannot be spoofed.
6. **Keep the instance behind a single reverse proxy** with HTTPS.
7. **Read your AI output** before publishing it — it is generated text on a public page.

To check the result, open your public URL in a private browser window. A guest session is labelled
**Public view** at the foot of the sidebar, with a **Log in** button beside it, so you can tell at
a glance which view you are looking at.

### Guest view: troubleshooting

- **Guests see nothing:** confirm **Enable public access** is on and there are detections within
  the history window. A custom window of `0` shows only today’s detections.
- **Guests see settings:** authentication is disabled. Enable it and set a password.
- **Guests see grey placeholders instead of birds:** **Share photographs with visitors** is off, or
  the detection is older than the media window.
- **HTTPS warning appears:** make sure your reverse proxy passes `X-Forwarded-Proto`, and set
  Trusted Proxy Hosts (below).

## Reverse Proxy & Trusted Hosts

If you run YA-WAMF behind a reverse proxy (e.g., Nginx or Cloudflare Tunnel), you should **explicitly set Trusted Proxy Hosts** in **Settings → Security**.

- This tells YA-WAMF which proxy IPs, CIDR ranges, or hostnames/container names are allowed to set `X-Forwarded-*` headers.
- The default is permissive (trusts all proxies) for compatibility with existing installs.
- For Docker setups, container DNS names (e.g., `nginx-rp`, `cloudflare-tunnel`) work when services share a network.
- Hostnames are resolved to IPs at startup. If your proxy IPs change, prefer a stable container name.
- For Cloudflare DNS proxy (no tunnel), use Cloudflare IP ranges and keep them updated.

## Recommended Proxy Topology

To avoid HTTPS warnings and simplify proxy trust, use a **single reverse proxy** (Nginx Proxy Manager, Caddy, Traefik, Cloudflare Tunnel, etc.) pointing at a single upstream.

### Monolithic deployment (recommended)

Route all YA-WAMF traffic to one upstream:

- All traffic → `yawamf-monalithic:8080`

See the [Reverse Proxy Guide](../setup/reverse-proxy.md) for full Nginx Proxy Manager, Caddy, and Cloudflare Tunnel config examples including SSE and video clip tuning.

For correct HTTPS detection, always pass these headers:

```nginx
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Host $host;
proxy_set_header X-Forwarded-Proto $scheme;
```

### Cloudflare Tunnel (monolithic)

Point the tunnel service at `http://yawamf-monalithic:8080`. Add the tunnel container name (e.g., `cloudflared` or `cloudflare-tunnel`) to **Trusted Proxy Hosts** in **Settings → Security**.

### Legacy split deployment

> [!WARNING]
> The split `yawamf-frontend` + `yawamf-backend` stack is a legacy path. New installs should use the monolithic container. The examples below are kept for users who have not yet migrated.

For the split stack, route API calls directly to the backend to avoid a multi-hop proxy chain:

- `/` → `yawamf-frontend:80`
- `/api/*` → `yawamf-backend:8000`

Nginx (standalone) example:

```nginx
server {
    listen 443 ssl;
    server_name yawamf.example.com;

    location /api/ {
        proxy_pass http://yawamf-backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
    }

    location / {
        proxy_pass http://yawamf-frontend:80;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Cloudflare Tunnel ingress for split routing:

```yaml
ingress:
  - hostname: yawamf.example.com
    path: /api/*
    service: http://yawamf-backend:8000
  - hostname: yawamf.example.com
    service: http://yawamf-frontend:80
  - service: http_status:404
```

## Technical Details

- **Token Storage:** Authentication uses JWT (JSON Web Tokens) stored in your browser's Local Storage.
- **Media:** the browser sends the session in an `HttpOnly` cookie for images, clips, and audio.
  The app keeps the session token out of media URLs so it is not copied into URL logs. Only
  read-only media routes and the live stream accept this cookie; it cannot authorise settings
  changes or other writes. The app uses a Bearer header for those requests.
- **Live stream:** the browser's `EventSource` cannot send headers, so the live-update stream is
  opened with a single-use ticket exchanged from the session (`POST /api/auth/stream-ticket`),
  never with the session token in the URL. A ticket expires after 60 seconds and can be redeemed
  once. An unredeemed ticket exposed in a log remains usable until it expires. The stream also
  accepts the session cookie or a Bearer header.
- **Session Expiry:** Sessions are valid for 7 days by default (configurable).
- **Rate Limiting:** Login attempts are strictly rate-limited (5 per minute) to prevent brute-force attacks.
- **Legacy API Key:** Older `YA_WAMF_API_KEY` authentication still works but is deprecated.
