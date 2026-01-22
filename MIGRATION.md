# Authentication Migration Guide

This guide helps you migrate to YA-WAMF v2.6+ with the new JWT-based authentication system.

---

## Overview

**v2.6+** introduces optional JWT-based authentication replacing the legacy API key system.

### What's New

✅ JWT-based authentication
✅ Web-based login
✅ Public access mode (optional guest read-only)
✅ Security hardening (rate limiting, audit logs)
✅ Initial setup wizard

### Backward Compatibility

- Authentication is **disabled by default**
- Legacy API key still supported (deprecated)
- Existing installations continue working

---

## Migration Scenarios

### Fresh Install

**On first access:**
1. Navigate to YA-WAMF
2. First-Run Setup wizard appears
3. Set password OR skip (can enable later)

### Upgrade from v2.5.x (No Auth)

1. Pull latest: `docker compose pull && docker compose up -d`
2. Access YA-WAMF (no login required)
3. Enable auth in Settings → Security (optional)

### Upgrade from v2.5.x (With API Key)

1. Pull latest: `docker compose pull && docker compose up -d`
2. Legacy API key continues working (deprecated)
3. Enable new auth in Settings → Security
4. Update integrations to use JWT tokens
5. Remove `YA_WAMF_API_KEY` environment variable

---

## Configuration

### New Fields (config.json)

```json
{
  "auth": {
    "enabled": false,
    "username": "admin",
    "password_hash": null,
    "session_expiry_hours": 168
  },
  "public_access": {
    "enabled": false,
    "show_camera_names": true,
    "show_historical_days": 7,
    "rate_limit_per_minute": 30
  }
}
```

---

## Common Issues

### Locked Out After Enabling Auth

1. Stop backend: `docker compose stop yawamf-backend`
2. Edit `config/config.json`: Set `"enabled": false`
3. Restart: `docker compose start yawamf-backend`

### Forgotten Password

1. Stop backend
2. Set `"password_hash": null` in config.json
3. Restart and use setup wizard

### HTTPS Warning

⚠️ Use HTTPS in production! See [SECURITY.md](./SECURITY.md) for setup.

---

## Testing Checklist

- [ ] Can login with correct credentials
- [ ] Login rejects wrong password
- [ ] Session persists across refresh
- [ ] Public access works (if enabled)
- [ ] Cannot access Settings as guest
- [ ] HTTPS warning shows (if HTTP)

---

For detailed instructions, see full documentation at:
https://github.com/Jellman86/YetAnother-WhosAtMyFeeder

**Last Updated:** 2026-01-22
