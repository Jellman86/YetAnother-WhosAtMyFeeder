# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 2.6+    | :white_check_mark: (with authentication) |
| 2.5.x   | :white_check_mark: (legacy API key) |
| < 2.5   | :x:                |

---

## Overview

YA-WAMF takes security seriously. This document outlines security features, best practices, and how to report vulnerabilities.

---

## Security Features (v2.6+)

### Authentication & Authorization

YA-WAMF implements a JWT-based authentication system:

- **Bcrypt Password Hashing** - Passwords are hashed using bcrypt with automatic salting
- **JWT Tokens** - HS256 signed tokens with configurable expiry (default: 7 days)
- **Role-Based Access** - Owner (full access) and Guest (read-only) roles
- **Public Access Mode** - Optional unauthenticated read-only access
- **Initial Setup Wizard** - Secure first-run password configuration

### Security Hardening

#### 1. Security Headers

All API responses include security headers:

| Header | Purpose |
|--------|---------|
| `Strict-Transport-Security` | Force HTTPS (HTTPS only) |
| `X-Content-Type-Options` | Prevent MIME sniffing |
| `X-Frame-Options` | Prevent clickjacking |
| `X-XSS-Protection` | Enable browser XSS filter |
| `Content-Security-Policy` | Control resource loading |
| `Referrer-Policy` | Prevent referrer leakage |
| `Permissions-Policy` | Disable unused browser features |

#### 2. Rate Limiting

**Login Endpoint:**
- 5 attempts per minute per IP
- 20 attempts per hour per IP
- Works behind proxies (`X-Forwarded-For`, `X-Real-IP`)

**Guest API Access:**
- Configurable per-minute limit (default: 30/minute)

#### 3. Input Validation

**Username:** Alphanumeric + underscore/hyphen/period, 1-50 chars
**Password:** 8-128 chars, must contain letter + number

#### 4. Audit Logging

All authentication events are logged with structured fields.

**Search logs:**
```bash
# All auth events
grep "AUTH_AUDIT" logs/backend.log

# Failed login attempts
grep "event_type=login_failure" logs/backend.log
```

#### 5. HTTPS Detection

- Backend logs warnings when auth enabled over HTTP
- Frontend displays red warning banner

---

## Best Practices

### ⚠️ CRITICAL: Use HTTPS in Production

**Always use HTTPS when authentication is enabled.**

HTTP transmits credentials in plaintext, making them vulnerable to:
- Network sniffing
- Man-in-the-middle attacks
- Session hijacking

**Setup Options:**

1. **Reverse Proxy (Nginx/Traefik/Caddy)** - Recommended
2. **Cloudflare Tunnel** - Free HTTPS, no port forwarding
3. **Let's Encrypt** - Free SSL certificates

**Example Nginx Config:**
```nginx
server {
    listen 443 ssl http2;
    server_name yawamf.example.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://localhost:8946;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Strong Passwords

- Use a password manager to generate strong passwords
- Minimum 12 characters recommended (8 required)
- Include letters, numbers, and symbols

### Regular Updates

- Keep YA-WAMF updated to receive security patches
- Monitor the GitHub repository for security advisories

### Network Security

- Use firewall to restrict access
- Consider IP whitelisting for sensitive deployments
- Monitor failed login attempts
- Use VPN for remote access

---

## Known Limitations

### Single-User System

- Only one admin account supported
- For multi-user: Use reverse proxy authentication (Authelia, Authentik)

### JWT Token Revocation

- Tokens remain valid until expiry (cannot be revoked)
- Logout is client-side only
- Changing password does NOT invalidate existing tokens

**Mitigation:** Restart backend to change session secret (invalidates all tokens)

### No Account Lockout

- Rate limiting provides brute-force protection
- No automatic account suspension after failures
- Monitor audit logs for suspicious activity

### localStorage Token Storage

- Tokens stored in browser localStorage
- Vulnerable to XSS (acceptable for self-hosted apps)

---

## Reporting a Vulnerability

If you discover a security vulnerability:

1. **DO NOT** create a public GitHub issue
2. Report via the **GitHub Security** tab or contact maintainers directly
3. Include:
   - Description of vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if available)

### Disclosure Policy

- We will acknowledge receipt within 48 hours
- We will provide a fix timeline within 1 week
- We will credit you in the security advisory (unless you prefer anonymity)
- We request 90 days before public disclosure

---

## Security Checklist

### Initial Setup

- [ ] Enable HTTPS
- [ ] Set strong admin password (12+ characters)
- [ ] Review default settings
- [ ] Disable public access if not needed
- [ ] Configure rate limiting appropriately

### Regular Maintenance

- [ ] Update to latest version monthly
- [ ] Review audit logs weekly
- [ ] Rotate passwords quarterly
- [ ] Backup configuration monthly
- [ ] Monitor failed login attempts

### Production Deployment

- [ ] HTTPS enabled and tested
- [ ] Firewall configured
- [ ] Rate limiting tested
- [ ] Audit logging enabled
- [ ] Backups configured
- [ ] Reverse proxy headers configured (if applicable)

---

## Common Security Concerns

### API Exposure

Ensure your `docker-compose.yml` does not expose the backend port (8000/8946) to the public internet without a reverse proxy handling HTTPS and authentication.

### MQTT Auth

We recommend using MQTT username/password authentication in production environments.

### Camera Access

If using public access mode, be aware that camera feeds and locations may be visible to unauthenticated users.

---

## Security Roadmap

### Planned Enhancements (v2.7+)

- Account lockout after N failed attempts
- Session management (view/revoke active sessions)
- Token refresh mechanism
- Two-factor authentication (TOTP)
- OAuth integration (Google, GitHub)

---

## References

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [NIST Password Guidelines](https://pages.nist.gov/800-63-3/)
- [JWT Best Practices](https://tools.ietf.org/html/rfc8725)

---

**Last Updated:** 2026-01-22
**Version:** 2.6.0+
