# Environment variables

Complete reference for every environment variable YA-WAMF reads. Everything that
can be configured in **Settings** can also be set here, so an install can be
driven entirely from `docker-compose` with no clicking.

## How overrides work

- **Precedence:** environment variable → `config/config.json` (what the UI writes)
  → built-in default. **If an env var is set, it wins and the matching field
  becomes read-only-in-effect** — editing it in the UI won't stick across a
  restart because the env value is re-applied on load.
- **Naming:** `SECTION__FIELD`, upper-case, with a **double underscore** between
  the section and the field (and again for nested notification channels, e.g.
  `NOTIFICATIONS__DISCORD__WEBHOOK_URL`).
- **Booleans** are the strings `true` / `false` (case-insensitive). **Numbers**
  are plain digits. **Lists** are comma-separated.
- **Set them** under `environment:` in `docker-compose.monolith.yml` (see the
  examples already there) or in your `.env` file.
- **Secrets** (tokens, passwords, API keys, webhook URLs) are redacted as
  `***REDACTED***` in the API and never logged. Setting one via env keeps it out
  of `config.json`.

> Not everything is env-configurable. A few things are **UI/file-only** by design
> — see [UI/file-only settings](#uifile-only-settings) at the end.

---

## Core & general

| Variable | Default | Description |
| --- | --- | --- |
| `YA_WAMF_API_KEY` | _(unset)_ | Require `X-API-Key` on all API requests when set. |
| `CONFIG_FILE` | `/config/config.json` | Path to the persisted config file. |
| `LOG_LEVEL` | `INFO` | Log verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |
| `SPECIES_INFO__SOURCE` | `auto` | Species info source: `auto`, `inat`, `wikipedia`. |
| `DISPLAY__DATE_FORMAT` | `locale` | Date format: `locale`, `mdy`, `dmy`, `ymd`. |

## Frigate & MQTT (Connection)

| Variable | Default | Description |
| --- | --- | --- |
| `FRIGATE__FRIGATE_URL` | `http://frigate:5000` | Frigate base URL for snapshots/clips. |
| `FRIGATE__FRIGATE_AUTH_TOKEN` | _(unset)_ | Bearer token if Frigate requires auth. |
| `FRIGATE__MAIN_TOPIC` | `frigate` | Frigate MQTT base topic. |
| `FRIGATE__MQTT_SERVER` | `mqtt` | MQTT broker host. |
| `FRIGATE__MQTT_PORT` | `1883` | MQTT broker port. |
| `FRIGATE__MQTT_AUTH` | `false` | Enable MQTT username/password auth. |
| `FRIGATE__MQTT_USERNAME` | _(empty)_ | MQTT username. |
| `FRIGATE__MQTT_PASSWORD` | _(empty)_ | MQTT password. |
| `FRIGATE__CLIPS_ENABLED` | `true` | Fetch event clips from Frigate. |
| `FRIGATE__RECORDING_CLIP_ENABLED` | `false` | Build clips from Frigate recordings. |
| `FRIGATE__RECORDING_CLIP_BEFORE_SECONDS` | `30` | Seconds of recording before the event. |
| `FRIGATE__RECORDING_CLIP_AFTER_SECONDS` | `90` | Seconds of recording after the event. |
| `FRIGATE__BIRDNET_ENABLED` | `true` | Enable the BirdNET-Go audio integration. |
| `FRIGATE__AUDIO_TOPIC` | `birdnet/text` | MQTT topic BirdNET-Go publishes to. |
| `FRIGATE__BIRDNET_URL` | _(empty)_ | Backend URL for spectrograms (e.g. Docker address). |
| `FRIGATE__BIRDNET_EXTERNAL_URL` | _(empty)_ | Browser-facing BirdNET-Go URL for dashboard links. |

## Detection (Classification)

| Variable | Default | Description |
| --- | --- | --- |
| `CLASSIFICATION__INFERENCE_PROVIDER` | `auto` | `auto`, `cpu`, `cuda`, `intel_gpu`, `intel_cpu`, `intel_npu`. |
| `CLASSIFICATION__USE_CUDA` | _(legacy)_ | Legacy boolean; mapped to `cuda`/`cpu` when the provider is unset. |
| `CLASSIFICATION__IMAGE_EXECUTION_MODE` | `in_process` | `in_process` (shared RAM) or `subprocess` (isolated). |
| `CLASSIFICATION__WRITE_FRIGATE_SUBLABEL` | `true` | Write the identified species back to Frigate as a sub-label. |
| `CLASSIFICATION__PERSONALIZED_RERANK_ENABLED` | `false` | Learn per-camera/model ranking from manual tags. |
| `CLASSIFICATION__STRICT_NON_FINITE_OUTPUT` | `true` | Reject all-non-finite classifier output (also `CLASSIFIER_STRICT_NON_FINITE_OUTPUT`). |
| `CLASSIFICATION__BIRD_CROP_SOURCE_PRIORITY` | `frigate_hints_first` | Crop-source order for the displayed image. |
| `CLASSIFICATION__MAX_CLASSIFICATION_RESULTS` | `5` | Top-N species kept per detection. |
| `CLASSIFICATION__AI_PRICING_JSON` | `[]` | Token pricing registry for cost estimates. |
| `CLASSIFICATION__AUTO_VIDEO_CLASSIFICATION` | `false` | Analyse video frames after a detection. |
| `CLASSIFICATION__VIDEO_CLASSIFICATION_DELAY` | `30` | Seconds to wait before video analysis. |
| `CLASSIFICATION__VIDEO_CLASSIFICATION_FRAMES` | `15` | Frames sampled per video. |
| `CLASSIFICATION__VIDEO_CLASSIFICATION_MAX_RETRIES` | `3` | Retries for a failed video job. |
| `CLASSIFICATION__VIDEO_CLASSIFICATION_RETRY_INTERVAL` | `15` | Seconds between video retries. |
| `CLASSIFICATION__VIDEO_CLASSIFICATION_MAX_CONCURRENT` | `1` | Concurrent video jobs. |
| `CLASSIFICATION__VIDEO_CLASSIFICATION_TIMEOUT_SECONDS` | `180` | Per-video timeout. |
| `CLASSIFICATION__VIDEO_CLASSIFICATION_STALE_MINUTES` | `15` | Age after which a queued video is dropped. |
| `CLASSIFICATION__VIDEO_FAILURE_THRESHOLD` | `5` | Failures before the video circuit opens. |
| `CLASSIFICATION__VIDEO_FAILURE_WINDOW_MINUTES` | `10` | Window for counting video failures. |
| `CLASSIFICATION__VIDEO_FAILURE_COOLDOWN_MINUTES` | `15` | Cooldown while the video circuit is open. |
| `CLASSIFICATION__LIVE_WORKER_COUNT` | `2` | Live-inference worker processes. |
| `CLASSIFICATION__BACKGROUND_WORKER_COUNT` | `1` | Background-inference worker processes. |
| `CLASSIFICATION__LIVE_EVENT_COALESCING_ENABLED` | `true` | Coalesce rapid live events. |
| `CLASSIFICATION__LIVE_EVENT_STALE_DROP_SECONDS` | `30.0` | Drop live events older than this. |
| `CLASSIFICATION__WORKER_HEARTBEAT_TIMEOUT_SECONDS` | `5.0` | Worker heartbeat timeout. |
| `CLASSIFICATION__WORKER_HARD_DEADLINE_SECONDS` | `35.0` | Live worker hard deadline. |
| `CLASSIFICATION__BACKGROUND_WORKER_HARD_DEADLINE_SECONDS` | `120.0` | Background worker hard deadline. |
| `CLASSIFICATION__WORKER_READY_TIMEOUT_SECONDS` | `20.0` | Worker start-up readiness timeout. |
| `CLASSIFICATION__WORKER_RESTART_WINDOW_SECONDS` | `60.0` | Window for counting worker restarts. |
| `CLASSIFICATION__WORKER_RESTART_THRESHOLD` | `3` | Restarts before the worker breaker trips. |
| `CLASSIFICATION__WORKER_BREAKER_COOLDOWN_SECONDS` | `60.0` | Cooldown after the worker breaker trips. |

## Media cache & maintenance (Data)

| Variable | Default | Description |
| --- | --- | --- |
| `MEDIA_CACHE__ENABLED` | `true` | Master switch for media caching. |
| `MEDIA_CACHE__CACHE_SNAPSHOTS` | `true` | Cache event snapshots locally. |
| `MEDIA_CACHE__CACHE_CLIPS` | `false` | Cache event clips locally. |
| `MEDIA_CACHE__HIGH_QUALITY_EVENT_SNAPSHOTS` | `false` | Store full-resolution event snapshots. |
| `MEDIA_CACHE__HIGH_QUALITY_EVENT_SNAPSHOT_BIRD_CROP` | `false` | Store a high-quality bird crop. |
| `MEDIA_CACHE__HIGH_QUALITY_EVENT_SNAPSHOT_JPEG_QUALITY` | `95` | JPEG quality for high-quality snapshots. |
| `MEDIA_CACHE__RETENTION_DAYS` | `0` | Days to keep cached media (`0` = keep). |
| `MAINTENANCE__RETENTION_DAYS` | `0` | Days to keep detection history (`0` = keep forever). |
| `MAINTENANCE__CLEANUP_ENABLED` | `true` | Run the periodic cleanup job. |
| `MAINTENANCE__MAX_CONCURRENT` | `1` | Concurrent maintenance operations. |
| `MAINTENANCE__AUTO_DELETE_MISSING_CLIPS` | `false` | Prune records whose Frigate clip is gone. |
| `MAINTENANCE__FRIGATE_MISSING_BEHAVIOR` | _(unset)_ | How to treat detections missing in Frigate (`mark`/`keep`). |

## Integrations

| Variable | Default | Description |
| --- | --- | --- |
| `BIRDWEATHER__ENABLED` | `false` | Enable BirdWeather reporting. |
| `BIRDWEATHER__STATION_TOKEN` | _(unset)_ | BirdWeather station token. |
| `EBIRD__ENABLED` | `false` | Enable eBird hotspot lookups. |
| `EBIRD__API_KEY` | _(unset)_ | eBird API key. |
| `EBIRD__DEFAULT_RADIUS_KM` | `25` | Default hotspot search radius. |
| `EBIRD__DEFAULT_DAYS_BACK` | `14` | Default hotspot look-back window. |
| `EBIRD__MAX_RESULTS` | `25` | Max hotspot results. |
| `EBIRD__LOCALE` | `en` | eBird common-name locale. |
| `INATURALIST__ENABLED` | `false` | Enable iNaturalist integration. |
| `INATURALIST__CLIENT_ID` | _(unset)_ | iNaturalist OAuth client ID. |
| `INATURALIST__CLIENT_SECRET` | _(unset)_ | iNaturalist OAuth client secret. |
| `ENRICHMENT__MODE` | `per_enrichment` | `per_enrichment` or `single_provider`. |
| `ENRICHMENT__SINGLE_PROVIDER` | `wikipedia` | Provider when in single-provider mode. |
| `ENRICHMENT__SUMMARY_SOURCE` | `wikipedia` | Source for species summaries. |
| `ENRICHMENT__TAXONOMY_SOURCE` | `inaturalist` | Source for taxonomy. |
| `ENRICHMENT__SIGHTINGS_SOURCE` | `disabled` | Source for recent sightings. |
| `ENRICHMENT__SEASONALITY_SOURCE` | `disabled` | Source for seasonality. |
| `ENRICHMENT__RARITY_SOURCE` | `disabled` | Source for rarity. |
| `ENRICHMENT__LINKS_SOURCES` | `wikipedia,inaturalist` | Comma-separated link sources. |

## AI (LLM)

| Variable | Default | Description |
| --- | --- | --- |
| `LLM__ENABLED` | `false` | Enable LLM behavioural analysis / chat. |
| `LLM__PROVIDER` | `gemini` | `gemini`, `openai`, `claude`, `openrouter`. |
| `LLM__API_KEY` | _(unset)_ | Provider API key. |
| `LLM__MODEL` | _(provider default)_ | Model ID. |
| `LLM__ANALYSIS_PROMPT_TEMPLATE` | _(built-in)_ | Behavioural-analysis prompt. |
| `LLM__CONVERSATION_PROMPT_TEMPLATE` | _(built-in)_ | Conversation prompt. |
| `LLM__CHART_PROMPT_TEMPLATE` | _(built-in)_ | Chart-analysis prompt. |

## Notifications

Global:

| Variable | Default | Description |
| --- | --- | --- |
| `NOTIFICATIONS__MODE` | `standard` | `silent`, `final`, `standard`, `realtime`, `custom`. |
| `NOTIFICATIONS__NOTIFY_ON_INSERT` | `true` | Notify on a new detection. |
| `NOTIFICATIONS__NOTIFY_ON_UPDATE` | `false` | Notify on an updated detection. |
| `NOTIFICATIONS__DELAY_UNTIL_VIDEO` | `false` | Hold until video analysis completes. |
| `NOTIFICATIONS__VIDEO_FALLBACK_TIMEOUT` | `45` | Seconds to wait for video before sending anyway. |
| `NOTIFICATIONS__NOTIFICATION_COOLDOWN_MINUTES` | `0` | Global cooldown between notifications. |
| `NOTIFICATIONS__NOTIFICATION_LANGUAGE` | `en` | Notification language. |

Discord / Pushover / Telegram / Email:

| Variable | Default | Description |
| --- | --- | --- |
| `NOTIFICATIONS__DISCORD__ENABLED` | `false` | Enable Discord. |
| `NOTIFICATIONS__DISCORD__WEBHOOK_URL` | _(unset)_ | Discord webhook URL. |
| `NOTIFICATIONS__DISCORD__USERNAME` | `YA-WAMF` | Webhook display name. |
| `NOTIFICATIONS__DISCORD__INCLUDE_SNAPSHOT` | `true` | Attach a snapshot. |
| `NOTIFICATIONS__PUSHOVER__ENABLED` | `false` | Enable Pushover. |
| `NOTIFICATIONS__PUSHOVER__USER_KEY` | _(unset)_ | Pushover user key. |
| `NOTIFICATIONS__PUSHOVER__API_TOKEN` | _(unset)_ | Pushover API token. |
| `NOTIFICATIONS__PUSHOVER__PRIORITY` | `0` | Message priority (`-2`…`2`). |
| `NOTIFICATIONS__PUSHOVER__INCLUDE_SNAPSHOT` | `true` | Attach a snapshot. |
| `NOTIFICATIONS__TELEGRAM__ENABLED` | `false` | Enable Telegram. |
| `NOTIFICATIONS__TELEGRAM__BOT_TOKEN` | _(unset)_ | Telegram bot token. |
| `NOTIFICATIONS__TELEGRAM__CHAT_ID` | _(unset)_ | Telegram chat ID. |
| `NOTIFICATIONS__TELEGRAM__INCLUDE_SNAPSHOT` | `true` | Attach a snapshot. |
| `NOTIFICATIONS__EMAIL__ENABLED` | `false` | Enable email. |
| `NOTIFICATIONS__EMAIL__ONLY_ON_END` | `false` | Only email once a visit ends. |
| `NOTIFICATIONS__EMAIL__USE_OAUTH` | `false` | Use Gmail/Outlook OAuth instead of SMTP. |
| `NOTIFICATIONS__EMAIL__OAUTH_PROVIDER` | _(unset)_ | `gmail` or `outlook`. |
| `NOTIFICATIONS__EMAIL__GMAIL_CLIENT_ID` | _(unset)_ | Gmail OAuth client ID. |
| `NOTIFICATIONS__EMAIL__GMAIL_CLIENT_SECRET` | _(unset)_ | Gmail OAuth client secret. |
| `NOTIFICATIONS__EMAIL__OUTLOOK_CLIENT_ID` | _(unset)_ | Outlook OAuth client ID. |
| `NOTIFICATIONS__EMAIL__OUTLOOK_CLIENT_SECRET` | _(unset)_ | Outlook OAuth client secret. |
| `NOTIFICATIONS__EMAIL__SMTP_HOST` | _(unset)_ | SMTP host. |
| `NOTIFICATIONS__EMAIL__SMTP_PORT` | `587` | SMTP port. |
| `NOTIFICATIONS__EMAIL__SMTP_USERNAME` | _(unset)_ | SMTP username. |
| `NOTIFICATIONS__EMAIL__SMTP_PASSWORD` | _(unset)_ | SMTP password. |
| `NOTIFICATIONS__EMAIL__SMTP_USE_TLS` | `true` | Use STARTTLS. |
| `NOTIFICATIONS__EMAIL__FROM_EMAIL` | _(unset)_ | From address. |
| `NOTIFICATIONS__EMAIL__TO_EMAIL` | _(unset)_ | To address. |
| `NOTIFICATIONS__EMAIL__INCLUDE_SNAPSHOT` | `true` | Attach a snapshot. |
| `NOTIFICATIONS__EMAIL__DASHBOARD_URL` | _(unset)_ | Dashboard link included in emails. |

## Security — Authentication & Public access

| Variable | Default | Description |
| --- | --- | --- |
| `AUTH__ENABLED` | `false` | Require login for owner access. |
| `AUTH__USERNAME` | `admin` | Owner username. |
| `AUTH__PASSWORD_HASH` | _(unset)_ | Pre-hashed owner password. |
| `AUTH__SESSION_SECRET` | _(auto-generated)_ | Session signing secret; set to keep it stable across restarts. |
| `AUTH__OAUTH_TOKEN_SECRET` | _(auto-generated)_ | Encryption key for stored OAuth tokens. |
| `AUTH__SESSION_EXPIRY_HOURS` | `168` | Session lifetime in hours. |
| `AUTH__INITIAL_SETUP_COMPLETE` | `false` | Marks first-run setup as done. |
| `PUBLIC_ACCESS__ENABLED` | `false` | Allow read-only guest access. |
| `PUBLIC_ACCESS__SHOW_CAMERA_NAMES` | `true` | Show camera names to guests. |
| `PUBLIC_ACCESS__SHOW_AI_CONVERSATION` | `false` | Expose the AI chat to guests. |
| `PUBLIC_ACCESS__ALLOW_CLIP_DOWNLOADS` | `false` | Let guests download clips. |
| `PUBLIC_ACCESS__HISTORICAL_DAYS_MODE` | `retention` | `retention` or `fixed` history window for guests. |
| `PUBLIC_ACCESS__SHOW_HISTORICAL_DAYS` | `7` | Guest history window (when `fixed`). |
| `PUBLIC_ACCESS__MEDIA_DAYS_MODE` | `retention` | `retention` or `fixed` media window for guests. |
| `PUBLIC_ACCESS__MEDIA_HISTORICAL_DAYS` | `7` | Guest media window (when `fixed`). |
| `PUBLIC_ACCESS__RATE_LIMIT_PER_MINUTE` | `30` | Per-IP guest request limit. |
| `PUBLIC_ACCESS__EXTERNAL_BASE_URL` | _(unset)_ | Public base URL for guest links. |

## System

| Variable | Default | Description |
| --- | --- | --- |
| `SYSTEM__DEBUG_UI_ENABLED` | `false` | Show the Debug settings tab. |
| `SYSTEM__UPDATE_CHECK_ENABLED` | `true` | Check for new releases. |
| `SYSTEM__TRUSTED_PROXY_HOSTS` | _(built-in list)_ | Comma-separated trusted reverse-proxy hosts. |
| `SYSTEM__BROADCASTER_MAX_QUEUE_SIZE` | `100` | SSE broadcaster queue size. |
| `SYSTEM__BROADCASTER_MAX_CONSECUTIVE_FULL` | `10` | Consecutive full-queue drops before a client is dropped. |

## Telemetry, Accessibility & Appearance

| Variable | Default | Description |
| --- | --- | --- |
| `TELEMETRY__ENABLED` | `false` | Opt in to anonymous usage stats. |
| `TELEMETRY__HEALTH_ENABLED` | `false` | Opt in to anonymous health reports. |
| `TELEMETRY__URL` | _(hosted worker)_ | Heartbeat endpoint. |
| `TELEMETRY__HEALTH_URL` | _(hosted worker)_ | Health-issue endpoint. |
| `TELEMETRY__INSTALLATION_ID` | _(auto)_ | Stable anonymous install ID. |
| `ACCESSIBILITY__HIGH_CONTRAST` | `false` | High-contrast theme. |
| `ACCESSIBILITY__DYSLEXIA_FONT` | `false` | Dyslexia-friendly font. |
| `ACCESSIBILITY__REDUCED_MOTION` | `false` | Reduce animation. |
| `ACCESSIBILITY__ZEN_MODE` | `false` | Minimal "zen" layout. |
| `ACCESSIBILITY__LIVE_ANNOUNCEMENTS` | `true` | Screen-reader live announcements. |
| `APPEARANCE__FONT_THEME` | `classic` | Font theme. |
| `APPEARANCE__COLOR_THEME` | `bluetit` | Colour theme (`default` or `bluetit`). |

---

## UI/file-only settings

These are stored in `config/config.json` (written by the UI) and have **no env
override** — they're per-install data rather than deployment config:

- **Location:** latitude, longitude, auto-detect, weather unit system.
- **Detection tuning:** confidence threshold, minimum-confidence floor, blocked
  species / blocked labels, region override, camera↔audio sensor mapping.
- **Notification filters:** species allow/block lists, per-camera filters,
  minimum confidence, audio-confirmed-only.
- **Bird model region override** and the **active model** selection.

If you need one of these fixed at deploy time, set it once in the UI (it persists
to `config.json`) or open an issue — the env surface above is what the loader
(`backend/app/config_loader.py`) currently reads.
