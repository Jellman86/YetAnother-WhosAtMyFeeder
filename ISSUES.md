# Issues (Known Gaps)

This document tracks known issues and testing gaps that have not been verified end-to-end by the maintainer.

If you find a bug, please open a GitHub issue with the steps to reproduce and any redacted logs.

Last reviewed against the GitHub issue tracker on **August 19, 2026**.

## P0: Active Regressions

- None currently confirmed as unresolved in current `dev`.

## Pending Verification (Fixes in Dev, Awaiting Reporter Confirmation)

- **#167 Video will not play in Safari:** the likely cause is HEVC packaged as `hev1`, which Safari's
  video element refuses while QuickTime plays it, so "the download opens fine" does not clear it.
  Diagnostics bundles now report the sample format of a recent clip, and there is a troubleshooting
  page at `docs/troubleshooting/safari-video-playback.md`. Waiting on a bundle from the reporter.

## Known Remaining Exposure

- **Six read paths still resolve species names under a held database connection.** The fix for
  #300/#301 removed the connection holds around Frigate, weather, AI and inference work, and around
  the species filter's name resolution. These six remain, and each resolves a localized common name
  inside a loop that also reads from the database, so the split is a refactor rather than a
  rearrangement:
  `events.py` events list (680-902), `species.py` (859-970, 1002-1093, 1108-1320), `stats.py`
  (291-424), `ebird.py` (265-478), and `detection_service.py` (631-908).

  The cost only lands on a cache miss: a species not yet in `taxonomy_translations` for the
  requested language costs one iNaturalist request with a ten-second timeout. A steady-state install
  is unaffected; a fresh install, or the first load after switching language, is not. When it
  happens the pool now logs `Slow DB connection hold` naming the handler, `db_pool.hold_ms_max`
  rises, and health reports `degraded`, so it is visible rather than silent.

  The durable fix is for a render path never to block on a third-party API: resolve names from
  cache only and enrich in the background. That is a behaviour change (a new species' localized name
  would appear on the next load) and is a maintainer decision, not a mechanical one.

## Open on the Tracker

- **#178** Dedicated media retention rotation and favourite protection. Accepted; the durability
  contract is recorded in `ROADMAP.md` and the stronger behaviour is planned, not shipped.

## Recently Closed (Context)

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
