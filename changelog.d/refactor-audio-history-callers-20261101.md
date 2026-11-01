- **Audio callers now use the audio history repository directly.** Nothing changes for
  someone at their feeder. The audio routes, the audio service, the catalogue identity
  backfill and the public-audio checks on events, the daily summary and species detail
  now read and write BirdNET-Go history through `AudioHistoryRepository`, and the
  detection repository's temporary audio delegates are gone. Each call keeps the same
  connection and commit point it had before.
