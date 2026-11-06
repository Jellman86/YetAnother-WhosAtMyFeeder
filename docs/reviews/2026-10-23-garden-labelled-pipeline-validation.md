# Garden labelled pipeline validation, 23 October 2026

## Decision

Keep the tracked-crop automatic check and its current thresholds. The check can
separate non-bird animals from birds on this small panel, but detector misses and
person false positives remain material limitations. A whole-image classification
must not override person evidence. These results do not justify promoting Garden
out of beta or claiming general accuracy.

## Frozen experiment

Tested the published development revision `e43686dd8827917910bb41c89dca08c0cc431df2`
on one RTX 4070 host through its WSL CUDA image. Accuracy runs explicitly used
`CPUExecutionProvider`; they are not additional CUDA performance qualification.
The immutable image platform digest was
`sha256:05f5eba6b62a3aed06b1b7b0cd72c8fff07d64b7abb8dc4497ef6359e3287f0f`.

The [frozen panel manifest](2026-10-23-garden-labelled-panel.json) contains 84 cases
and 132 images, with source URLs, image hashes, external labels, licences and
attribution. It contains metadata only, so the original photographs can be fetched
and verified without redistributing them in this repository. Selection,
development/holdout splits and the comparison plan were frozen before inference. The frozen panel SHA-256 was
`cf496fccb46916d09d32a8b2baba81853fd111de4f54d4b83a07cf6e1aaea9e3`.

- 48 deterministic [COCO 2017 validation](https://cocodataset.org/#download)
  images, with external boxes. Two bird depictions were identified before testing
  and treated as non-animal hard negatives; one ambiguous costumed scene was
  excluded from scored class comparisons.
- 24 [Wellington Camera Traps](https://lila.science/datasets/wellingtoncameratraps/)
  sequences, eight each labelled bird, non-bird animal and empty. Each complete
  three-image sequence stayed together. Development and holdout locations were
  disjoint. Labels describe the sequence, not necessarily every individual frame.
  The dataset uses CDLA-Permissive-1.0 and cites Anton, Hartley, Geldenhuis and
  Wittmer's urban camera-trap study.
- 12 [SpeciesNet upstream test images](https://github.com/google/cameratrapai/tree/main/test_data)
  were separate sanity checks, not independent holdout evidence. Their upstream
  attribution and CDLA-Permissive licence were retained.

The resulting split was 36 development, 36 holdout and 12 upstream sanity cases.
The one ambiguous case remained in execution coverage but outside scored class
comparisons. Third-party photographs are not redistributed in this repository.
Training overlap is unknown. Convenience samples, COCO indoor scenes and selected
camera locations do not represent a feeder's deployment distribution.

## Actual application path

The packaged Cedar detector processed the complete scene and all three frames of
each Wellington sequence with unchanged thresholds. Any detected person vetoed
collection. Otherwise the highest-scoring animal box selected the image and crop.
No animal box meant no capture; that is different from a stored dismissed photo.

Eligible candidates used the actual `GardenAutomaticReviewService.process_once`,
real native CPU subprocess, model/package validation and private SQLite state.
Only Frigate event/snapshot responses and an explicitly idle private bird queue
and camera-pressure boundary were fixtures. No production images, history,
settings, jobs or credentials were mounted. The still-image panel does not test
motion-change discovery, camera timing, MQTT ingest or video decoding.

For the same selected frame, comparison arms were 4.0.3a on the full scene,
4.0.3a on the actual detector crop, 4.0.3a on the largest externally annotated
relevant box where available, and 4.0.3b with its whole-image preprocessing.
Annotated boxes were diagnostic reference inputs, not a deployed crop strategy.
Naming was disabled for the presence baseline to keep those decisions separate.

All 84 cases completed. There were 39 actual automatic subprocess checks; each
persisted outcome agreed with the same-crop reference arm. Image hashes, exact
boxes and CPU provider bindings matched. SQLite integrity passed, bird detection
history stayed unchanged and owner dismiss/restore overrides survived a later
automatic cycle. The owned container exited zero and was removed.

A retained first attempt stopped before automatic inference because the isolated
harness had no bird-worker status. The application correctly declined admission.
The corrected attempt supplied an explicit idle external queue boundary; it did
not change model thresholds or bypass native model validation.

### Collected Frigate false proposals

A further persistence smoke used all four externally labelled non-animal upstream
sanity images: three empty scenes and one vehicle. Each simulated a Frigate event
mislabelled as animal with a full-frame tracked hint. This box describes the
proposed input, not a ground-truth animal region. The Frigate route does not use
Cedar's collection gate. All four real automatic CPU subprocesses persisted a
non-animal check and moved the capture to Dismissed; bird history and database
integrity passed. The container exited zero and was removed.

These already observed controls verify the second collection route and its
persistence behavior. They are not fresh holdout accuracy data.

## Presence results

| Externally labelled group | Cases | Complete pipeline outcome |
| --- | ---: | --- |
| Non-bird animal | 26 | 25 animal outcomes in Needs review; one detector person veto |
| Bird | 18 | 12 dismissed as bird, one dismissed as non-animal, one uncertain in Needs review, two without an animal box, two detector person vetoes |
| Human, including human plus dog | 14 | All vetoed before collection |
| Non-animal | 25 | 18 without an animal box, seven detector person vetoes |
| Ambiguous | 1 | Person veto; excluded from scored comparisons |

The 26 animal cases include six upstream sanity images. In the externally labelled
COCO and Wellington sources, COCO admitted 11/12 and Wellington admitted 8/8.
The one animal veto was in development. All ten non-bird animal holdout cases were admitted. This small
sample cannot estimate a reliable field miss rate.

Wellington bird sequences were dismissed in all eight cases, seven as bird and
one as non-animal. That final action is appropriate for Garden, but the latter
is still a wrong coarse label and must not be called correct bird recognition.
All eight Wellington empty sequences produced no animal candidate.

## Crop versus whole scene

The paired comparison below includes only cases where Cedar supplied an animal
box. It includes person-vetoed scenes for input research; the application still
honoured the veto. It is a presence comparison, not species-name accuracy.

| Group | Paired cases | 4.0.3a full scene matches | 4.0.3a detector crop matches | 4.0.3b whole image matches |
| --- | ---: | ---: | ---: | ---: |
| Bird | 14 | 5 | 12 | 14 |
| Non-bird animal | 26 | 19 | 26 | 26 |

Cropping clearly helped this panel compared with using the crop model on a full
scene. The whole-image variant did better on these bird cases, but does not
establish superiority on empty scenes, human safety, species names or field data.
A human-plus-dog scene also supplied an animal crop that looked like an animal;
only the full-scene detector veto prevented collection. Crop classification alone
cannot replace full-scene privacy checks.

A visual audit of veto boxes confirmed person false positives on birds, objects
and food. Do not reinterpret a detector person veto as proof that a person was
present, or relax privacy policy using this sample. Real feeder false positives
need a separately labelled evaluation before a detector or threshold change.

## Automatic naming

A separate run enabled automatic naming at the unchanged 0.80 threshold for all
24 Wellington sequences, with the dataset's documented country, New Zealand.
All presence outcomes matched the baseline. Sixteen real automatic subprocesses
ran. Five cat sequences were confirmed and named **domestic cat**, matching the
external sequence labels, with scores from 0.99198 to 0.99994. Each persisted result
was marked automatic and accepted and retained the correct country, crop, model,
package and image identity. A rabbit and two mouse sequences remained in Needs
review without a name. Birds remained dismissed and empty sequences uncollected.
Owner overrides, bird-history isolation, database integrity and clean container
removal passed again.

This qualifies that naming path on those inputs; all five confirmations were
cats, so it is not a broad species-name accuracy result. The rabbit and mouse
cases are not counted as correct names merely because animal presence passed.

## Follow-up and limits

- Extend species-name comparisons against external labels separately from presence. A high
  animal mass is not proof of a correct species name.
- Preserve uncertain cases, owner overrides, country filtering and person vetoes.
  Do not lower thresholds or use holdout results to choose a passing setting.
- Collect a larger independently labelled, deployment-relevant panel before
  changing the default model or privacy gate. Include people with animals, tiny
  birds, night scenes, depictions, empty scenes and duplicate animal parts.
- Fresh independent two-bird counting and duplicate-part labels for #734 remain
  outstanding. This presence panel does not qualify counting.
- Neither the original affected-host Intel slowdown in #778 nor #490's original
  fault or live concurrency is reproduced by these tests.
- The sequential 2-CPU, 6-GiB diagnostic has no sustained-load, native-Windows,
  general-hardware, camera-ingest or production-concurrency claim.
