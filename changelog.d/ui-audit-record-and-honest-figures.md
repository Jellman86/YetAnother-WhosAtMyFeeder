- The detection record now reads, and is walked by keyboard, in one order: the
  identification, the decisions about it, the facts, a short species summary with a
  link to its source, then the identifiers. Confirm and Pick a different species sit
  directly under the name; Score again, Change the common name, Hide and Delete
  permanently wait in the **More actions** list, and Species details is a link beside
  the name. The archive status of a favourite is a line in the record instead of a
  pill over the photograph, the video analysis card no longer shows the model id or
  device, and a disabled Find more birds says why. The identifiers are a plain panel in the current
  theme instead of an imitation terminal window, and the close button has a strip of
  its own so nothing scrolls underneath it. A dialog whose last control is a
  collapsed section can now be reached by keyboard.
- About no longer shows "Running for Unknown" beside an availability figure. The
  running time is read from the backend and, when it cannot be, the card says it was
  not measured; availability is labelled with its 24-hour window. The card names the
  runtime and its device ("TFLite on CPU"), the page shows one version string, and
  the latest visit falls back to the newest stored photograph when no cropped one is
  in reach. With no picture at all the facts sit under the title instead of beside an
  empty frame. The pipeline cards share one style with the state as a dot and a word,
  and model names no longer break mid-word.
- Species detail labels its count "Detections, all time" (or "shared history" for a
  visitor) and says how that differs from the Leaderboard's visit counts. The Audio
  history species ring adds an "Other species" slice so its total is the page's
  "Heard" figure.
- The footer of every page carries the version, the licence and the links only. The
  bird facts moved to a **Did you know?** card on About, where a fact changes only
  when you ask for another. How the project was built is said once, in About's
  opening paragraph and its thanks.
- A failed MQTT or BirdNET-Go connection test now states the cause (host name not
  found, nothing answering, no answer in time, user name or password refused) and what
  to check, instead of "Check logs" or an exception name, and says it in the page's
  language: the backend answers with a cause code and the host and port only, and the
  page words it. A server failure that gives no reason, such as a bare "Internal Server
  Error", is now explained with what to try and where to look instead of being shown raw. The test dialog has one close
  button, states each stage's outcome in a word, shows a summary only when it adds
  something, and offers **Test again** after a run.
- First-run setup is nine steps instead of ten: the history import and the usage-stats
  question share one **Optional extras** step. A disabled **Continue** says why, the
  model step always opens with a model selected, the connection step offers **Set up
  later** and says exactly what waits on Frigate and the broker, and setup opens on its
  heading rather than on **Skip setup**.
- Notifications say once, above the list, that jobs and system events are shown only to
  you, and draw a progress bar only for work that is unfinished. A row that leads
  somewhere is itself the link, with the time on its title line, so the list is about
  half as tall. A failed connection test now ends each failed row with what to check. The process table on
  Settings → Health can be scrolled by keyboard.
