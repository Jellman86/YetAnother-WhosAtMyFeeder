# Issues (Known Gaps)

This document tracks known issues and testing gaps that have not been verified end-to-end by the maintainer.

If you find a bug, please open a GitHub issue with the steps to reproduce and any redacted logs.

Last reviewed against the GitHub issue tracker on **February 27, 2026**.

## P0: Active Regressions

- None currently confirmed as unresolved in current `dev`.

## Pending Verification (Fixes in Dev, Awaiting Reporter Confirmation)

### GitHub Issue #21: OpenVINO load fails for ConvNeXt
- Issue: `https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues/21`
- Status (as of February 27, 2026): Open, remediation shipped on `dev`, awaiting reporter retest with model re-download.
- Implemented fixes on `dev`:
  - `4cbd61f` (`patch_convnext_openvino_model.py` utility for unsupported ONNX sequence ops)
  - `e2eaeea` (safe model re-download with in-UI progress and staged replace/rollback)
  - `08eb353`, `4f44b15` (host-verified dynamic capability pills and duplicate-label cleanup)
- Current understanding:
  - The prior ConvNeXt model artifact could fail OpenVINO compile (`SequenceEmpty`/`SequenceInsert`/`ConcatFromSequence`) on affected runtimes.
  - `dev` now provides a patched model path plus guided re-download flow to replace stale local artifacts safely.
  - The issue remains open until reporter confirms successful OpenVINO activation after re-download.

### GitHub Issue #16: No audio detection mapped
- Issue: `https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues/16`
- Status (as of February 26, 2026): Open, behavior improved on `dev` and awaiting longer-running user confirmation.
- Current understanding:
  - Initial multilingual/common-name correlation fixes improved audio correlation behavior.
  - BirdNET-Go source ID drift (`src`) after restart caused mappings to break over time.
  - `dev` now uses BirdNET source name (`nm`) mapping and exposes recent BirdNET source names in Settings to make mapping easier.
- Reporter feedback so far:
  - Dashboard audio figures are now appearing.
  - Reporter still needs to confirm the count continues increasing reliably after restart/runtime.

## Recently Closed (Context)

- **#19** Incorrect filter application / stale Explorer state - follow-up fixes merged and issue closed on **February 27, 2026**.
- **#20** Weather conditions panel text alignment - reporter confirmed fix; closed on **February 26, 2026**.
- **#17** Batch reclassify issue - remaining symptom moved to `#19`; closed on **February 26, 2026**.
- **#13** Wrong Wikipedia reference (RU localization) - closed on **February 19, 2026** after validation.

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

## Notes

- Resolved/closed investigation notes live in `CHANGELOG.md`.
- Open GitHub issues are the source of truth for active bug state; this file is a maintainer triage summary.
- Resolved on February 12, 2026: video player modal stall/hang regression in `Events` flow.
- Resolved on February 12, 2026: video playback-state badge now tracks active playback correctly and no longer sticks on `Paused`.
- Resolved on February 12, 2026: timeline preview VTT cues now use path-based sprite URLs for reverse-proxy compatibility.
- Resolved on February 12, 2026: owner share-link lifecycle tooling now supports in-app list/update/revoke management, create-rate limiting, and scheduled stale-link cleanup.
- Verification evidence: `tests/e2e/test_video_player.py` passes in the current dev workspace.
