# Notifications

YA-WAMF sends detection alerts through Discord, Pushover, Telegram, and email.

## Notification history

The bell icon in the header opens the notification centre; **Notifications** in the sidebar opens
the full page. Both show one history, filtered by category: **Everything**, **Birds**, **Updates**,
**Jobs**, and **Errors**. The **Jobs** and **Errors** categories are owner-only.

The **Jobs** category separates queued, running, and recent work. Video analysis, best-quality
snapshots, full-visit clips, and backfills stay distinct, so a queued item is never presented as a
running worker.

The compact progress bar across the top of the application is reserved for prominent work you
started, such as a backfill or a manual analysis. Routine per-detection media work appears under
**Jobs** without keeping a permanent banner on screen. Jobs read current server state and fall back
to browser live updates, so opening a second tab does not create a second job or invent a separate
queue.

If live job status cannot be read, the page keeps the last known progress, shows a warning,
and retries automatically. **Try again** on a paused video-analysis lane reopens the circuit
breaker; it does not discard queued detections.

## Supported Platforms

### Discord
Sends rich embeds with snapshot previews to a Discord channel.

- **Webhook URL:** Create a webhook in your Discord server settings.
- **Bot Username:** Custom name for the bot (default: "YA-WAMF").
- **Snapshots:** Option to include the detection image.

### Pushover
Sends push notifications to your mobile device via the Pushover app.

- **User Key:** Your user identifier.
- **API Token:** Create a new application in Pushover to get this.
- **Priority:** Adjust the alert priority (-2 to 2).
- **Snapshots:** Attach images to notifications.

### Telegram
Sends messages or photos to a Telegram chat.

- **Bot Token:** From `@BotFather`.
- **Chat ID:** The user or group ID to send messages to.
- **Snapshots:** Send as a photo message (with caption) or just text.

### Email
Send rich HTML emails with optional snapshots.

- **OAuth (Gmail/Outlook):** Authorize YA-WAMF to send email on your behalf.
- **SMTP:** Configure your server hostname, port, TLS, and optional auth.
- **From/To:** Set sender and recipient addresses.
- **Snapshots:** Attach the detection image in the email.

## Linking back to the detection

Set **Instance address** under **Settings → Notifications** to the address you use to open
YA-WAMF, for example `https://feeder.example.com`. Every notification then links to the detection
it announces, at `<address>/events?event=<id>`:

- **Discord:** the embed title opens the detection.
- **Pushover:** a **View detection** button.
- **Telegram:** a **View detection** button under the photo or message.
- **Email:** the **View in Dashboard** button opens the detection rather than the dashboard.

**Notification link opens** chooses the target. **This YA-WAMF** (the default) opens the detection
as above. **Frigate** opens the same tracked object in Frigate's Explore page instead, at
`<Frigate public URL>/explore?event_id=<id>`, using the public URL saved under
**Settings → Integrations**; it needs Frigate 0.15 or newer. With Frigate chosen and no public URL
saved, notifications carry no link and the settings card says so, with a shortcut to Integrations.
A preview line under the choice shows the exact address the next notification will carry.

Leave the field blank and notifications carry no link, as before. The link is only as reachable as
the address you enter: a LAN address works on your network only, and a public address works from
anywhere. Opening a detection needs the owner sign-in unless public access is enabled, so a link
opened on a phone that is not signed in shows the sign-in page first. The environment variable is
`NOTIFICATIONS__INSTANCE_URL`; the older email-only `NOTIFICATIONS__EMAIL__DASHBOARD_URL` is still
honoured when the newer one is unset.

## Filtering

**Settings → Notifications** states your filter as a sentence, and every highlighted part of it is
a control:

> Tell me about **new visits** that are at least **70% sure** of **any species** on **Discord**

![Settings → Notifications: the Global Notification Filters card reading "Tell me about new visits that are at least 70% sure of any species on nowhere yet", with the notification cooldown, notification language, and the three species filter modes beneath](../images/settings-notifications.png)

### Minimum confidence
Only alert at or above this score (default `0.7`). Raise it to reduce alerts for lower-confidence
identifications. A high score does not guarantee that the identification is correct.

### Audio confirmed only
Alert only when the visual model identified a bird **and** BirdNET-Go heard the *same species*
within the configured correlation window. This requires supporting audio
evidence, but both models can still make mistakes. Visits without matching audio do not trigger
an alert. The sentence changes to **"70% sure and heard"** when it is on.

### Species filter
Three modes, chosen with the tiles under **Species filter**:

| Mode | Effect |
|---|---|
| **No species filter** | Notify for every species that passes the other filters. This is the default. |
| **Block selected species** | Notify for everything *except* the species you list. Use this to exclude frequent visitors. |
| **Only selected species** | Notify *only* for the species you list. Use this to watch for particular species. |

Species are matched on taxonomic identity rather than on display text, so a name change or a
different UI language does not quietly break your filter.

### Notification cooldown
A minimum gap in minutes between notifications, across all channels (default `0`, disabled).
Use it to reduce notification frequency when the feeder is busy.

## Notification Modes

Choose a delivery mode in **Settings → Notifications**:

- **Final-only:** Notify only when Frigate ends the event and video analysis (if enabled) completes.
- **Standard:** Notify when a confirmed detection is created.
- **Realtime:** Notify as early as possible and allow update notifications as detections evolve.
- **Silent:** Disable all notifications.
- **Advanced (Custom):** Manually toggle the exact triggers.

## How it Works

1. **Event Trigger:** A detection is processed and saved to the database.
2. **Filter Check:** The system checks your confidence, audio, and species filters.
3. **Dispatch:** If passed, the notification service dispatches async requests to all enabled platforms simultaneously.
4. **Rich Media:** If enabled, the system fetches the high-quality crop from Frigate to attach to the message.

## Setup

Go to **Settings → Notifications** to configure all of this. Saved webhooks, tokens, and
passwords display as `***REDACTED***` and are preserved when you save other settings, so you never
have to re-enter a working credential.
