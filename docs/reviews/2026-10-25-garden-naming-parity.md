# Garden and bird naming parity

This review covers the automatic naming path on `dev`, including the private
Explorer refresh change. It separates implemented behaviour from remaining
product and field-validation work.

## Naming behaviour

Garden now checks each eligible new capture without an owner click, uses its
configured naming threshold, automatically names qualifying animals, and places
successful below-threshold results in restorable Dismissed history. Model/runtime
failures remain pending for retry. Missing location or catalogue identity is
reported rather than guessed. Owner decisions take precedence over later model
results and restart recovery.

Automatic SpeciesNet execution follows the configured Detection device preference,
with a CPU comparison before an accelerator is accepted. Completed results retain
execution evidence. Garden yields to bird inference and camera activity, and
releases its disposable worker after each operation. These are intentional
resource-management differences from warm bird classifiers.

The Explorer receives a private invalidation after an automatic result is saved.
It rereads the current Garden view and updates an open record, or closes it if the
capture has been removed. Reconnection also invalidates the view. The signal has
no capture details and is excluded from guest streams. Burst updates are combined
into one refresh; the mixed view need not reread bird history.

## Remaining differences

- Garden notifications are not implemented. Any future notifications must have
  their own opt-in and must not enter bird notification/reporting paths.
- Garden history has its own capture/retention rules. Frigate photographs can
  expire, and motion-photo retention is bounded; bird media archival is not
  automatically available to Garden.
- Garden visit grouping is a browser presentation over captures. Mixed Explorer
  pages have a 200-capture limit, unlike server-paged bird visit summaries. The
  Garden-only view pages through all captures.
- Cedar motion collection remains CPU-only. SpeciesNet accelerator validation
  does not establish motion-detector accelerator support.
- Broad mammal accuracy and privacy qualification remain incomplete. Detector
  misses, false person vetoes, night footage and hard negatives need labelled
  evidence; a passing runtime or UI test does not establish field accuracy.

Garden remains an owner-only beta. Bird audio matching, bird exports and bird
leaderboards are domain-specific boundaries, not features to enable for Garden
as part of naming parity. The outstanding field acceptance is tracked in
[#641](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues/641).

See the maintained [Garden guide](../features/garden-animals.md),
[labelled pipeline comparison](2026-10-23-garden-labelled-pipeline-validation.md)
and [accelerator qualification](2026-10-24-garden-automatic-accelerators.md).
