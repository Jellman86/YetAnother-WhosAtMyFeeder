# Security Policy

## Supported Versions

Use the [latest stable release](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/latest)
for the current published fixes. Development builds receive ongoing changes and can be unstable.
Older tagged images are historical snapshots; check their release notes and upgrade before
assuming they contain a later security fix. This project does not promise a separate backport
stream for every older minor version.

## Reporting a Vulnerability

If you discover a security vulnerability in YA-WAMF, you may report it via a public GitHub issue.

**How to report:**
- Open a GitHub issue with clear reproduction steps and affected versions.

Do not include usable credentials, private camera URLs or unredacted support bundles in a public report. Describe the affected version and behavior; arrange a private exchange before sharing exploit details or secrets.

## Security Review Request

If you can, please perform a code review or pentest of YA-WAMF and report any issues you find. Practical reports (repro steps, impacted routes, configs) are especially helpful.

## Security Features

YA-WAMF includes several built-in security features to protect your installation:

### 1. Authentication
- **JWT-based Auth:** Uses industry-standard JSON Web Tokens for session management.
- **Bcrypt Hashing:** Passwords are hashed using bcrypt.
- **Rate Limiting:** Login attempts are limited to 5 per minute and 20 per hour per client address. Configure proxy trust correctly so that address is meaningful.
- **Optional API Key:** Legacy API key support for non-UI integrations.

### 2. Network Security
- **Security Headers:** The application automatically adds HSTS (if HTTPS), X-Frame-Options, CSP, and X-Content-Type-Options headers.
- **HTTPS Warning:** The admin interface warns you if authentication is enabled over an insecure HTTP connection.
- **Proxy Support:** Configure trusted proxy boundaries deliberately; see the [reverse proxy guide](docs/setup/reverse-proxy.md). Forwarded client headers must come from a proxy you control.

### 3. Public Access Control
- **Granular Permissions:** "Guest" mode allows read-only access to detections while blocking sensitive actions (delete, reclassify, settings).
- **Data Filtering:** You can configure the number of historical days visible to guests.
- **Media Privacy:** Camera names, photographs, video and audio have separate guest-sharing controls. Guest history limits apply to public records and media.

### 4. Data Protection & Secrets
- **Secret Redaction:** Settings responses redact saved credentials such as LLM keys, notification tokens and OAuth client secrets. Authentication endpoints issue session credentials to authorized clients.
- **Owner-only Settings:** Settings updates, support-bundle exports and test endpoints require owner permissions. When authentication is disabled, requests receive owner access. Saved configuration and backups may contain credentials; keep `/config` private.

### 5. Operational Safety
- **Health & Metrics:** Health checks and metrics endpoints help detect anomalies early.
- **Audit-Friendly Logs:** Structured logs provide diagnostic context, with credential redaction on supported paths. Review logs and support bundles before sharing them.

## Best Practices

To ensure your installation is secure:

1. **Use HTTPS:** Always run YA-WAMF behind a reverse proxy (like Nginx, Caddy, or Traefik) with SSL/TLS enabled.
2. **Enable Authentication:** Do not leave your instance open to the internet without a password.
3. **Keep Updated:** Apply updates regularly to get the latest security patches.
4. **Isolate Network:** If possible, run your Docker containers in an isolated network segment (VLAN).
