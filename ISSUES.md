# Issues (Known Gaps)

This document tracks known issues and testing gaps that have not been verified end-to-end by the maintainer.

If you find a bug, please open a GitHub issue with the steps to reproduce and any redacted logs.

Last reviewed against the GitHub issue tracker and opt-in fleet telemetry on
**September 15, 2026**.

## P0: Active Regressions

- None currently confirmed as unresolved in current `dev`.

## P1: Active Regressions

### REG-2026-09-15-01 — Accepted detections can expire before notification dispatch

- **State:** unresolved in current `dev`.
- **Evidence:** the September 15 fleet review found 41 underlying occurrences across two
  installations in the preceding 30 days, including one occurrence from the current `dev` build.
  Each failure emits both `stage_timeout/save_and_notify` and
  `drop_save_and_notify_failed`; those 82 raw markers describe 41 failures and must not be counted
  as separate incidents.
- **Impact:** one six-second deadline currently covers the database upsert, optional Frigate
  sublabel write, snapshot caching, video-classification scheduling and notification enqueue. A
  timeout can therefore cancel an otherwise accepted detection before notification work becomes
  durable, either losing the detection or leaving a saved detection without its notification.
- **Roadmap:** [telemetry-confirmed regression queue](ROADMAP.md#telemetry-confirmed-regression-queue).
- **Complete when:** the accepted detection is durably committed before optional remote and media
  work, notification delivery is independently recoverable, and a regression test proves slow
  optional work cannot turn a committed detection into `save_and_notify_failed`.

### REG-2026-09-15-02 — Legacy health batches disappear from telemetry breakdowns

- **State:** unresolved in the telemetry worker on current `dev`.
- **Evidence:** legacy v1 batches retain aggregate `critical_count` and related count columns but
  have no `event_groups_json`. The public severity, component and top-issue queries only expand
  `event_groups_json`, so those batches contribute to headline totals while disappearing from the
  breakdown. The fleet review found a still-active legacy client reporting a cumulative
  `classify_snapshot` critical; repeated daily cumulative reports must not be presented as new
  failures.
- **Impact:** operators can read a clean or incomplete breakdown while older enabled clients are
  still reporting critical health in an otherwise publishable cohort, which makes release-health
  assessment unreliable.
- **Roadmap:** [telemetry-confirmed regression queue](ROADMAP.md#telemetry-confirmed-regression-queue).
- **Complete when:** mixed-schema aggregates preserve legacy severities without inventing missing
  fingerprints or violating the public cohort threshold, cumulative reports are labelled or
  deduplicated honestly, and integration tests cover a mixed v1/v3 reporting window.

## Pending Verification (Fixes in Dev, Awaiting Reporter Confirmation)

- **REG-2026-09-15-03 — final-mode detection notifications:** stable `2.20.1` can save a final
  Frigate event without dispatching its notification because the terminal path treated the earlier
  preliminary classification as unchanged. PR #467 makes the terminal decision authoritative in
  `dev`, but the reference install has not yet produced a qualifying accepted detection since that
  build was deployed. Keep this open until Telegram and the in-app notification timeline both
  prove one real final-mode detection end to end. Tracked in the
  [telemetry-confirmed regression queue](ROADMAP.md#telemetry-confirmed-regression-queue).

- **#451 Frigate clips stop after their first chunk:** the media-cookie security change made the
  browser stop carrying the owner token in video URLs, but the rate limiter still recognised only
  bearer/query tokens and the legacy API key. It therefore counted a signed-in owner's clip probes
  and browser range requests against the public budget, eventually answering 429. Current `dev`
  recognises a valid owner cookie for rate limiting only on the read-only media routes where that
  cookie is already allowed. Awaiting a release and reporter confirmation.

## Known Remaining Exposure

- **The owner system checks walk the media cache once a minute.** With PR #401 the walk no longer
  blocks the API, but it still runs every sixty seconds on every owner page, and on a large cache
  over a slow mount that is sustained disk work for a number nobody is looking at. Caching the
  result for a few minutes, or updating counts as files are written and removed, is the durable
  fix and a design decision rather than a mechanical one.
- **Reported cache sizes undercount.** `get_cache_stats` counts `*.jpg` and `*.mp4` only, so the
  `.meta.json` sidecars beside every snapshot are not in the total. On the reference install that
  is 14,712 uncounted files.
- **The CUDA and amd64 `full` images stay on ONNX Runtime 1.26.** 1.27 and later ship CUDA 13
  userspace, which needs the NVIDIA 580 driver series on the host, so the bump Dependabot proposed
  in #284 was closed and the window is held until 3.0 (`ROADMAP.md`, 1.7). Those images therefore
  lack the input-validation hardening 1.29 added to several CUDA kernels. Exposure is limited: the
  runtime only loads models the owner installed, never user-supplied files.
- **API process memory is being watched again.** #314 closed at about 340 MB resident after the
  `MALLOC_ARENA_MAX=2` fix. On the reference install the API process measured 1.49 GB resident
  fourteen hours after a start in subprocess mode, where it holds no model. The RSS sampler is
  running again; if the growth continues, #314 reopens with the numbers.

## Open on the Tracker

- **#451** Frigate clips stop after their first chunk. See Pending Verification above.

## Recently Closed (Context)

- **#178** Durable favourite media and per-species retention floors shipped in 2.20.0 (#445).
  Favourites now acquire their photograph and available clip into `/config/archive`; cache cleanup
  and Frigate rotation do not touch that archive, and acquisition failures and destructive actions
  are explicit.
- **#437** Release images could inherit the wrong channel label when concurrent main, tag and dev
  builds promoted the same working tag. The promotion paths were separated in 2.19.6, the footer
  now links to the running build's branch, and the reporter confirmed the fix.
- **#300** Settings stalls from media-cache statistics walking every file on the event loop were
  fixed by moving that walk to a worker thread (#401); closed September 8.
- **#256** Snapshot choice and identification now share one record flow with one frame strip and
  plain-language actions; shipped in 2.20.0 and closed September 12.
- **#432** "YA-WAMF was updated while this tab was open" on every load of a stable image; the bundle
  kept the `-stable` label in its version string and the backend did not, so the deploy-recovery
  check saw two deployments. Fixed in dev on 10 September (#433) and shipped in 2.19.5.
- **#414** Clickable link in notifications; shipped in 2.19.4 (#417, #422, #423), closed with the
  2.19.5 release.
- **Owner media URLs no longer carry the session token.** NPM in front of the reference install logs
  full request URIs; its access log held 482 owner thumbnail and clip URLs with `?token=` on
  September 8. Media now authenticates with an `HttpOnly`, `SameSite=Lax` session cookie that only
  read-only media routes and the stream honour. The session secret on the reference install was
  rotated on September 8, so every token that log holds is dead. Dropping the query from the proxy's
  log format was tried the same day and reverted: NPM only reads its bundled format from its vendor
  config tree, and mounting over that file broke its startup. The access log keeps its normal rotation.
- **The owner's SSE token no longer reaches nginx's error log.** The live stream opens with a
  single-use, 60-second ticket from `POST /api/auth/stream-ticket`, and `/api/sse` refuses the
  session token in its query string. The three lines nginx wrote on the September 8 restart carried
  a valid owner token; the same lines now carry a spent ticket.
- **#167** Video would not play in Safari; closed August 31 after the reporter confirmed playback.
  Diagnostics bundles report a recent clip's sample format, and
  `docs/troubleshooting/safari-video-playback.md` stays for the next report.
- **#392** Audio routes held a pooled connection while naming species over the network; closed
  September 3, 2026, with the lookup itself now refusing the network while a connection is held.
- **#386** Leaderboard duplicates from split identities and hand corrections; closed September 4.
- **#375** Delete a detection from the "needs your call" queue; closed September 4.
- **#365** Explorer not filtering; **#360** a post-classification write clobbered a healed
  `species_id`; both closed September 1.
- **#314** Resident memory grew to 4.8 GiB; closed August 31 with `MALLOC_ARENA_MAX=2` and clips
  streamed to disk (#341). Being watched, see above.
- **#313** Hardware probes ran on the event loop and stalled every request; **#312** inference no
  longer shares a process with the web service by default; both closed August 31.
- **#305** The 49 open CodeQL alerts triaged; closed August 31.
- **#207** eBird localization - distances now follow the chosen unit system; closed August 17, 2026.
- **#189** Mobile UI overlap on manual tagging - fixed and confirmed by the reporter; closed
  August 15, 2026.
- **#21** OpenVINO load fails for ConvNeXt - closed after the patched artifact / redownload remediation path shipped.
- **#19** Incorrect filter application / stale Explorer state - follow-up fixes merged and issue closed on **February 27, 2026**.
- **#16** No audio detection mapped - the stable-name mapping fix landed and the issue was closed.
  The later BirdNET-Go payload drift is also resolved: upstream `tphakala/birdnet-go#2799` shipped a
  stable `sourceName` field on May 1, 2026, and `dev` reads it with the older fields as fallback.

## P1: Untested Integrations (Need Community Testing)

Some integrations are implemented but have not been validated end-to-end (no accounts/credentials available for real-world verification).

For a step-by-step checklist, see `INTEGRATION_TESTING.md`.

### Email Notifications via OAuth2 (Gmail/Outlook)
- Scope: OAuth connect flow + sending mail via XOAUTH2 SMTP + refresh tokens.
- Code: `backend/app/routers/email.py`, `backend/app/services/smtp_service.py`, `backend/app/services/notification_service.py`
- Needs testing:
  - OAuth authorize + callback completes and stores token
  - Token refresh works when expired
  - Sending a test email succeeds (with and without snapshot attachment)

### Telegram Notifications (Real Bot API)
- Scope: Real bot token + chat ID, snapshot/no-snapshot paths, HTML escaping, error handling.
- Code: `backend/app/services/notification_service.py`, Settings test endpoint `backend/app/routers/settings.py`
- Needs testing:
  - Settings "Send Test Notification" succeeds against the real Telegram Bot API
  - Snapshot attachment path works reliably
  - Special characters in species/camera names render correctly (no formatting injection)

### Pushover Notifications (Real API)
- Scope: Real user key + API token, snapshot/no-snapshot paths, error handling.
- Code: `backend/app/services/notification_service.py`, Settings test endpoint `backend/app/routers/settings.py`
- Needs testing:
  - Settings "Send Test Notification" succeeds against the real Pushover API
  - Snapshot attachment path works reliably
  - Invalid credentials or rate-limit responses surface clear UI/backend errors

### iNaturalist Submissions (OAuth + Draft/Submit Flow)
- Scope: OAuth connect flow + creating/submitting observations from a detection.
- Code: `backend/app/routers/inaturalist.py`, `backend/app/services/inaturalist_service.py`, UI panel: `apps/ui/src/lib/components/DetectionModal.svelte`
- Needs testing:
  - OAuth authorize + callback completes and stores token
  - "Draft" loads correctly for a detection
  - Submitting an observation succeeds (or fails with a clear UI error)

### NVIDIA CUDA Inference Provider (Real GPU Validation)
- Scope: End-to-end CUDA provider behavior for ONNX models on real NVIDIA hardware.
- Code: `backend/app/services/classifier.py`, `backend/app/services/model_manager.py`, `apps/ui/src/lib/components/settings/DetectionSettings.svelte`, `apps/ui/src/lib/pages/models/ModelManager.svelte`
- Needs testing:
  - The full and `-cuda` images report CUDA as packaged; CPU/Intel image mismatch diagnostics remain clear and non-destructive
  - CUDA host/runtime detection correctly reports availability only when an NVIDIA GPU is present
  - ONNX model activation succeeds with `cuda` provider and remains stable across backend restart
  - Live detections and manual/background reclassification flows execute on CUDA without unexpected fallback loops
  - Failure paths surface clear diagnostics in Settings and backend logs

## Notes

- Resolved/closed investigation notes live in `CHANGELOG.md`.
- Open GitHub issues are the source of truth for active bug state; this file is a maintainer triage summary.
