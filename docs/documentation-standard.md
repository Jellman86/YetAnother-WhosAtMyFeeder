# Documentation standard

YA-WAMF documentation is part of the product. It must help a self-hosted user
understand what the app will do before they point it at a live Frigate NVR,
BirdNET-Go instance, notification channel, or public URL.

## Audience

Write for a person running one self-hosted server with Docker Compose, an
existing Frigate NVR, and optionally BirdNET-Go, a reverse proxy, and Home
Assistant. Assume they understand containers, MQTT, and file permissions, but do
not assume they know YA-WAMF's vocabulary (detection, classification, admission,
correlation, admission threshold, guest access) yet.

## Source of truth

Ground every claim in the current repository:

- Code and tests are the source of truth for behaviour.
- `backend/app/routers/` is the source of truth for the API; document no endpoint
  that does not exist there.
- `backend/app/config_models.py` is the source of truth for settings, defaults,
  and valid ranges.
- Compose files (`docker-compose.monolith.yml`, `docker-compose.yml`,
  `docker-compose.prod.yml`) are the source of truth for deployment examples.
- Svelte UI text and routes under `apps/ui/src` are the source of truth for
  screen names and control labels.
- Existing docs are context, not proof. Correct them when the code has moved on.

Do not invent capabilities, settings, guarantees, support promises, or future
dates. Mark unverified assumptions explicitly or remove them.

## Roadmap, changelog, issue, and pull request boundaries

Keep the project records distinct:

- [`../ROADMAP.md`](../ROADMAP.md) contains prioritised future user/operator
  outcomes, their dependencies, and the evidence needed to consider them
  complete. It contains no promised dates and never describes planned work as
  available.
- [`../CHANGELOG.md`](../CHANGELOG.md) records implemented user- or
  operator-relevant changes under **Unreleased** until release.
- GitHub issues hold actionable scope, acceptance criteria, reproduction
  evidence, and current discussion. Link a roadmap outcome to an issue when it
  becomes concrete enough to implement.
- Pull requests deliver one reviewable behaviour change or tightly related
  maintenance slice into `dev`, with actual verification and material risk
  recorded. Release pull requests alone promote reviewed `dev` state to `main`.
- Durable architecture, data-integrity, or security decisions belong in
  maintained documentation, not only in an issue or pull request conversation.

## Information architecture

Use the Diátaxis structure. Every user-facing page is exactly one kind:

| Kind | Purpose | Current examples |
|---|---|---|
| README | Project orientation, quick start, and links onward. | [`../README.md`](../README.md) |
| Tutorial | First successful run, safest path, expected results. | [`setup/getting-started.md`](setup/getting-started.md) |
| How-to | Task-focused operational guidance. | [`setup/reverse-proxy.md`](setup/reverse-proxy.md), [`setup/hardware-acceleration.md`](setup/hardware-acceleration.md), [`integrations/frigate.md`](integrations/frigate.md), [`troubleshooting/diagnostics.md`](troubleshooting/diagnostics.md) |
| Reference | Complete lookup information. | [`setup/configuration.md`](setup/configuration.md), [`api.md`](api.md) |
| Explanation | Product direction, tradeoffs, architecture. | [`features/model-accuracy.md`](features/model-accuracy.md), roadmap. |

Keep detail out of the README when a docs page can carry it better. The README
orients and links; [`index.md`](index.md) routes; individual pages solve one user
need. When you add a user-facing page, link it from [`index.md`](index.md).

## Page pattern

For task pages, prefer this order:

1. User outcome.
2. Prerequisites or safety warning.
3. Smallest working path.
4. Expected result.
5. Optional details and variants.
6. Troubleshooting or next link.

For procedures, use short numbered steps. Add a short "You should see" or
"If it fails" paragraph when the result is not obvious.

For reference pages, use consistent tables, valid enum values, request/response
examples, and links to related concepts.

## Safety requirements

YA-WAMF ingests untrusted external input (Frigate MQTT events, BirdNET-Go
payloads, media URLs) and keeps a durable detection history the user cares about.
Every page that touches deletion, retention, credentials, public access, or media
proxying must state the relevant boundary:

- The detections database is user data; ingest is idempotent (`frigate_event` is
  unique) so a re-processed event does not duplicate or mutate history.
- Hiding a detection is a soft delete (`is_hidden`) and is recoverable; a hard
  delete is irreversible and must be labelled as such.
- Retention cleanup permanently deletes detections — visual and BirdNET-Go audio —
  older than `maintenance.retention_days`. Purged history cannot be recovered.
- Secrets (API keys, tokens, passwords) are redacted as `***REDACTED***` in API
  responses, are never written to logs, and are preserved on settings writes.
- Public/guest access and privacy controls change what an unauthenticated visitor
  can see; the UI and API are administrative surfaces and need an authenticated
  reverse proxy if exposed remotely.
- Media (snapshots, clips, spectrograms) is proxied so no Frigate/BirdNET-Go token
  reaches the browser.

Never imply a destructive action is reversible when it is not.

## Screenshots

Screenshots must be current, specific, and useful:

- Capture from the current UI or a local build matching the documented behaviour.
- Prefer focused section screenshots over full-page images when explaining one
  control or workflow.
- Use stable filenames under `docs/images/`.
- Include meaningful alt text that describes the UI information, not just the page
  name.
- Do not show real provider tokens, hostnames that reveal secrets, or private
  location data. YA-WAMF screenshots are its own detections, so no copyrighted
  third-party media disclaimer is required.

## Style

- Use plain English, active voice, and `you` for instructions.
- Use exact UI labels in bold, for example **Settings → Detection**.
- Use monospace for paths, commands, endpoints, environment variables, enum
  values, and file names.
- Prefer "YA-WAMF does X" over vague passive phrasing.
- Keep paragraphs short.
- Explain acronyms (NVR, NPU, MQTT, SSE) the first time they matter.
- Avoid marketing language, release promises, and generic filler.
- Avoid "we"; use "YA-WAMF" or "you".

## Commands and examples

Commands must be copyable and match the repository:

- Use `docker compose`, not legacy `docker-compose`.
- Use real container paths: `/config`, `/data`.
- Use current image names and the committed compose examples.
- Prefer `curl -fsS` in API recipes when a failure should stop a shell script.
- Redact secrets in examples.
- Include the expected response when it helps the user confirm success.

## API docs

The API reference ([`api.md`](api.md)) is separate from workflow docs. It should
state the authentication boundary and common status codes, group endpoints by
method/path/purpose, show request bodies for writes and response examples for
important reads, and note the safety implications of automation. Do not document
an endpoint unless it exists under `backend/app/routers/`.

## Release notes

GitHub Release notes are a short, friendly guide to an update, not a second
changelog. Write for the person deciding whether to update a working feeder.

- Open with one or two sentences that explain who will notice the release and why.
- Group bullets by user outcome, not by code area. Prefer **What's new**,
  **Smoother everyday use**, and **Before you update** over Backend/Frontend/Other.
- Start each bullet with a short bold benefit, then explain the practical change
  in one or two sentences.
- Use `you` and plain English. Explain an unavoidable technical term the first
  time it matters.
- State new defaults, opt-in behaviour, migration steps, downtime, hardware
  limits, and meaningful tradeoffs honestly. If no special action is needed, say
  so.
- Keep implementation detail in `CHANGELOG.md`; link it for readers who want the
  complete record.
- Omit empty sections. Never pad the notes with commit titles, issue numbers,
  generic praise, or promises the shipped code does not prove.

Use [`development/releasing.md`](development/releasing.md) for the release workflow
and [the copy-ready template](../.github/RELEASE_NOTES_TEMPLATE.md) for every
GitHub Release.

## Validation checklist

Before finishing a documentation change:

1. Read the changed page from top to bottom.
2. Check UI labels against `apps/ui/src`.
3. Check commands, paths, and settings against the compose files and
   `backend/app/config_models.py`.
4. Check safety claims against the implementation.
5. Run `python backend/scripts/docs_consistency_check.py`.
6. Run `git diff --check`.
7. If screenshots changed, visually inspect them.
8. Confirm [`index.md`](index.md) links any new user-facing page.

If the change documents new behaviour, update `CHANGELOG.md` unless the change is
purely documentation-only.
