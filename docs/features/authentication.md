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
wizard. Creating a password signs that browser in immediately. Either choice completes first-run
account setup, which cannot later be claimed through the unauthenticated setup endpoint. Reopen
the non-destructive section map from **Settings → Setup wizard**.

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

While the **Garden animals** beta is on, guests also see confirmed Garden animals, under the same
switches and windows as bird detections. Captures waiting for review, dismissed captures and every
Garden review action stay owner-only.

Public history and media windows use **UTC calendar days**, regardless of the server’s `TZ`
setting. “Today only” starts at 00:00 UTC and excludes the next midnight; a custom `N`-day
window starts at 00:00 UTC `N` days ago. Capture times can still be displayed in your local
timezone. Photographs in About and leaderboard portraits follow the same media calendar.

**With the default Keep Everything retention policy, both public windows cover 365 days.**
The stored seven-day values apply only when you select custom windows. Check both windows
before sharing your URL.

Location precision defaults to **Approximate**. Choose **Exact** only if you want
guest-facing features to use your precise feeder location.

Diagnostics workspaces, support-bundle exports and model-evaluation artifacts require owner
access even when public viewing is enabled. A shared history or media window does not grant access
to these operational reports. Saved credentials remain redacted in API responses and are
preserved when you save other settings.

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

See [Reverse Proxy Configuration](../setup/reverse-proxy.md) for monolithic, Cloudflare Tunnel and
legacy split examples. Keep a single controlled proxy boundary and confirm HTTPS detection before
sharing the instance.

## Technical Details

Guest history limits apply before paging and counts, including statistics, leaderboards and audio.
Media requests recheck visibility and sharing switches. Hidden or unavailable evidence is not made
public through a cached annotation or upstream fetch. A failed refresh clears stale guest rows;
very low request limits or several visitors sharing an address may require a later manual refresh.
Signing out clears owner detail caches. Already downloaded data cannot be recalled from a browser.

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
- **Rate Limiting:** Login attempts are limited to 5 per minute and 20 per hour per client address.
- **Legacy API Key:** Older `YA_WAMF_API_KEY` authentication still works but is deprecated.

Guest audio confirmation uses currently visible evidence from the camera's mapped microphones.
Location precision also applies to saved manual-observation pins; owners keep the original coordinates.
