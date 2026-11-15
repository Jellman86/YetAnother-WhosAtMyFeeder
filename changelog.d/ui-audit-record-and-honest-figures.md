- The detection record now reads, and is walked by keyboard, in one order: the
  identification, the decisions about it, the facts, a short species summary with a
  link to its source, then the identifiers. Confirm, Pick a different species and
  Score again sit directly under the name; Change the common name, Hide and Delete
  wait behind **More actions**. The identifiers are a plain panel in the current
  theme instead of an imitation terminal window, and the close button has a strip of
  its own so nothing scrolls underneath it. A dialog whose last control is a
  collapsed section can now be reached by keyboard.
- About no longer shows "Running for Unknown" beside an availability figure. The
  running time is read from the backend and, when it cannot be, the card says it was
  not measured; availability is labelled with its 24-hour window. The card names the
  runtime and its device ("TFLite on CPU"), the page shows one version string, and
  the latest visit falls back to the newest stored photograph when no cropped one is
  in reach, instead of saying there is no picture.
- Species detail labels its count "Detections, all time" (or "shared history" for a
  visitor) and says how that differs from the Leaderboard's visit counts. The Audio
  history species ring adds an "Other species" slice so its total is the page's
  "Heard" figure.
- The footer of every page carries the version, the licence and the links only. The
  bird facts and the "Built with AI assistance" line moved to a new **About this
  project** section on About, where a fact changes only when you ask for another.
- A failed MQTT or BirdNET-Go connection test now states the cause (host name not
  found, nothing answering, no answer in time, user name or password refused) and what
  to check, instead of "Check logs" or an exception name. The test dialog has one close
  button, states each stage's outcome in a word, shows a summary only when it adds
  something, and offers **Test again** after a run.
- First-run setup is nine steps instead of ten: the history import and the usage-stats
  question share one **Optional extras** step. A disabled **Continue** says why, the
  model step always opens with a model selected, the connection step offers **Set up
  later** and says exactly what waits on Frigate and the broker, and setup opens on its
  heading rather than on **Skip setup**.
- Notifications say once, above the list, that jobs and system events are shown only to
  you, and draw a progress bar only for work that is unfinished. The process table on
  Settings → Health can be scrolled by keyboard.
