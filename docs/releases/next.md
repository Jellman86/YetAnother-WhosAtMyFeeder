# Next release — draft

This is a release-preparation draft for the current `dev` branch, reviewed against `438ed1af`
on October 11, 2026. No new version or release tag has been published. The final release must pass
the [publication checklist](../development/releasing.md); recheck its scope and exact-tag evidence
before copying these notes to GitHub Releases.

Your feeder history is easier to review, and model setup now makes the difference between a
hardware check and species accuracy clear. Photos stay with your records under explicit storage
limits, while new model choices can be compared on your own hardware.

## What's new

- **More local model choices, with species names built in.** Model Manager adds DINOv2, newer
  RoPE models, regional NaFlex and Parallel models, and BioCLIP 2.5. Registered classifiers use
  the species catalogue rather than requiring a label text file. Regional coverage matters;
  [compare coverage, sizes and tested hardware](../features/model-catalogue-2026-10.md).
- **Setup that saves the model and provider you chose.** The wizard offers a complete location
  pair for DINO, saves it before validation and keeps a passing manual provider choice. Continue
  saves the displayed preference. Reopening setup preserves unrelated Settings edits.
- **Seen visits and heard calls together.** Explorer's optional **Heard calls** lane shows stored
  call bouts between camera visits, with spectrograms and playback. Matching calls attach to
  a seen visit. Guest sharing rules and visual-only filter restrictions still apply.
- **A clearer review of uncertain species.** **Needs a check** shows the photographs behind a
  name, lets you correct selected visits and handles visits with many captures. A rename also
  teaches personalised identification; inspect the selected scope before applying it.

## Smoother everyday use

- **A compatibility check no longer looks like 0% accuracy.** Results show passing providers and
  measured inference time. Detection and Models refresh the workers' actual provider after a
  check, so a move to NPU does not leave an old CPU label on screen.
- **Photos follow retention controls.** The old Media Cache and Snapshots switches are removed.
  Photographs and visit media are retained within age, per-species and storage limits; copies of
  Frigate's event clips remain optional. Unwritable media storage is reported as degraded health.
- **Less repeated video decoding.** Photo updates can reuse the winning frame without changing
  the accepted species or counted-bird evidence. CPU, Intel and one NVIDIA configuration have
  been tested; sustained production backfill with live ingestion remains under review in
  [#576](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues/576).

## Before you update

- **Back up persistent data first.** Preserve `/config` and `/data`, including configuration,
  database, models and favourite archive. This update includes migrations; see the
  [upgrade and rollback guide](../../MIGRATION.md) before reverting to an older image.
- **Check the one-time retention migration.** An installation that disabled either retired
  photo/cache switch has best-available snapshots disabled once; a previously disabled cache also
  disables full-visit clips once. Explicit environment overrides and later owner choices are
  preserved. Review **Settings → Data** and **Settings → Connection** after updating.
- **Your default classifier stays the same.** New models are optional and need the matching
  application build. Downloading a new model asset does not add support to an older application.
  DINO is experimental; location is optional and sent to its local inference input, not embedded
  in redistributed weights. Hardware compatibility does not prove accuracy at your feeder.
- **Keep your image family unless you intend to change it.** Unsuffixed tags remain the full
  compatibility image. Optional CPU, Intel and CUDA variants are described in
  [Hardware Acceleration](../setup/hardware-acceleration.md).

## Good to know

- **The original #490 fault is still unconfirmed.** Worker isolation and bounded same-model CPU
  recovery contain failures, but they do not prove the reporter's EVA-02/Intel GPU stall is gone.
  A healthy NPU run is evidence for that tested configuration only.
- **Video requires recordings.** A Frigate event with a snapshot and `has_clip: false` can still
  classify; it cannot supply a missing event clip. Enable and retain recordings if you want video
  analysis or full-visit playback.
- **Garden-visitor history and full identification provenance are deferred.** The proposals in
  #641 and #643 are not included as shipped features.

## Thanks

Thanks to [@Milirey](https://github.com/Milirey) for the detailed backfill/live-feed report and
support bundles in [#490](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues/490).
That evidence helped improve isolation and recovery while keeping the original hardware fault
open for confirmation.

Thanks to [@aav7fl](https://github.com/aav7fl) for the original multi-bird clips, screenshots,
diagnostics and follow-up testing in [#481](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues/481).
Their report informed the photo repair and the still-open decoding and retention follow-ups,
[#576](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues/576) and
[#622](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues/622).

Thank you as well to everyone listed in [Contributors](../../CONTRIBUTORS.md).
See the [development changelog](../../CHANGELOG.md) for the full implemented record; the published
release will link to its exact tag.
