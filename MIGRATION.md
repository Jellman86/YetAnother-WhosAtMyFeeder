# Migration Guide

## Notes for Integrators (AI Output)

If you parse or post-process AI Naturalist output programmatically, treat the content as Markdown and avoid depending on exact heading names/ordering. No database migrations are required for these UI/content changes.

## Upgrading to v2.6.0 (Authentication & Public Access)

Version 2.6.0 introduces a major security upgrade with a new authentication system and public access controls. This guide covers how to migrate from previous versions.

### ⚡ Quick Summary

- **Zero Breaking Changes:** Your existing installation will continue to work.
- **New Feature:** You can now set a password for the admin interface.
- **New Feature:** You can enable a "Public View" to share your bird detections without giving admin access.
- **Deprecated:** The `YA_WAMF_API_KEY` environment variable is deprecated and will be removed in v2.9.0.

---

### 🟢 Scenario 1: Fresh Installation

If you are installing YA-WAMF for the first time:

1. Start the container.
2. Open the dashboard (`http://localhost:9852`).
3. You will see a **Setup Wizard**.
4. Create an admin username and password.
5. (Optional) You can choose to skip authentication if you are on a trusted local network, but it is recommended to secure your instance.

---

### 🟡 Scenario 2: Upgrading from v2.5.x (No API Key)

If you previously ran YA-WAMF without any authentication:

1. Update your Docker image tag to `v2.6.0` (or `latest`).
2. Recreate the container (`docker compose up -d`).
3. The system will automatically migrate your `config.json` to include the new authentication settings (disabled by default).
4. You will see a banner in the UI prompting you to secure your installation.
5. Go to **Settings > Security** to enable authentication and set a password.

---

### 🟠 Scenario 3: Upgrading with Legacy API Key

If you were using `YA_WAMF_API_KEY` in your `.env` file:

1. Update your Docker image.
2. The system will detect your existing API key and continue to honor it.
3. You will see a warning in the Settings page: **"Legacy API Key Detected"**.
4. **To Migrate:**
   - Go to **Settings > Security**.
   - Enable "Authentication".
   - Set a username and password.
   - Save settings.
5. **Cleanup:**
   - Once verified, remove `YA_WAMF_API_KEY` from your `.env` or `docker-compose.yml` file.
   - Restart the container.

---

### 🛡️ Rollback Guide

If you encounter issues after upgrading, you can easily roll back or reset authentication.

**Option A: Disable Auth via Config File**
If you get locked out or forget your password, you can manually reset it:

1. Access your server via SSH/terminal.
2. Edit `config/config.json`.
3. Find the `"auth"` section.
4. Remove the `"password_hash"` line (or set it to `null`).
   ```json
   "auth": {
     "enabled": true,
     "username": "admin",
     "password_hash": null,  <-- Set to null
     ...
   }
   ```
5. Restart the backend container. You will be prompted to set a new password.

For more details, see the [Authentication Guide](docs/features/authentication.md).

**Option B: Downgrade Docker Image**
You can revert by changing the image tag in `docker-compose.yml` to a prior version tag (for example `v2.5.1`). Newer `config.json` fields are typically ignored by older versions, but always keep a backup before downgrading.
