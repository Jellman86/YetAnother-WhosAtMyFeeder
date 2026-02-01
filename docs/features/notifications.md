# Notifications

YA-WAMF includes a flexible multi-platform notification system that alerts you when birds are detected.

## Notification Center

Use the bell icon in the header to open the Notification Center. It separates **ongoing actions** (like backfills and reclassifications) with pinned progress bars, and lists completed notifications below.

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

## Intelligent Filtering

To prevent spam, you can configure powerful filters that apply to all notifications:

### 1. Minimum Confidence
Only send alerts if the detection confidence is above a certain threshold (default: 70%).
*   **Tip:** Set this higher than your database storage threshold to only get alerts for "sure things."

### 2. Audio Confirmation Only
**Enable this to eliminate false positives.**
When enabled, you will **only** receive a notification if:
*   The visual model detects a bird **AND**
*   BirdNET-Go simultaneously detects the *same species* by sound.

This creates a "dual-factor authentication" system for bird sightings, making alerts extremely reliable.

### 3. Species Whitelist
Only want to know about Cardinals and Blue Jays? Add them here. If the list is empty, you get notifications for everything.

## Notification Modes

Choose a delivery mode in **Settings → Notifications**:

- **Final-only:** Notify only when Frigate ends the event and video analysis (if enabled) completes.
- **Standard:** Notify when a confirmed detection is created.
- **Realtime:** Notify as early as possible and allow update notifications as detections evolve.
- **Silent:** Disable all notifications.
- **Advanced (Custom):** Manually toggle the exact triggers.

## How it Works

1. **Event Trigger:** A detection is processed and saved to the database.
2. **Filter Check:** The system checks your confidence, audio, and whitelist settings.
3. **Dispatch:** If passed, the notification service dispatches async requests to all enabled platforms simultaneously.
4. **Rich Media:** If enabled, the system fetches the high-quality crop from Frigate to attach to the message.

## Setup

Go to **Settings > Notifications** in the web dashboard to configure these options. Credentials are redacted in the UI for security.
