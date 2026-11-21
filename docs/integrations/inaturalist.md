# iNaturalist

YA-WAMF can submit **owner-reviewed** observations to iNaturalist using OAuth. This keeps a human in the loop and aligns with iNaturalist’s community guidelines.

## Requirements (App Owner Approval)
Check the current [iNaturalist application requirements](https://www.inaturalist.org/oauth/applications)
and obtain App Owner approval before creating OAuth credentials. Provider eligibility can change;
YA-WAMF cannot grant approval. Once approved, create an OAuth application and obtain its Client ID
and Client Secret.

## Create an iNaturalist App
1. Visit the iNaturalist Applications page and create a new application.
2. Set the **redirect URI** to:
   ```
   https://<your-domain>/api/inaturalist/oauth/callback
   ```
3. Save the application and copy the **Client ID** and **Client Secret**.

## Configure YA-WAMF
In **Settings → Sharing & integrations → More options → iNaturalist**:
- Enable the integration
- Paste the Client ID + Client Secret
- (Optional) Set default latitude/longitude/place
- Click **Connect iNaturalist** and complete OAuth. Private instances accept the provider redirect
  using the single-use owner-issued state; the redirect does not need a Bearer header. Complete
  the connection within ten minutes, or start it again after a server restart.

The Connect action persists only the iNaturalist enable flag and credentials currently shown in
that section before requesting the authorization URL. Other unsaved Settings edits are left alone.
YA-WAMF opens the sign-in window synchronously from your click so browser popup protection does not
mistake it for an unsolicited window; if popups are blocked, the UI tells you to allow them and
retry. Saved credentials remain redacted and can be reused without re-entering them.

## Before you connect
The submission panel appears in a visit's record only when iNaturalist is turned on and your
account is connected. There is no preview without OAuth: the earlier Debug UI preview has been
removed, so you need App Owner approval before you can see the panel.

## Reliability
YA-WAMF supports OAuth token refresh. Revoked access, changed credentials, provider policy or network failures can still require reconnection. Review the draft, photograph and location before submission: submitting sends those details to your connected iNaturalist account.

## Status
This integration is considered **Beta**. Authentication and submission are implemented, but real-account end-to-end verification remains an [integration testing gap](../../INTEGRATION_TESTING.md).
