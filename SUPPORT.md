# Get help with YA-WAMF

Start with the [documentation hub](docs/index.md), then check [Diagnostics & Logs](docs/troubleshooting/diagnostics.md)
for the failed stage. Search [existing issues](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues)
before opening a new report.

For a bug report, include:

- The running build, image family, model and actual provider shown under **Settings → Detection**.
- What you expected, what happened, when it happened, and steps that reproduce it.
- A fresh support bundle from **Settings → Health → Diagnostics export**, captured near the failure.
  Review it and any notes for private information before attaching it. A later healthy capture
  does not disprove an earlier incident.
- For UI problems, the browser/device and relevant console errors. For media problems, say whether
  Frigate still has a snapshot or clip for that event.

Do not post passwords, usable tokens, private camera URLs or unredacted configuration. The app
redacts saved secrets in API responses, but files you supply yourself can contain them. The
support-bundle workflow downloads a file; it does not automatically upload it to the project.

For vulnerabilities, follow [Security](SECURITY.md). This is a community project; response times vary.
