# Qualifying a bird-counting change

Use this offline check before promoting a counting policy for
[#734](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues/734).
It checks **retained individual bird observations**, after confirmation and
duplicate suppression. Raw detector boxes and the selected photograph are
different evidence and cannot qualify a counting change.

The check does not run inference, import application configuration, access an
application database, change model eligibility or authorize deployment.

## Prepare and freeze the panel

Review the full-resolution images and box every visible bird. Count uncertain
species as birds when their physical presence is clear. Include birds of the
same and different species, overlapping birds, fixtures, empty scenes and other
animals. Record exclusions before inference when presence itself is ambiguous.
Contact sheets and classifier predictions are not ground truth.

Every case needs an image path and SHA-256 checksum, a stable visit ID, verified
exhaustive bird boxes, and exactly one cohort tag:

- `development`: cases already used to design or adjust the policy.
- `holdout`: independent primary visits reserved before evaluating the policy.
- `stress`: secondary examples, including public photos with unknown training
  overlap. Keep license and source records beside those images.

Keep all frames of a visit in the same cohort. Related events from one visit
must share a visit ID. Renaming an image does not make it independent.
An annotation corrected after viewing inference becomes development evidence;
set `annotation_amended_after_inference` and use a new holdout for qualification.
Keep the old annotation and the correction rationale for audit.

Declare the required number of independent multibird and negative visits in
`protocol` before inference. These targets express the intended test coverage;
passing a finite panel cannot guarantee perfect recognition on unseen footage.
For example, the following schema excerpt declares twenty visits of each kind.
Its two example cases alone cannot pass those coverage requirements.

```json
{
  "protocol": {
    "minimum_multibird_visits": 20,
    "minimum_negative_visits": 20
  },
  "cases": [
    {
      "id": "two-birds",
      "visit_id": "visit-a",
      "tags": ["holdout"],
      "image_path": "images/two-birds.jpg",
      "image_sha256": "<image-sha256>",
      "annotation_verified": true,
      "annotation_scope": "exhaustive",
      "boxes": [[10, 10, 50, 50], [70, 10, 110, 50]]
    },
    {
      "id": "fixtures-only",
      "visit_id": "visit-b",
      "tags": ["holdout"],
      "image_path": "images/fixtures-only.jpg",
      "image_sha256": "<image-sha256>",
      "annotation_verified": true,
      "annotation_scope": "exhaustive",
      "boxes": []
    }
  ]
}
```

Boxes use original-image pixel coordinates `[left, top, right, bottom]`.
Save the exact manifest's SHA-256 separately **before** inference. Changing the
manifest later requires a recorded amendment, not silently refreshing its hash.
Keep private photos, models and large reports outside the repository.

## Export the actual counting result

Replay baseline and candidate policies against the same verified image bytes.
Export one row per holdout and stress case from each policy's retained
`BirdObservationSelection.birds`. Preserve failures as failed results; do not
turn a failed or unavailable scan into an empty successful result.

```json
{
  "manifest_sha256": "<previously-frozen-manifest-sha256>",
  "evaluation_role": "retained_bird_observations",
  "baseline": [
    {
      "case_id": "two-birds",
      "image_sha256": "<image-sha256>",
      "status": "completed",
      "boxes": [[10, 10, 50, 50], [70, 10, 110, 50]]
    }
  ],
  "candidate": []
}
```

This is a format excerpt, not complete passing evidence. Record the inference
runner revision, policy parameters, model artifact digests and actual provider
execution alongside the export. The checker binds supplied rows to the panel;
reviewing the runner is still necessary to establish their provenance.

## Run the check

From `backend`, using the repository's Python environment:

```bash
python -m scripts.eval_bird_count_qualification \
  --manifest /path/to/private/manifest.json \
  --frozen-manifest-sha256 "$COUNT_PANEL_SHA256" \
  --predictions /path/to/private/retained-observations.json \
  --output /path/to/private/qualification.json
```

`COUNT_PANEL_SHA256` must be the independently saved checksum. Relative image
paths resolve against the manifest's directory. The command verifies image
checksums and decoding, and rejects boxes outside the original image.

A successful exit requires complete, correctly bound results, independent
cohorts, the declared primary visit coverage, and no missed or extra candidate
bird on the holdout and stress cases. Objects match one-to-one at IoU 0.5.
A missed bird and a false fixture cannot cancel each other, and a duplicate
body-part box remains an extra observation. Repeat frames and public stress
photos do not increase primary multibird-visit coverage.

The JSON retains baseline and candidate object metrics, count agreement,
individual cases and failure reasons. A nonzero exit means the evidence does
not qualify the candidate; it does not prescribe lowering a threshold.

## Complete the change

Corpus qualification is one part of completion. Also verify the automatic HQ
path and owner-requested scene scans, unknown-species handling, review and
correction behavior, cancellation and native-runtime failures, and preservation
of owner-reviewed history. Measure the added inference cost and exercise the
supported model/provider routes. Hardware agreement, CI and a healthy deployment
are separate requirements; this report grants none of them.

## Confirmation evidence under development

The classifier adapters retain internal `taxonomic_evidence` when the catalogue
binds the complete output order to the actual loaded model checksum. ONNX,
OpenVINO and TFLite use the same aggregation before species grouping or top-k
selection. The record contains bird, non-bird and unknown score mass, output
counts, the winning native output's group, the model checksum and a fingerprint
of the ordered source labels and groups. These are model scores, not calibrated
probabilities that a physical bird exists.

Classification reads an immutable in-memory catalogue snapshot. Loading a model
warms that snapshot off-thread; app-owned catalogue changes invalidate it.
Missing rows, a different label order or width, unavailable mappings, and
classifiers without both bird and non-bird outputs supply no presence evidence.
Unknown mass is retained, never redistributed over known groups. Ordinary
species ranking does not change.

The pure confirmation policy has three outcomes: `counted`, `excluded` and
`unconfirmed`. Its development thresholds are a strong detector score of 0.60,
bird mass of 0.50, and non-bird mass of 0.85 with a non-bird winning output.
Strong detector evidence conflicting with a confident non-bird confirmation is
unconfirmed. Invalid evidence, an unqualified finder, or an uncertain mid-band
proposal also remains unconfirmed. Species certainty is a separate decision.
These are proposal-level verdicts. Bird pixels in an overlapping proposal do
not establish another individual; duplicate and touching-cluster checks remain
necessary before publishing a count. Group scores alone cannot resolve that
ambiguity.

Confirmation must classify a proposal's own pixels afresh. The preparation
helper pads centre-crop inputs on a bounded neutral canvas so the classifier's
subsequent centre crop retains the proposal's full extent. It never widens the
source crop toward neighbouring birds. A caller must bind that result to the
model, catalogue fingerprint and exact crop checksum before applying the policy.

This policy and preparation helper are not yet enabled in capture counting.
Existing saved counts and finder defaults are unchanged. Enabling confirmation
still requires service integration, honest unresolved outcomes, history and
cancellation tests, frozen scene qualification, and provider and cost checks.
