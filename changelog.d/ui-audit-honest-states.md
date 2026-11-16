- **Health is readable in both themes and says what it measured.** Subsystem detail is one ruled
  list in full-contrast ink, with each state in a worded label instead of tinted cards and dimmed
  text. Labels say what they count ("Messages being handled", "Failures in a row") rather than
  "In flight" or "Open until: Closed", and video analysis says whether it is paused and until when.
  A pipeline with the broker down reads as not measured, not healthy. The broker's last failure is
  worded from its cause ("the host name … was not found. Check the address.") with the client's
  own text under **Technical details**, and the commonest backend warnings, such as a detection
  dropped because naming its snapshot took too long, are said in plain words with what to try. Any
  other warning reads "A processing step failed" and never shows the backend's raw error, which can
  hold paths and addresses, outside **Technical details**.
  While the first reading loads the page says so and holds its space; if it cannot be read it
  claims no state; if a refresh fails it keeps the earlier reading and says how old it is, until a
  read (from the page or in the background) succeeds; a slow, older answer never replaces a newer one. On a
  phone each process in **Resource use right now** is a short list, so no column is cut off, and
  **Clear error history** now sits with **Earlier incidents**.
- **One name for Health.** The sidebar, the System status link, the Notifications link and the
  server-error hint all call the page Health. The health notification states its cause ("The MQTT
  broker is not connected, so no new detections can arrive.") instead of "Health status: degraded".
- **The jobs banner counts honestly.** It counts every job once by its real state ("4 jobs: 1
  running, 3 queued", never "5 jobs running" over "1 running"), says what the leading job is doing
  or waiting for ("Video analysis: waiting for Frigate to answer"), drops the "capacity" wording,
  and draws a progress bar only when there is a measured total. `GET /api/jobs` reports the new
  `waiting_for_frigate` phase, and `GET /api/diagnostics/connections` the broker failure's
  `last_error_cause` (see [the API reference](docs/api.md#debug-owner)).
- **Audio history never shows a zero it did not measure.** While it loads the figures and charts
  show placeholders, not "0 heard" and "No activity yet"; if the history cannot be read the page
  says so with what to try (the server's words under Technical details) and shows no figures; a
  failed refresh keeps the earlier reading and says when it was read. Every chart has **Show the
  numbers** with its values as a table (each day as the calendar day counted, in any time zone, and
  all 24 hours), and the species mix key shows each slice's count,
  "Other species" included. The top species' reference photos load only when that list comes
  into view.
- **A favourite's failed copy says why.** Instead of "Archive failed · Try again", the record says
  what was not kept, the cause (Frigate could not be reached, the disk is full, …) with what to
  check, and whether YA-WAMF will try again by itself. Until the copy's status has been read it
  says only that it is checking, and if that check fails it says so and offers **Check again**. A matching call is stated once, in the
  facts with its score.
- **Notices no longer cover a dialog's close button.** While a dialog is open, toasts appear at
  the bottom left.
