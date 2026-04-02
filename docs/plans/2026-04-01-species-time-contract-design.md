# Species And Time Contract Alignment Design

## Goal

Reduce second- and third-order regressions from the recent species-normalization and UTC work by aligning downstream contracts with current backend behavior.

## Problems

1. `/api/stats/daily-summary` now represents a rolling 24-hour UTC-naive window, but some consumers still treat it as "today".
2. Home Assistant exposes that rolling count as a monotonic daily total, which is semantically wrong and can confuse recorder/statistics behavior.
3. Daily summary species thumbnails still pick `latest_event` by lexicographic event id instead of latest detection time, which can drift further once multiple labels collapse into one canonical species bucket.
4. Adjacent API surfaces still return mixed timestamp formats (`Z`, `+00:00`, or naive strings), even though the main API model path now normalizes timestamps explicitly.

## Chosen Approach

Use contract alignment rather than introducing a second summary model.

- Keep `/api/stats/daily-summary` as the rolling 24-hour summary.
- Update Home Assistant naming/metadata/state semantics to match that rolling window instead of pretending it is a monotonic "today" counter.
- Fix daily-summary species aggregation so the representative event really comes from the latest detection in the bucket.
- Normalize adjacent non-`APIModel` timestamp responses onto the shared API datetime serializer.

## Why This Approach

- It matches the current backend semantics instead of reintroducing split meanings.
- It avoids another parallel "today" API that would create more drift and maintenance burden.
- It addresses the two real correctness risks from the review: wrong HA entity semantics and wrong species event selection.
- It narrows timestamp inconsistency near the recently changed surfaces without broad refactoring.

## Intended Behavior

### Daily Summary

- The endpoint remains a rolling 24-hour view ending at the current UTC instant.
- Aggregate species cards return a `latest_event` that corresponds to the row with the latest `detection_time` in that species bucket.
- Unknown/species-normalized buckets preserve correct counts while also pointing at the newest underlying event.

### Home Assistant

- The count entity becomes a rolling-window measurement, not a total-increasing counter.
- Entity naming and/or attributes make the 24-hour scope explicit to users and automations.
- Existing latest-event/latest-timestamp behavior remains event-driven and UTC-safe.

### Timestamp Serialization

- Nearby endpoints that currently hand-roll `.isoformat()` responses switch to the same serializer used by the primary API model path.
- Consumers should receive explicit UTC timestamps consistently for these touched surfaces.

## Edge Cases

- Rolling counts naturally decrease as detections age out of the 24-hour window.
- Species buckets containing multiple normalized labels must still choose the newest real event.
- Missing/null timestamps still serialize as `null`.
- Existing clients that parse RFC3339 with either `Z` or `+00:00` should continue to work; the goal is to remove naive timestamps, not broaden accepted input.

## Testing Strategy

1. Add a backend regression test proving daily summary chooses `latest_event` by latest detection time, not max event id.
2. Add/adjust Home Assistant tests to prove the rolling count entity is not modeled as `TOTAL_INCREASING`.
3. Add backend API tests for touched timestamp endpoints to ensure explicit UTC serialization.
4. Re-run the focused backend and UI/HA tests that cover daily summary and sensor behavior.
