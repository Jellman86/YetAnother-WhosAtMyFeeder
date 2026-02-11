# Integration Testing Requests

Several third-party integrations are implemented in YA-WAMF but are not fully validated end-to-end by the maintainer (no accounts/credentials available for real-world verification).

If you can test any of the items below, please open a GitHub issue with results. Thank you.

## What To Include In A Test Report

- Which integration you tested (Gmail OAuth, Outlook OAuth, Telegram, Pushover, iNaturalist)
- Whether you were on `dev` images or a tagged release
- The exact error message shown in the UI (if any)
- Redacted backend logs around the failure (remove tokens, emails, chat IDs)
- Your SMTP provider + port if testing password SMTP (587 vs 465 matters)

## Email OAuth (Gmail)

Goal: connect OAuth and send an email via SMTP XOAUTH2.

Checklist:
1. Configure Gmail OAuth Client ID/Secret in Settings.
2. Click Connect Gmail and complete the OAuth flow.
3. Confirm the connected email is shown in Settings.
4. Click Send Test Email.
5. Wait 10+ minutes (or manually expire the token if you can) and re-test to confirm refresh works.

Notes:
- SMTP XOAUTH2 typically requires the full mail scope (`https://mail.google.com/`).

## Email OAuth (Outlook / Microsoft 365)

Goal: connect OAuth and send an email via SMTP XOAUTH2, including refresh tokens.

Checklist:
1. Configure Microsoft OAuth Client ID/Secret in Settings.
2. Click Connect Outlook and complete the OAuth flow.
3. Confirm the connected email is shown in Settings.
4. Click Send Test Email.
5. Wait for access token expiry and re-test to confirm refresh works.

Notes:
- This uses Microsoft identity platform v2.0 with delegated SMTP permission scope.

## Email (Password SMTP)

Goal: send an email via traditional SMTP with STARTTLS/TLS.

Checklist:
1. Configure SMTP host, port, from/to, username/password.
2. If your provider uses port 587, ensure TLS/STARTTLS is enabled.
3. Click Send Test Email.

If it fails, include:
- Port number (587 or 465)
- Whether TLS/STARTTLS toggle was enabled

## Telegram Bot API Notifications

Goal: send a Telegram notification (with and without a snapshot).

Checklist:
1. Configure bot token and chat ID in Settings.
2. Click Send Test Notification (Telegram).
3. Verify message formatting when species/camera contains special characters.
4. Trigger a real detection notification if possible (snapshot and no-snapshot paths).

Notes:
- Telegram has message length limits (caption vs message body). If you hit truncation, please report what content caused it.

## Pushover Notifications

Goal: send a Pushover notification (with and without a snapshot).

Checklist:
1. Configure Pushover User Key and API Token in Settings.
2. Click Send Test Notification (Pushover).
3. Trigger a real detection notification if possible (snapshot and no-snapshot paths).
4. Confirm message title/body fields render as expected in the Pushover app.

If it fails, include:
- Whether test send failed immediately or timed out
- Redacted response/error from backend logs
- Whether snapshot attachments were enabled

## iNaturalist Submissions

Goal: connect OAuth and submit a detection as an observation, including photo upload.

Checklist:
1. Enable iNaturalist integration and configure Client ID/Secret.
2. Click Connect iNaturalist and complete OAuth.
3. Open a detection modal and load the iNaturalist draft panel.
4. Submit the observation.
5. Confirm the observation exists on your iNaturalist account and the photo upload succeeded.

Notes:
- iNaturalist requires "App Owner" approval before you can create OAuth apps, which is why this has been hard to test without community help.
