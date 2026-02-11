# Issues (Known Gaps)

This document tracks known issues and testing gaps that have not been verified end-to-end by the maintainer.

If you find a bug, please open a GitHub issue with the steps to reproduce and any redacted logs.

## P0: Active Regression - Video Player Can Stall/Hang UI

### Summary
- Status: Open, high impact.
- Affected branch/builds observed: `dev` (`2.7.9-dev+78e0bab` through `2.7.9-dev+d90acc6`).
- User-facing symptom: clicking `Play video` can leave modal in `Preparing player...` state and, in some sessions, cause full browser tab lock/crash.

### Reproduction (Current)
1. Open Events page.
2. Open a detection that has a clip.
3. Click `Play video`.
4. Observe modal startup behavior.

### Observed Behavior
- In failing runs, the video modal opens but player UI is inconsistent:
  - `.plyr` may fail to appear, or appears without visible `.plyr__controls`.
  - `Video Unavailable` / `Clip Fetching Disabled` is not shown in these cases.
  - Timeline status text can still show `Timeline previews enabled`.
- Browser console repeatedly logs:
  - `Failed to load initial detections AbortError: signal is aborted without reason`
  - Stack in bundle (example): `index-*.js:11:6876`, `11:7926`, `61:3474`, `61:4458`.
- Backend/frontend networking for the clip path is healthy during failures:
  - `HEAD /api/frigate/<event>/clip.mp4 -> 200`
  - `GET /api/frigate/<event>/clip.mp4 -> 200`
  - `GET /api/frigate/<event>/clip-thumbnails.vtt -> 200`

### Test Evidence
- `tests/e2e/test_video_player.py` still fails on current `dev` despite multiple fixes.
- Latest failure mode:
  - `.plyr` visibility may pass in some runs.
  - `.plyr__controls` visibility times out (`Timeout 8000ms exceeded`).
- Local ad-hoc Playwright probes confirm modal opens but player controls do not reliably initialize.

### Mitigations Already Landed (Not Sufficient Yet)
- `34901e2`: removed self-triggering watchdog reactive state loop.
- `a71a5e2`: added probe timeout + bound video element gating.
- `78e0bab`: switched preview probing to non-blocking player startup.
- `2c8999c`: added configure idempotency key to prevent repeated reconfiguration.
- `d90acc6`: added try/catch + init watchdog fail-safe to avoid infinite startup pending state.

### Likely Fault Domain
- Frontend runtime/reactivity interaction during modal + player initialization (Svelte state/effect flow and/or player init lifecycle), not media fetch availability.
- Separate abort-path console error on Events loading may be contributing noise or side effects and needs source-level tracing.

### Next Steps
- Add source-mapped diagnostics for production bundle errors in UI build to map `index-*.js` offsets back to source quickly.
- Instrument `VideoPlayer.svelte` lifecycle transitions with a stable state machine log (`created`, `probed`, `plyr-init`, `ready`, `failed`).
- Temporarily add a guarded native `<video controls>` fallback mode (bypass Plyr) to confirm UI hangs are player-init related.
- Expand E2E to assert no unhandled page errors during `Play video` flow before control visibility assertions.

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
