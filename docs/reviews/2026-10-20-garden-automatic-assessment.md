# Automatic Garden candidate assessment

## Behaviour

New Garden candidates previously waited for an owner to press Check photo.
The collector now runs SpeciesNet 4.0.3a on the exact detector crop automatically,
including Frigate event snapshots that have a valid representative snapshot box.
It downloads and checksum-verifies the model when needed. No new setting or
automatic species confirmation is added. Garden remains off by default.

The complete ordered 2,498-output mapping partitions probability mass into
non-human/non-bird animals, birds, humans, blank/vehicle and unresolved outputs.
At least 0.8 bird or blank/vehicle mass dismisses a capture; at least 0.8 animal
mass keeps it for presence review. Everything else stays uncertain. Unknown
outputs are never renormalized away or interpreted as empty. These fixed cutoffs
are decision rules, not measured probabilities of correctness. Human evidence
uses the existing winner/0.1 privacy veto and removes the media.

Dismissal is soft. The result and model, package, photo, crop and device evidence
remain visible privately, with Return to review available while the photo exists.
An owner action sets a durable override, including a dismiss/restore cycle, so
later checks cannot undo it. Existing captures are preserved during migration;
only newly collected captures enter automatic assessment. Duplicate event or
recording delivery does not reset an assessment or owner override.

## Crop comparison

Before choosing the automatic input path, a paired CPU comparison used 115
distinct retained photos, with the exact same inputs for each model. Visual
inspection of full photos and saved detector crops labelled 8 mammal photos,
35 bird photos and 72 fixture/no-visible-non-bird-animal photos before opening
model results. Owner review states were retained separately: dismissal alone
was not treated as proof that a photo lacked an animal.

The 0.8 cutoff was fixed before inference. All 345 forwards completed with finite
outputs using the verified released weights and packaged preprocessing/mapping.

| Input | Mammals suggested / uncertain / rejected | Fixture negatives dismissed | Bird photos dismissed |
| --- | --- | --- | --- |
| 4.0.3a, exact detector crop | 7 / 1 / 0 | 55 of 72 | 30 of 35 |
| 4.0.3b, whole image with upstream trim | 6 / 1 / 1 | 42 of 72 | 27 of 35 |
| 4.0.3a, uncropped experimental control | 0 / 1 / 7 | 72 of 72 | 35 of 35 |

The whole-image variant also triggered person evidence on two fixture negatives;
these are separate from its 42 blank/vehicle dismissals. One bird crop was called
blank, so dismissal counts must not be read as correct species classification.
Median warm CPU forward times were about 294 ms for each path. Loading a fresh
worker and model, downloads, image handling and queue waits are additional costs.

The crop path retained all eight mammal examples for review, including an
uncertain squirrel that the whole-image model rejected. Automatic rejection
therefore requires a valid tracked crop; missing boxes stay pending rather than
using a whole-image fallback. The uncropped 4.0.3a control is not promoted.

These are correlated, owner-selected local regression controls from one camera,
including repeated daytime dog/squirrel visits and nighttime fixture proposals.
They do not establish independent visit accuracy, infrared mammal recall, mixed
scene safety, person recall or performance on other cameras. The prior confident
toy-car/cattle error remains relevant: a second classifier cannot prove presence
or absence. Keep [#641](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues/641)
open for those remaining qualifications. No production review or settings changed
to obtain this comparison. Private images and raw evidence stay outside Git.

## Capacity, races and rollback

- One automatic check runs at a time, sharing the existing Garden admission slot.
  The worker is disposable CPU inference, with the existing two-minute deadline,
  cancellation/reaping and cleanup-failure quarantine. It yields to bird work,
  disabled cameras, privacy updates and camera pressure. No GPU/NPU route or bird
  threshold changes. Repeated model loads can slow collection and allow recording
  windows to age out under sustained load; this is not a capacity qualification.
- Each cycle selects one available pending photo. Successful checks persist once;
  unavailable checks stay pending and retry no sooner than five minutes later.
  New checks precede retries. No per-capture task or unbounded in-memory queue is
  created. Models use about 224 MB disk space; one model/worker is active at a time.
- The result is checked against the current source photo, catalogue, privacy and
  owner-review generation before saving. A database compare-and-set checks both
  the previous assessment and durable owner override. Changing, restoring or
  revoking a photo during inference cannot apply a stale automatic dismissal.
- Automatically dismissed photos use existing three-day expiry and bounded photo
  reclamation. They can be reclaimed before a person reviews them; restoration
  after photo expiry/reclamation is unavailable. Confirmed history is preserved.
- The idempotent migration adds one override column and a child evidence table.
  Downgrade returns untouched automatic dismissals to pending and drops only
  automatic evidence/override metadata. Owner reviews and capture photos remain.
  Privacy tombstones remain blocked. Disable Garden to stop collection and checks
  immediately; saved history remains under the existing retention rules.

The maintained [Garden guide](../features/garden-animals.md) describes operation;
[the API reference](../api.md#garden-animal-review) describes private evidence.
