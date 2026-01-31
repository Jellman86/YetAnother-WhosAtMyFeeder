# iNaturalist

YA-WAMF can submit **owner-reviewed** observations to iNaturalist using OAuth. This keeps a human in the loop and aligns with iNaturalist’s community guidelines.

## Requirements (App Owner Approval)
iNaturalist requires **manual approval** before you can create OAuth apps. Your account must:
- Be at least **2 months old**
- Have **10 improving identifications** in the last month

Once approved as an **App Owner**, you can create an OAuth application and obtain a Client ID + Client Secret.

## Create an iNaturalist App
1. Visit the iNaturalist Applications page and create a new application.
2. Set the **redirect URI** to:
   ```
   https://<your-domain>/api/inaturalist/oauth/callback
   ```
3. Save the application and copy the **Client ID** and **Client Secret**.

## Configure YA-WAMF
In **Settings → Integrations → iNaturalist**:
- Enable the integration
- Paste the Client ID + Client Secret
- (Optional) Set default latitude/longitude/place
- Click **Connect iNaturalist** and complete OAuth

## Status
**Note:** This integration is currently **untested** in YA-WAMF due to unavailable app credentials during development.

