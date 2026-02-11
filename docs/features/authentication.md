# Authentication & Access Control

YA-WAMF provides a secure authentication system to protect your settings and data while offering flexible options for public access (Guest Mode).

## Overview

- **Owner:** Full access to settings, management, reclassification, and AI tools.
- **Guest (Public):** Read-only access to the dashboard and events (if enabled). No access to settings or actions that incur cost (like AI analysis).
- **Disabled:** Full access for everyone (default for backward compatibility, but not recommended for exposed instances).

## Enabling Authentication

By default, authentication is **disabled** to allow easy first-time setup. To enable it:

1.  Navigate to **Settings** > **Authentication**.
2.  Set a strong password.
3.  Enable **"Require Authentication"**.
4.  (Optional) Enable **"Public Access"** if you want to share your dashboard.

Alternatively, you can enable it via the `initial-setup` flow if you are accessing the instance for the first time without a configured password.

## Quick Start (Recommended)

1. **Enable Authentication** and set a strong password.
2. **Enable Public Access** only if you want a read‑only guest view.
3. **Set Trusted Proxy Hosts** if you are behind a reverse proxy (see below).
4. **Save** and refresh the UI to confirm the login prompt appears.

## Password Reset

Currently, there is no email-based "Forgot Password" flow. If you lose your password, you must reset it manually via the server file system.

1.  Access your server (SSH or direct access).
2.  Locate the `config/config.json` file in your mapped Docker volume.
3.  Find the `"auth"` section.
4.  Remove the `"password_hash"` line (or set the value to `null`).
5.  **Restart** the YA-WAMF container.
6.  Access the web UI. You will be prompted with the "Initial Setup" screen to create a new password.

**Example `config.json` edit:**

```json
{
  "auth": {
    "enabled": true,
    "username": "admin",
    "password_hash": null,  <-- Set this to null or delete the line
    ...
  }
}
```

## Public Access (Guest Mode)

You can allow unauthenticated users to view your detections while keeping settings secure.

- **Enable:** In **Settings** > **Public Access**, toggle "Enable Public Access".
- **Restrictions:**
    - Guests cannot change settings.
    - Guests cannot delete or reclassify detections.
    - Guests cannot trigger new AI Naturalist analysis (but can view existing analysis).
- Guests are rate-limited to prevent abuse.

### Guest Mode: What’s Exposed

When Public Access is enabled, guests can see:

- **Dashboard + Events** (limited by the configured history window).
- **Detection details** including timestamps, species labels, and confidence.
- **AI Naturalist analysis** if it already exists (guests cannot generate new analysis).
- **Camera names** *only if* "Show camera names to public users" is enabled.
- **Clip downloads** *only if* "Allow clip downloads" is enabled.

### Guest Mode: Recommended Safety Checklist

1. **Limit the history window** (e.g., 7–30 days) to reduce exposure.
2. **Hide camera names** unless you explicitly want them public.
3. **Disable guest clip downloads** unless required.
4. **Enable authentication** even if you allow public access.
5. **Set Trusted Proxy Hosts** to avoid spoofed `X-Forwarded-*` headers.
6. **Keep the instance behind a single reverse proxy** with HTTPS.
7. **Review AI text output** if you share the site publicly.

### Guest Mode: Troubleshooting

- **Guests see nothing:** Make sure "Enable Public Access" is on and your history window isn’t set to 0.
- **Guests see settings:** Authentication may be disabled. Enable it and set a password.
- **HTTPS warning appears:** Configure split routing and trusted proxy hosts (see below).

## Reverse Proxy & Trusted Hosts

If you run YA-WAMF behind a reverse proxy (e.g., Nginx or Cloudflare Tunnel), you should **explicitly set Trusted Proxy Hosts** in **Settings > Authentication**.

- This tells YA-WAMF which proxy IPs, CIDR ranges, or hostnames/container names are allowed to set `X-Forwarded-*` headers.
- The default is permissive (trusts all proxies) for compatibility with existing installs.
- For Docker setups, container DNS names (e.g., `nginx-rp`, `cloudflare-tunnel`) work when services share a network.
- Hostnames are resolved to IPs at startup. If your proxy IPs change, prefer a stable container name.
- For Cloudflare DNS proxy (no tunnel), use Cloudflare IP ranges and keep them updated.

## Recommended Proxy Topology (Split Routing)

To avoid HTTPS warnings and simplify proxy trust, use a **single reverse proxy** (Nginx Proxy Manager, Caddy, Traefik, Cloudflare Tunnel, etc.) and **route API calls directly to the backend**:

- `/` → `yawamf-frontend:80`
- `/api/*` → `yawamf-backend:8000`

This removes the extra proxy hop (frontend → backend) so YA-WAMF can trust only the actual reverse proxy.

### Nginx Proxy Manager example

Create a single proxy host (e.g. `yawamf.yourdomain`) and add **custom locations**:

```
/              -> yawamf-frontend:80
/api/          -> yawamf-backend:8000
/api/sse       -> yawamf-backend:8000
/api/frigate/* -> yawamf-backend:8000
```

Advanced config (recommended for SSE and correct HTTPS detection):

```
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Host $host;
proxy_set_header X-Forwarded-Proto $scheme;

# SSE
proxy_buffering off;
proxy_cache off;
proxy_read_timeout 86400s;
proxy_send_timeout 86400s;
```

If you keep a multi-hop proxy (NPM → frontend → backend), you must also trust the frontend proxy in YA-WAMF.

### Nginx (standalone) example

```
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

### Cloudflare Tunnel example

`cloudflared` ingress with split routing:

```
ingress:
  - hostname: yawamf.example.com
    path: /api/*
    service: http://yawamf-backend:8000
  - hostname: yawamf.example.com
    service: http://yawamf-frontend:80
  - service: http_status:404
```

Trusted Proxy Hosts:
- If using the tunnel container, add its service name (e.g., `cloudflared` or `cloudflare-tunnel`).
- If using Cloudflare DNS proxy without a tunnel, add Cloudflare IP ranges instead.

## Technical Details

- **Token Storage:** Authentication uses JWT (JSON Web Tokens) stored in your browser's Local Storage.
- **Session Expiry:** Sessions are valid for 7 days by default (configurable).
- **Rate Limiting:** Login attempts are strictly rate-limited (5 per minute) to prevent brute-force attacks.
 - **Legacy API Key:** Older `API_KEY` authentication still works but is deprecated.
