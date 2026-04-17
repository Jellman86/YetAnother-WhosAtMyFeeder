# Issues (Known Gaps)

This document tracks known issues and testing gaps that have not been verified end-to-end by the maintainer.

If you find a bug, please open a GitHub issue with the steps to reproduce and any redacted logs.

Last reviewed against the GitHub issue tracker on **April 17, 2026**.

## P0: Active Regressions

- None currently confirmed as unresolved in current `dev`.

## Pending Verification (Fixes in Dev, Awaiting Reporter Confirmation)

- **BirdNET-Go source-name drift / `Unknown sensor` fallback:** Some newer BirdNET-Go MQTT payloads appear to omit the stable source-name fields (`nm` / `Source.displayName`) and only publish `sourceId`/`src`. `dev` now falls back to those ID-style fields so Recent Audio and the source picker no longer show `Unknown sensor`, but stable long-term camera mapping still depends on BirdNET-Go exposing a stable published source/display name again. Upstream feature request: `tphakala/birdnet-go#2799`.

## Recently Closed (Context)

- **#21** OpenVINO load fails for ConvNeXt - closed after the patched artifact / redownload remediation path shipped.
- **#19** Incorrect filter application / stale Explorer state - follow-up fixes merged and issue closed on **February 27, 2026**.
- **#16** No audio detection mapped - original stable-name mapping fix landed and the issue was closed, but newer BirdNET-Go payload drift is now tracked above under Pending Verification.

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
  - CUDA host/runtime detection correctly reports availability only when an NVIDIA GPU is present
  - ONNX model activation succeeds with `cuda` provider and remains stable across backend restart
  - Live detections and manual/background reclassification flows execute on CUDA without unexpected fallback loops
  - Failure paths surface clear diagnostics in Settings and backend logs

## Notes

- Resolved/closed investigation notes live in `CHANGELOG.md`.
- Open GitHub issues are the source of truth for active bug state; this file is a maintainer triage summary.
- Verification evidence: `tests/e2e/test_video_player.py` passes in the current dev workspace.
