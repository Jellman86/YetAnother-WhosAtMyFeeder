# Garden acceptance audit, 26 October 2026

The collection, automatic naming, grouped visits and saved-crop paths are present
in `dev` at `460a906`. This audit checks their connections and owner/privacy
boundaries. It does not establish field accuracy or complete hardware qualification
for [#641](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues/641).

## Reproduced gap and correction

The open Explorer already consumes a private `garden_history_changed` signal.
Automatic results and saved-crop collection emitted it, but initial Frigate and
motion collection did not. Frigate revocations also changed durable history
without notifying the open view. When automatic work was waiting, a new capture
could remain invisible until a refresh; an already open revoked record could stay
on screen even though further API/media reads were denied.

Six new regression cases failed against the original tree: new Frigate capture,
four Frigate rejection/relabel paths, and motion collection. The fix sends the
existing signal after a committed visible history change, outside the database
connection and privacy lock. Repository write results distinguish new changes
from duplicate deliveries and private tombstones with no visible capture. No
capture identifiers, labels, camera names or image URLs enter the signal.

## Acceptance coverage

These tests use disposable migrated databases, generated photographs and mocked
external-service/native-inference boundaries. They do not run production models,
send notifications or modify live settings/history.

| Path | Evidence |
| --- | --- |
| Frigate capture, duplicate deliveries and later person/false-positive/bird/disabled-label revocation | `test_garden_capture_history.py`: committed history is readable when the signal arrives; duplicate messages cause no further refresh. |
| Motion capture reaches the Explorer before identification | `test_garden_motion_service.py`: committed photo is visible and the privacy lock is released when notified. |
| Two named captures form one visit with real crop bytes | `test_garden_automatic_review.py`: generated JPEGs pass the automatic service, catalogue binding, repository naming/crop transaction and server grouping together. |
| Restart and original-photo expiry | The combined acceptance test reopens the database and automatic service, preserves both visit members and saved crops after expiry, and performs no repeated identification. |
| Owner dismissal | The combined test removes only the dismissed capture's crop; the other crop survives and automatic work does not undo the decision. Bird history is unchanged. |
| Person update after restart with Garden disabled | `test_garden_saved_crops.py`: rebuilt history state admits privacy cleanup, removes the saved crop, then notifies the open view once, outside the privacy lock. |
| Guest boundary | Existing `test_guest_privacy_review.py` verifies Garden update signals are not delivered to guest streams. Owner-only capture/crop API coverage remains in the focused suite. |

This is deterministic application-path evidence. The combined automatic test uses
fixed native outputs, so it proves persistence and policy behavior rather than
species accuracy, accelerator execution or camera recall.

## Next evidence

- The [bounded native sampling comparison](2026-10-27-garden-motion-sampling.md)
  now covers the externally tagged brief-animal example. Nine samples recover a
  proposal at the separate 0.5 diagnostic threshold, but neither policy produces
  a candidate at Quark's 0.63 setting. Original recordings with independent animal,
  person, fixture and weather labels are still needed. Keep bird priority, person
  vetoes and existing thresholds; finding an animal is separate from naming it.
- Extend deployment-relevant daytime/IR and hard-negative labels. The
  [frozen panel](2026-10-23-garden-labelled-pipeline-validation.md) remains a small
  selected sample, not a general field-accuracy estimate.
- Independent two-bird/duplicate-part validation in
  [#734](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues/734) and CUDA
  qualification remain separate from this Garden acceptance slice.
- Quark's RF-DETR GPU hang reproduction remains deferred until Garden parity work
  is complete. No GPU replay, device sweep or quarantine reset is part of this audit.
