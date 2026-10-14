# Garden integration handover: 14 October 2026

## Resumed investigation

The owner subsequently requested continuation. Their screenshot reproduced a
grouping defect: feeder proposals at the same position had different box extents
and fell below the 75% intersection-over-union rule. The browser grouped 119 photos
into 15 cards, but three night feeder outliers remained separate. A test-first fix
adds bounded extent tolerance against the fixed first photo, reducing this saved
page to 12 cards while retaining all 119 originals. The footer also distinguishes
photo counts from review-card counts. Publication and deployment must be verified
before treating this change as live.

Read-only photo history showed 226 retained model-crop candidates across 35 visits
on 14 October. Six cached full views were replayed on Quark with the published
strict CPU detector under the external resource guard. Inference completed without
errors or remaining workers; normal thumbnail crops were below threshold on all
six, while classification-candidate searches produced crops in three. The detector
artifact matched its registered checksum. Preprocessing, input size and decoder
configuration matched the canonical release configuration; differences concerned
provider declarations and catalogue metadata. The crop-service source is unchanged
from the earlier 8 October baseline. These checks establish that the detector runs,
but do not establish unchanged recall or explain the owner's reduced displayed
crops. Do not lower thresholds or declare that concern resolved from this sample.

Photo selection has a separate, intentional gate: commit `1bcd8b02` on 4 October
raised the minimum photo detector score from 0.08 to 0.25. Saved examples include
Dunnock crops with species scores 0.9806/0.9849/0.9933 but detector scores
0.2353/0.1694/0.1176, which the current photo-presence gate excludes. Conversely,
one tree-sparrow crop has detector score 0.7057 but species score 0.1477 and fails
the independent species requirement. These explain specific exclusions, not the
entire reported trend. Qualify the photo-selection policy with labelled positives
and hard negatives before weakening either gate; do not conflate it with detector
execution, video counting or Garden's separate 0.63 threshold.

## Initial pause checkpoint

Work is paused at the owner's request. Garden remains an owner-reviewed prototype;
production-grade mammal capture is not yet demonstrated. **Animal grouping is the
first unresolved defect to investigate when work resumes.** The owner reports that
it does not work in the running application. This report has not yet been reproduced
or fixed; passing fixture tests do not establish that the live review flow works.

The owner also reports **many fewer crops recently** and suspects that the crop
detector may have partially regressed. This is an unresolved owner observation,
not a confirmed cause. Earlier bird classification and data-integrity checks do
not establish that crop detection still works at its previous rate. Investigate
this bird-pipeline concern before further Garden model changes.

## Deployed state

Latest `dev` at this checkpoint is `e6f0cb3d5078200c7b4cd64312d65a06e30395d8`
([PR #713](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/pull/713)).
All 14 publication jobs succeeded. A fresh registry and Dockhand check on
14 October confirmed that the running `dev-intel` image matches this revision and
is healthy, with zero container restarts. Dockhand had already pulled and deployed
this image; a second deployment was unnecessary.

The latest changes retain the selected collection cadence while a scan is active
and let completed work catch up without replaying completed windows. The earlier
known-photo-unavailable fix is also deployed. Issue
[#698](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues/698)
remains open: screenshots alone do not establish every missing photograph's cause.

At the pause, motion collection remains enabled only for the Patio camera, with
Cedar's animal threshold at **0.63**. Bird routing, models, settings and owner
decisions have not been changed by the model experiments. Pausing development
does not switch off the running collector.

## Demonstrated checks

- Published-build collector tests passed on both Intel and CUDA images using
  actual Cedar CPU inference and original public fox recording windows. Quark's
  catch-up starts were about 5.003 seconds apart; Picard's latest-build starts
  were 5.005 and 5.018 seconds apart. Active intervals were 10/5/5 seconds,
  returning to 10 seconds when caught up.
- Private tests passed restart/cursor deduplication, invalid-media backoff and
  queued-bird priority. Picard's completed results were collected successfully;
  all owned test workers exited. These collector checks are **not new CUDA
  model qualification**. Earlier actual CPU/CUDA model and bird-preemption checks
  are separate evidence.
- Deployment acceptance preserved all 746 existing detection rows, including their
  fields, owner names, evidence and configuration. Both databases passed integrity
  checks. A normal bird diagnostic identified Robin on the Intel NPU at 0.9644;
  its first request after restart took 9.494 seconds.
- The final read-only observation at approximately 17:15 UTC showed readiness and
  MQTT connected, empty bird queues, zero fault drops, no camera frame skips,
  about 802 MB application RSS and a Garden completion cursor about 40 seconds
  behind. There were still 746 bird records. No natural bird events had been
  processed in this startup epoch, so natural live-ingest stress is unproven.

## Capture quality and model findings

The feeder/foliage false positives remain a real usability problem. At the final
observation there were **119 pending captures** and all **128 motion-photo slots**
were occupied, using about 65.3 MB. These are captures requiring review, not
confirmed animals. Grouping must reduce review effort without concealing individual
photos or applying decisions to unseen captures.

A retained, genuine daytime squirrel visit on the bird camera supplied a new
positive control. The existing bird path had stored two squirrel photographs from
this **single visit**. That camera is not opted into Garden motion collection;
the Garden comparison was private, not a missed live Patio visit.

All 800 decoded frames matched the three original Frigate downloads exactly.
Cedar rejected every window because it confidently labelled the green feeder as
a person, including a frame where it also detected the squirrel. Larch behaved
similarly. Original PyTorch checks reproduced the error, and fixed-square ONNX
output closely matched the original model. Neither changing the winning-class
rule nor restoring the original rectangular padding solved this case.

| Candidate | Result on this one visit | Limitation |
|---|---|---|
| Cedar, 640 | All three windows rejected by false person detections | Current model; animal threshold changes cannot repair the person veto |
| Larch, 640 | All three windows also rejected | No improvement for this scene |
| Redwood, 1280 | Localized squirrel samples, but other samples still vetoed each window | About 562 MB; roughly 3.1–3.3 seconds per CPU forward |
| Compact, 1280 | Localized all three annotated squirrel samples above 0.63 without the feeder person veto | Worse person coverage and weaker broader mammal recall; unsuitable as a direct replacement |

A separate person-only YOLOE26s experiment is promising but **not integrated**.
On the same 21 previously screened public images containing 41 annotated people:

| Model | Images triggering person rejection | Annotated people localized at IoU ≥ 0.5 |
|---|---:|---:|
| Cedar | 20/21 | 32/41 |
| Compact | 18/21 | 24/41 |
| YOLOE26s, person output only | 20/21 | 36/41 |

YOLOE26s lost none of Cedar's image rejections or localized-image coverage in these
controls. These are correlated comparison controls with unknown training overlap,
not independent privacy accuracy. Its exact feeder/video comparison is prepared
but **has not run**. No replacement, auxiliary person detector, threshold change,
mask or weaker privacy policy has been deployed.

## Resume here

1. Reproduce the owner's grouping failure against the deployed build. Compare
   actual API captures with rendered cards, camera/detector identities and box
   overlap; check the 128-capture page boundary and filtering. The current design
   groups motion boxes with at least 75% intersection-over-union against the first
   box. Determine the actual failure before changing this rule. Add a failing
   regression test and verify navigation, per-photo confirmation and group
   dismissal/undo on realistic repeated captures.
2. Investigate the reported reduction in crops. Compare recent crop attempts,
   accepted boxes, rejection/fallback reasons, active model/provider and settings
   against the previous working build. Replay identical retained bird images on
   both builds to distinguish a detector or preprocessing regression from changes
   in camera framing, bird activity or source events. Do not treat a successful
   species-classification diagnostic as proof of crop-detector health.
3. Finish the person-only detector comparison on the exact squirrel samples,
   feeder negatives and real-person video controls. Require positive and negative
   qualification before changing capture or privacy behaviour. A higher animal
   threshold alone cannot solve confident feeder errors or false person vetoes.
4. Keep issue [#641](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues/641)
   open until genuine daytime and infrared mammals and hard negatives qualify
   the complete capture/review path. Do not infer broad Patio accuracy from one
   daytime squirrel visit on another camera.
5. Any implementation resumes with test-first development, full repository checks,
   a PR to `dev`, complete image publication and Dockhand deployment. Preserve bird
   history/settings and owner decisions; never seed synthetic production sightings.

Private evidence and the operational continuation notes remain outside Git. No
private photographs, credentials or diagnostic archives belong in this report.
See the maintained [Garden feature guide](../features/garden-animals.md) and
[replay guide](../development/garden-replay.md) for the implemented behaviour.
