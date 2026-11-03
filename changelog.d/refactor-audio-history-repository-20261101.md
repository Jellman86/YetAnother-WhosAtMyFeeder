- **BirdNET-Go history now has its own repository.** Nothing changes for someone at their
  feeder. Audio ingest, hiding, history, context, public sharing and identity backfill
  moved out of the 6,200-line detection repository into `AudioHistoryRepository`. Every
  statement and commit is unchanged, and the detection repository still answers the same
  calls while callers move. The payload parsers that audio ingest and audio history both
  need now live in one pure module, so the repository no longer imports the audio service
  to avoid a cycle. A captured-output test pins every audio method's result over the same
  seeded history, before and after the move.
