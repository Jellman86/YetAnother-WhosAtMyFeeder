- **Delete all history** in Settings → Maintenance now counts the detections before it can be
  confirmed. The question said "Delete all 0 detections" on an install holding hundreds, because
  the count was only ever read on the Data tab. It now says it is counting, then states the real
  number, and if the count cannot be read it says "all detections" with no number. The confirm
  button reads **Delete all history permanently**. **Purge old records** reads its count the same
  way, at the moment of asking.
- A detection record says "Frigate no longer has this event or media" only when Frigate answered
  that the event is not found, or the media integrity scan recorded it missing. When Frigate was
  unreachable, slow, erroring or simply not asked, the record now says that instead, with what to
  try, and no longer offers "technical details" when no error was recorded. `/api/events` reports
  what Frigate answered in a new `frigate_event_check` field
  (see [the Frigate event guide](docs/troubleshooting/frigate-event-not-found.md)).
