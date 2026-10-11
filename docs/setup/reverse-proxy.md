# Reverse Proxy Configuration Guide

Proxy YA-WAMF through one address while preserving live updates, owner login and
video playback. Use HTTPS and enable YA-WAMF authentication before exposing its
administrative UI/API beyond your trusted network. Media routes enforce guest
sharing rules; the proxy must preserve the app's session cookie, authorization and
byte-range headers.

> [!WARNING]
> The monolithic container (`yawamf-monalithic`) is the recommended deployment. New installs should use the monolithic examples on this page. The split `yawamf-frontend` + `yawamf-backend` path is legacy and kept only for existing installs that have not yet migrated.

## Deployment Modes

YA-WAMF supports two proxy layouts:

- **Monolithic (recommended):** `yawamf-monalithic:8080` — one container, one upstream
- **Legacy split:** `yawamf-frontend:80` plus `yawamf-backend:8000` — two containers

Use the monolithic examples below for new installs. Only use the split upstreams if you are still running the old two-container stack and have not yet migrated.

## Core Requirements

1.  **Support for Server-Sent Events (SSE):** Buffering must be disabled, and timeouts must be increased.
2.  **Long-Lived Connections:** The backend heartbeat is 20s. Proxy timeouts should be >60s.
3.  **Correct Headers:** `Host`, `X-Forwarded-For`, and `X-Forwarded-Proto` must be passed correctly to avoid "Authentication enabled over HTTP" warnings.

---

## 1. Cloudflare Tunnel

If you are using Cloudflare Tunnel (cloudflared), use these settings to prevent "unexpected EOF" or stream cancellations.

### Public Hostname Settings

*   **Service:** `http://yawamf-monalithic:8080` (or your internal IP/Hostname)
*   **HTTP Host Header:** `your-public-domain.example`
    *   *Critical:* Must match your public domain exactly. Do not duplicate it.

### Additional Settings (Parameters)

| Setting | Value | Reason |
| :--- | :--- | :--- |
| **Disable Chunked Encoding** | Off (default) | Keep HTTP/1.1 streaming enabled. |
| **Connect Timeout** | `30s` (default) | Time allowed to establish the origin connection; this is not the SSE stream lifetime. |
| **TCP Keep Alive Interval** | `30s` (default) | Origin TCP keepalive interval. |

These names follow [Cloudflare's origin parameter reference](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/origin-parameters/).
**Idle Connection Expiration Time** controls idle pooled origin connections; it is
not a guarantee for the lifetime of an active SSE response. Check every proxy hop
for buffering and stream timeouts if live updates disconnect.

---

## 2. Nginx Proxy Manager (NPM)

In Nginx Proxy Manager, standard UI settings are not enough for SSE. You must use the **Advanced** tab.

### Details Tab
* **Websockets Support:** Optional; YA-WAMF live updates use SSE, not WebSockets.
*   **Block Common Exploits:** Enabled

### SSL Tab
*   **Force SSL:** Enabled (or Disabled if Cloudflare handles it, to avoid redirect loops)
*   **HTTP/2 Support:** Enabled (Highly Recommended for SSE performance)
*   **HSTS:** Enabled

### Advanced Tab (Custom Configuration)
Use this **monolithic** example in the **Advanced** custom configuration, adapting
the hostname to your network. It assumes NPM terminates browser HTTPS. `$scheme`
records the connection that NPM received; behind another TLS-terminating proxy,
configure a trusted upstream header policy instead. Never blindly trust a public
client's `X-Forwarded-Proto` or `X-Forwarded-For`. Add the actual proxy addresses to
**Settings → Security → Trusted Proxy Hosts** (or `SYSTEM__TRUSTED_PROXY_HOSTS`).

```nginx
# Docker DNS Resolver (Required for dynamic container resolution)
resolver 127.0.0.11 valid=30s;
set $app_upstream yawamf-monalithic;

# Global Timeout Increase
proxy_read_timeout 86400s;
proxy_send_timeout 86400s;

# 1. Server-Sent Events (SSE) - Live Status Stream
location /api/sse {
    proxy_pass http://$app_upstream:8080;

    # Connection Settings
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    chunked_transfer_encoding on;

    # Critical: Disable Buffering
    proxy_buffering off;
    proxy_cache off;
    proxy_set_header X-Accel-Buffering no;

    # Extended Timeouts
    proxy_read_timeout 86400s;
    proxy_send_timeout 86400s;

    # Headers
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}

# 2. Video Clips (Optimized for large files)
location ~ ^/api/frigate/.+/clip\.mp4$ {
    proxy_pass http://$app_upstream:8080;

    # Enable Buffering for Performance
    proxy_buffering on;
    proxy_buffer_size 128k;
    proxy_buffers 8 256k;
    proxy_busy_buffers_size 512k;

    # Reasonable Timeout
    proxy_read_timeout 300s;
    proxy_send_timeout 300s;
    client_max_body_size 0;

    # Headers
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}

# 3. Manual Observation Upload (bounded multipart streaming)
location = /api/manual-observations {
    proxy_pass http://$app_upstream:8080;

    # The backend retains the exact 25 MiB image and 250 MiB video limits.
    # This bounded envelope leaves room for multipart fields and headers.
    client_max_body_size 256m;
    proxy_request_buffering off;

    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
}

# 4. API Routes
location /api/ {
    proxy_pass http://$app_upstream:8080;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_http_version 1.1;
}

# 5. Root / Main App
location / {
    proxy_pass http://$app_upstream:8080;
    
    # Forward the scheme of the connection this proxy received
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    
    # Standard NPM inclusions
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $http_connection;
    proxy_http_version 1.1;
}
```

If you are still on the legacy split deployment, keep the old two-upstream pattern:

- `/` -> `yawamf-frontend:80`
- `/api/*` -> `yawamf-backend:8000`

---

## 3. Standard Nginx

If you are writing a raw `nginx.conf`:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    # ... SSL settings ...

    location /api/sse {
        proxy_pass http://yawamf-monalithic:8080;
        
        # SSE Required Settings
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_cache off;
        chunked_transfer_encoding on;
        
        # Timeouts
        proxy_read_timeout 86400s;
        
        # Headers
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location = /api/manual-observations {
        proxy_pass http://yawamf-monalithic:8080;
        client_max_body_size 256m;
        proxy_request_buffering off;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /api/ {
        proxy_pass http://yawamf-monalithic:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        proxy_pass http://yawamf-monalithic:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

The exact manual-observation location takes precedence over the generic `/api/` route. The 256 MiB
request envelope is intentionally bounded: it covers multipart overhead while the application
continues to reject image files above 25 MiB and video files above 250 MiB. Disabling request
buffering avoids storing a second full copy at the proxy before the backend streams and validates
the upload.

---

## 4. Caddy (Caddyfile)

Caddy handles SSE automatically in most cases, but ensuring `flush_interval` is set to -1 (immediate) helps.

```caddyfile
your-domain.com {
    reverse_proxy /api/sse yawamf-monalithic:8080 {
        # Flush immediately for SSE
        flush_interval -1
        header_up Host {host}
        header_up X-Forwarded-Proto {scheme}
    }

    reverse_proxy /api/* yawamf-monalithic:8080 {
        header_up Host {host}
        header_up X-Forwarded-Proto {scheme}
    }

    reverse_proxy /* yawamf-monalithic:8080 {
        header_up Host {host}
        header_up X-Forwarded-Proto {scheme}
    }
}
```

---

## Troubleshooting

### "System Offline" / Red Status Icon
*   **Cause:** Connection dropping between heartbeats (20s).
* **Fix:** Confirm buffering is disabled and each proxy's active-response read timeout
  exceeds the 20-second heartbeat interval. Test the direct app address as well as
  the public URL to distinguish an app/network outage from a proxy timeout.

### "Authentication enabled over HTTP" Warning
*   **Cause:** Backend sees `X-Forwarded-Proto: http` instead of `https`.
* **Fix:** Forward the real browser-facing scheme from a trusted proxy, and configure
  **Trusted Proxy Hosts** for that proxy. Use `$scheme` where the proxy terminates
  HTTPS; behind a tunnel or another proxy, preserve only that trusted hop's scheme.
  Do not hardcode HTTPS for a route that also accepts unprotected HTTP.

### 404 Errors / 301 Redirect Loops
*   **Cause:** "Force SSL" enabled on Proxy but Cloudflare is connecting via HTTP.
*   **Fix:** Disable "Force SSL" on the internal proxy if Cloudflare is already handling HTTPS redirection, or ensure Cloudflare connects via HTTPS Origin.
