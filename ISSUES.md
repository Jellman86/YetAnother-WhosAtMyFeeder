# Issues (Known Gaps)

This document tracks known issues and testing gaps that have not been verified end-to-end by the maintainer.

If you find a bug, please open a GitHub issue with the steps to reproduce and any redacted logs.

Last reviewed against the GitHub issue tracker on **September 7, 2026**.

## P0: Active Regressions

- None currently confirmed as unresolved in current `dev`.

## Pending Verification (Fixes in Dev, Awaiting Reporter Confirmation)

- **#300 Slowing interface:** reopened after the reporter found Settings still slow on a build
  that predates every 2.19.3 pool fix. Two causes have been found and fixed. The name lookups and
  Frigate calls that held a pooled connection shipped in 2.19.3 (#391, #392, #393, #395, #396).
  The remaining one is the media cache statistics walk: `GET /api/cache/stats` stat'ed every cached
  file on the event loop, and the owner system checks call it once a minute from every owner page,
  so on a slow or network-backed filesystem the whole API stalled for the length of the walk. The
  reporter's bundles carry 168 client-side timeouts on that request. The walk now runs on a worker
  thread and logs itself when it exceeds a second (PR #401). Waiting on a fresh bundle from a
  release that contains both.
- **#167 Video will not play in Safari:** the likely cause is HEVC packaged as `hev1`, which Safari's
  video element refuses while QuickTime plays it, so "the download opens fine" does not clear it.
  Diagnostics bundles now report the sample format of a recent clip, and there is a troubleshooting
  page at `docs/troubleshooting/safari-video-playback.md`. Waiting on a bundle from the reporter.

## Known Remaining Exposure

- **The owner system checks walk the media cache once a minute.** With PR #401 the walk no longer
  blocks the API, but it still runs every sixty seconds on every owner page, and on a large cache
  over a slow mount that is sustained disk work for a number nobody is looking at. Caching the
  result for a few minutes, or updating counts as files are written and removed, is the durable
  fix and a design decision rather than a mechanical one.
- **Reported cache sizes undercount.** `get_cache_stats` counts `*.jpg` and `*.mp4` only, so the
  `.meta.json` sidecars beside every snapshot are not in the total. On the reference install that
  is 14,712 uncounted files.
- **API process memory is being watched again.** #314 closed at about 340 MB resident after the
  `MALLOC_ARENA_MAX=2` fix. On the reference install the API process measured 1.49 GB resident
  fourteen hours after a start in subprocess mode, where it holds no model. The RSS sampler is
  running again; if the growth continues, #314 reopens with the numbers.

## Open on the Tracker

- **#300** Slowing interface. See Pending Verification above.
- **#256** Snapshot selection and classification overhaul. The two bug halves shipped (the delete
  control names its effect; species information is stated once). What remains is unifying frame
  choice and identification into one flow, which is a design decision and now has a roadmap entry.
- **#178** Dedicated media retention rotation and favourite protection. Accepted; the durability
  contract is recorded in `ROADMAP.md` and the stronger behaviour is planned, not shipped.

## Recently Closed (Context)

- **Owner media URLs no longer carry the session token.** NPM in front of the reference install logs
  full request URIs; its access log held 482 owner thumbnail and clip URLs with `?token=` on
  September 8. Media now authenticates with an `HttpOnly`, `SameSite=Lax` session cookie that only
  read-only media routes and the stream honour. The tokens already in that log stay valid until they
  expire or the session secret is rotated; the proxy's log format is being changed to drop the query.
- **The owner's SSE token no longer reaches nginx's error log.** The live stream opens with a
  single-use, 60-second ticket from `POST /api/auth/stream-ticket`, and `/api/sse` refuses the
  session token in its query string. The three lines nginx wrote on the September 8 restart carried
  a valid owner token; the same lines now carry a spent ticket.
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
- Verification evidence: `tests/e2e/test_video_player.py` passes in the current dev workspace.
