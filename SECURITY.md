# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 2.6.x   | :white_check_mark: |
| 2.5.x   | :white_check_mark: |
| < 2.5   | :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability in YA-WAMF, please report it privately instead of opening a public issue.

**How to report:**
- Email: [security@ya-wamf.org](mailto:security@ya-wamf.org) (Replace with actual email or remove if not applicable)
- OR: Open a GitHub draft security advisory (if enabled on the repo).

I will acknowledge your report within 48 hours.

## Security Features (v2.6.0+)

YA-WAMF includes several built-in security features to protect your installation:

### 1. Authentication
- **JWT-based Auth:** Uses industry-standard JSON Web Tokens for session management.
- **Bcrypt Hashing:** Passwords are hashed using bcrypt with a configurable work factor.
- **Rate Limiting:** Login endpoints are strictly rate-limited (5 attempts/minute) to prevent brute-force attacks.

### 2. Network Security
- **Security Headers:** The application automatically adds HSTS (if HTTPS), X-Frame-Options, CSP, and X-Content-Type-Options headers.
- **HTTPS Warning:** The admin interface warns you if authentication is enabled over an insecure HTTP connection.
- **Proxy Support:** Correctly handles `X-Forwarded-For` headers when running behind a reverse proxy (like Nginx or Traefik).

### 3. Public Access Control
- **Granular Permissions:** "Guest" mode allows read-only access to detections while blocking sensitive actions (delete, reclassify, settings).
- **Data Filtering:** You can configure the number of historical days visible to guests.
- **Camera Privacy:** Option to hide camera names from public view.

## Best Practices

To ensure your installation is secure:

1. **Use HTTPS:** Always run YA-WAMF behind a reverse proxy (like Nginx, Caddy, or Traefik) with SSL/TLS enabled.
2. **Enable Authentication:** Do not leave your instance open to the internet without a password.
3. **Keep Updated:** Apply updates regularly to get the latest security patches.
4. **Isolate Network:** If possible, run your Docker containers in an isolated network segment (VLAN).