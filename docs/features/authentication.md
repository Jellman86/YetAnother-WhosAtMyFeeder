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

## Reverse Proxy & Trusted Hosts

If you run YA-WAMF behind a reverse proxy (e.g., Nginx or Cloudflare Tunnel), you should **explicitly set Trusted Proxy Hosts** in **Settings > Authentication**.

- This tells YA-WAMF which proxy IPs or container names are allowed to set `X-Forwarded-*` headers.
- The default is permissive (trusts all proxies) for compatibility with existing installs.
- For Docker setups, container DNS names (e.g., `nginx-rp`, `cloudflare-tunnel`) work when services share a network.

## Technical Details

- **Token Storage:** Authentication uses JWT (JSON Web Tokens) stored in your browser's Local Storage.
- **Session Expiry:** Sessions are valid for 7 days by default (configurable).
- **Rate Limiting:** Login attempts are strictly rate-limited (5 per minute) to prevent brute-force attacks.
 - **Legacy API Key:** Older `API_KEY` authentication still works but is deprecated.
