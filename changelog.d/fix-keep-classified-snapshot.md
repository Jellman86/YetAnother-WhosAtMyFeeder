- **A chicken that sat still keeps its photo in Garden.** Frigate discards an event whose object
  never moves, snapshot and all, often within minutes. A domestic bird moved from Birds to Garden
  after that used to show "Photo expired", although YA-WAMF still held the frame its bird model
  classified. Garden now keeps YA-WAMF's own copy of that whole frame when Frigate has no snapshot,
  keeps it straight away for a domestic bird routed to Garden as it arrives, and looks once more at
  moved captures already recorded without a photo. The clip stays Frigate's: when Frigate kept
  none, the capture says so. See
  [Kept photographs and clips](docs/features/garden-animals.md#kept-photographs-and-clips).
- **"When Frigate loses a visit" never deletes a record YA-WAMF still has a photo for.** The
  **Delete** choice is now labelled **Delete records YA-WAMF has no photo for**: a record whose
  photo YA-WAMF holds is marked missing instead, so the media integrity scan (and the older
  missing-snapshot purge setting it replaced) cannot remove the only photo left. See
  [Frigate "Event Not Found" explained](docs/troubleshooting/frigate-event-not-found.md).
