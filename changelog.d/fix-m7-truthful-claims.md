- **Delete all history** in Settings → Maintenance now counts the detections before it can be
  confirmed. The question said "Delete all 0 detections" on an install holding hundreds, because
  the count was only ever read on the Data tab. It now says it is counting, then states the number
  the reset will really delete, hidden detections included, and if the count cannot be read it
  says "all detections" with no number. The number confirmed is sent with the request, and the
  server compares and deletes under one database write lock: if detections arrived while the
  question was open, nothing is deleted and the question is asked again with the new number. The confirm button reads **Delete all history permanently**.
  **Purge old records** reads its count at the moment of asking too.
- A detection record says "Frigate no longer has this event or media" only when Frigate answered
  that the event is not found, or the media integrity scan recorded it missing. When Frigate was
  unreachable, slow, erroring, refusing YA-WAMF's credentials or simply not asked, the record now
  says which, with what to try, and no longer offers "technical details" when no error was recorded. `/api/events` reports
  what Frigate answered in a new `frigate_event_check` field
  (see [the Frigate event guide](docs/troubleshooting/frigate-event-not-found.md)).
- The first-run wizard's Cameras step no longer shows "Loading your saved settings…" with Continue
  disabled while it is really waiting for Frigate. It says it is asking Frigate for its cameras,
  waits at most 8 seconds, and lets setup continue with the cameras already saved; after that it
  says Frigate did not answer and offers typed names. Back, Skip step and Continue now stay inside
  the wizard's card while the step scrolls above them, instead of being cut off at 1440×900.
- The wizard's review no longer says "Configured" for a model that cannot name a bird. It reads
  the classifier's own runtime report, as the model step does: **Needs a download** when the files
  are missing, **Could not load** when they are there but the model failed to load, **Loading** while it is being
  loaded, **Ready** or **Running** only on positive evidence that it is, and **Chosen** when
  nobody could check. About's pipeline says "Not
  installed" for a missing model instead of "Not loaded yet", and the status sentence names it as
  the chosen model.
- The "not responding" and "could not finish starting" screens no longer say "Your feeder data is
  safe", which nothing had checked while the service was down. About's browser step says
  "Connected" instead of "Live", a word kept for camera events.
- A saved diagnostics bundle on the Health page reads "1 group · 1 event · 1 snapshot" instead of
  "1 groups • 1 events • 1 snapshots", in every language.
- The review queue gives each visit its own reason. A bird the model could not name is no longer
  described as "below the naming threshold"; the dialog says there is no species to confirm, as
  the Dashboard card does for the same visit.
- Species details opened from a Leaderboard row lead with the visits that row showed, in its
  window ("Visits, last 30 days"), followed by the all-time detections.
