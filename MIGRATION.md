# Migration Guide

## Upgrading from v2.4.x to v2.5.0+ (Container Security Changes)

**Version 2.5.0 introduces important security improvements** - containers now run as non-root users instead of root.

### What Changed

- **Backend:** Now runs as UID 1000 (previously root/UID 0)
- **Frontend:** Now runs as UID 1000 (previously root/UID 0)
- **Impact:** Existing `config/` and `data/` directories may have permission issues

### Migration Options

Choose **ONE** of these options based on your setup:

#### Option 1: Change Directory Ownership (Recommended for new deployments)

Change your host directories to match the container user:

```bash
# Navigate to your YA-WAMF directory
cd /path/to/ya-wamf

# Change ownership to UID 1000
sudo chown -R 1000:1000 config data

# Restart containers
docker-compose down && docker-compose pull && docker-compose up -d
```

**Pros:** Most secure, follows best practices
**Cons:** Requires sudo access

---

#### Option 2: Use `user:` Override (Recommended for TrueNAS/existing setups)

Keep your existing directory ownership and run containers as your user. The updated `docker-compose.yml` uses `PUID` and `PGID` environment variables for this:

```bash
# In your .env file
PUID=568  # Replace with your UID
PGID=568  # Replace with your GID
```

**To find your UID/GID:**
```bash
# On Linux/TrueNAS
stat -c "%u %g" config/
# Or
ls -lan | grep config
```

**Pros:** No directory ownership changes needed
**Cons:** Overrides built-in security

---

#### Option 3: Make Directories World-Writable (Least secure)

```bash
cd /path/to/ya-wamf
chmod -R 777 config data
```

**⚠️ Only use this for testing/troubleshooting**

---

### Verification

After applying your chosen option, verify the containers start successfully:

```bash
docker logs yawamf-backend --tail 20
docker logs yawamf-frontend --tail 20
```

You should see no permission errors.

---

## Migrating from WhosAtMyFeeder v1 to YA-WAMF v2

If you are coming from the original `WhosAtMyFeeder` (v1), please note that **YA-WAMF (v2)** is a complete rewrite.

## Configuration Changes

*   **Format:** `config.yml` is deprecated. We now use a combination of Environment Variables (`.env`) for infrastructure and a web-based `config.json` for runtime settings.
*   **Frigate:** Instead of complex mapping, we simply ask for the Frigate URL. Camera names are automatically detected from the MQTT events.

## Database Migration

*   **Incompatible Schema:** The v1 database schema is not directly compatible with v2.
*   **Recommendation:** It is highly recommended to start with a fresh database (`speciesid.db`) to ensure the new "Leaderboard" and "Explorer" features work correctly with standardized species names.
*   **Legacy Data:** If you absolutely must keep your old data, you will need to manually export your v1 SQLite data and map it to the new `detections` table structure defined in `backend/app/repositories/detection_repository.py`.

## Docker Changes

*   **Service Name:** The main service is now split into `backend` and `frontend`.
*   **Ports:** The web interface is now served on port `3000` (or `80` inside the container) instead of the previous Flask default.
