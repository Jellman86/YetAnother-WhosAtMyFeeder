# Reverse Proxy Configuration Guide

When running Yet Another WhosAtMyFeeder (YA-WAMF) behind a reverse proxy, specific configurations are required to ensure the **Live Status** (Server-Sent Events) and **Video Playback** features work correctly without disconnection or buffering issues.

## Core Requirements

1.  **Support for Server-Sent Events (SSE):** Buffering must be disabled, and timeouts must be increased.
2.  **Long-Lived Connections:** The backend heartbeat is 20s. Proxy timeouts should be >60s.
3.  **Correct Headers:** `Host`, `X-Forwarded-For`, and `X-Forwarded-Proto` must be passed correctly to avoid "Authentication enabled over HTTP" warnings.

---

## 1. Cloudflare Tunnel

If you are using Cloudflare Tunnel (cloudflared), use these settings to prevent "unexpected EOF" or stream cancellations.

### Public Hostname Settings

*   **Service:** `http://yawamf-frontend:80` (or your internal IP/Hostname)
*   **HTTP Host Header:** `your-public-domain.com` (e.g., `yetanotherwhosatmyfeeder.pownet.uk`)
    *   *Critical:* Must match your public domain exactly. Do not duplicate it.

### Additional Settings (Parameters)

| Setting | Value | Reason |
| :--- | :--- | :--- |
| **No Chunked Encoding** | **Off** (Disabled) | **CRITICAL:** SSE requires chunked encoding. Enabling this will break the stream. |
| **Idle Timeout** | `120s` | Prevents Cloudflare from closing the stream during silence between heartbeats (20s). |
| **TCP Keep-Alive** | `15s` | Keeps the underlying tunnel socket active. |
| **Connect Timeout** | `30s` | Standard timeout. |

---

## 2. Nginx Proxy Manager (NPM)

In Nginx Proxy Manager, standard UI settings are not enough for SSE. You must use the **Advanced** tab.

### Details Tab
*   **Websockets Support:** Enabled
*   **Block Common Exploits:** Enabled

### SSL Tab
*   **Force SSL:** Enabled (or Disabled if Cloudflare handles it, to avoid redirect loops)
*   **HTTP/2 Support:** Enabled (Highly Recommended for SSE performance)
*   **HSTS:** Enabled

### Advanced Tab (Custom Configuration)
Paste this entire block into the "Custom Nginx Configuration" box. This handles SSE, Video Clips, and correct Header forwarding while using a resolver to prevent stale DNS cache issues.

```nginx
# Docker DNS Resolver (Required for dynamic container resolution)
resolver 127.0.0.11 valid=30s;
set $backend_upstream yawamf-backend;
set $frontend_upstream yawamf-frontend;

# Global Timeout Increase
proxy_read_timeout 86400s;
proxy_send_timeout 86400s;

# 1. Server-Sent Events (SSE) - Live Status Stream
location /api/sse {
    proxy_pass http://$backend_upstream:8000;

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
    proxy_set_header X-Forwarded-Proto $http_x_forwarded_proto;
}

# 2. Video Clips (Optimized for large files)
location ~ ^/api/frigate/.+/clip\.mp4$ {
    proxy_pass http://$backend_upstream:8000;

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
    proxy_set_header X-Forwarded-Proto $http_x_forwarded_proto;
}

# 3. Root / Main App
location /api/ {
    # Route all API traffic directly to the backend to preserve HTTPS detection
    proxy_pass http://$backend_upstream:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $http_x_forwarded_proto;
    proxy_http_version 1.1;
}

# 4. Root / Main App
location / {
    proxy_pass http://$frontend_upstream:80;
    
    # Ensure backend sees "https" even if proxy terminates SSL
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $http_x_forwarded_proto;
    
    # Standard NPM inclusions
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $http_connection;
    proxy_http_version 1.1;
}
```

---

## 3. Standard Nginx

If you are writing a raw `nginx.conf`:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    # ... SSL settings ...

    location /api/sse {
        proxy_pass http://yawamf-backend:8000;
        
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

    location /api/ {
        proxy_pass http://yawamf-backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        proxy_pass http://yawamf-frontend:80;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## 4. Caddy (Caddyfile)

Caddy handles SSE automatically in most cases, but ensuring `flush_interval` is set to -1 (immediate) helps.

```caddyfile
your-domain.com {
    reverse_proxy /api/sse yawamf-backend:8000 {
        # Flush immediately for SSE
        flush_interval -1
        header_up Host {host}
        header_up X-Forwarded-Proto {scheme}
    }

    reverse_proxy /api/* yawamf-backend:8000 {
        header_up Host {host}
        header_up X-Forwarded-Proto {scheme}
    }

    reverse_proxy /* yawamf-frontend:80 {
        header_up Host {host}
        header_up X-Forwarded-Proto {scheme}
    }
}
```

---

## Troubleshooting

### "System Offline" / Red Status Icon
*   **Cause:** Connection dropping between heartbeats (20s).
*   **Fix:** Increase proxy `read_timeout` to >60s and backend `keep-alive-timeout` to 75s.

### "Authentication enabled over HTTP" Warning
*   **Cause:** Backend sees `X-Forwarded-Proto: http` instead of `https`.
*   **Fix:** Ensure your proxy passes `proxy_set_header X-Forwarded-Proto $http_x_forwarded_proto;` (or hardcode to `https`).

### 404 Errors / 301 Redirect Loops
*   **Cause:** "Force SSL" enabled on Proxy but Cloudflare is connecting via HTTP.
*   **Fix:** Disable "Force SSL" on the internal proxy if Cloudflare is already handling HTTPS redirection, or ensure Cloudflare connects via HTTPS Origin.
