# Derived Notification Timeout Design

## Goal

Keep notification waiting behavior aligned with the real video-classification pipeline so `delay_until_video` does not silently time out before video analysis can possibly complete.

## Approach

When delayed notifications are enabled, YA-WAMF should derive the effective wait from the configured video pipeline instead of trusting a manually entered timeout alone.

The derived minimum should include:
- `classification.video_classification_delay`
- the full clip polling backoff budget from `video_classification_max_retries` and `video_classification_retry_interval`
- a small fixed safety buffer for DB updates and dispatch jitter

`notifications.video_fallback_timeout` should remain as an optional manual override, but only as a larger value. It should never shorten the effective wait below the derived minimum.

## Scope

- Backend notification orchestration
- Targeted backend tests
- Settings copy/UI to explain the behavior accurately

## Non-Goals

- Reworking notification confidence filters
- Reworking SMTP/Discord delivery
- Changing the video-classification retry algorithm itself
