# Notification Timeout Runtime Hardening Design

## Goal

Prevent delayed notifications from timing out before video classification has a realistic chance to finish by including video runtime in the derived wait floor.

## Approach

The current derived timeout already includes the configured clip-finalization delay and clip polling backoff. It should also include the configured video-classification runtime budget so the notification waiter cannot expire before the classifier itself reaches its own timeout.

The effective minimum should therefore include:
- `classification.video_classification_delay`
- clip polling backoff derived from `video_classification_max_retries` and `video_classification_retry_interval`
- `classification.video_classification_timeout_seconds`
- a small fixed safety buffer

`notifications.video_fallback_timeout` remains only a larger override.

## Scope

- Backend notification timeout helper
- Targeted backend tests

## Non-Goals

- Modeling arbitrary queue congestion
- Reworking video-classification scheduling
- Changing frontend copy again unless needed
