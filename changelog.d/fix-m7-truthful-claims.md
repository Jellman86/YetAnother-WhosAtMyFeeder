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
- The first-run wizard's Cameras step no longer shows "Loading your saved settings…" with Continue
  disabled while it is really waiting for Frigate. It says it is asking Frigate for its cameras,
  waits at most 8 seconds, and lets setup continue with the cameras already saved; after that it
  says Frigate did not answer and offers typed names. Back, Skip step and Continue now stay inside
  the wizard's card while the step scrolls above them, instead of being cut off at 1440×900.
- The wizard's review no longer says "Configured" for a model that is not on the install. It reads
  the same state as the model step and says **Needs a download**, **Installed**, or **Chosen** when
  nobody could check. About's pipeline says "Not installed" for the same model instead of "Not
  loaded yet", and the status sentence names it as the chosen model.
- The "not responding" and "could not finish starting" screens no longer say "Your feeder data is
  safe", which nothing had checked while the service was down. About's browser step says
  "Connected" instead of "Live", a word kept for camera events.
