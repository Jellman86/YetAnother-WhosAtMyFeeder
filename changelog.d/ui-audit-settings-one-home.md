- **Every setting has one home, and Settings has a tab per job.** Detection keeps the rules for
  accepting an identification; a new **Models** tab holds the identification model, the bird
  finder, the hardware and the runtime report, with the full model list behind **Choose another
  model**. Data keeps what is kept and for how long, with the configuration backup; a new
  **Maintenance** tab holds the repair and fill-in jobs and, in a closed card at its end, the
  actions that delete history. Telemetry moved to Security, beside who can reach the install. The
  Debug tab is gone: its switch and the Model evaluation link are in Models, and old links to
  `/settings/debug` open Models.
- **Health is a page of its own** under Manage in the sidebar, at `/system-health`. Older links to
  Settings → Health and `/settings/errors` open it. Its verdict and its list of open problems now
  come from the same reading, so it can no longer say "Degraded" beside "0 open"; an open
  incident is listed with the verdict and never shown beside "Healthy", and the panel below holds
  only incidents that have cleared. The process table can be reached and scrolled by keyboard, the
  chart legend names CPU once, and **Clear error history** says what it clears.
- **Settings › Models names the model in use as its card does** and says when its file is not on
  this install, instead of showing a file name with "1 species". The bundled model in use shows
  **In use**, never **Download & set up**. The classifier status reports `effective_model_name`
  and `active_model_installed` ([API](docs/api.md)).
- **Garden alerts are set with the rest of Garden**, in Beta features → Garden animals → Alerts;
  Notifications links there and stays the one place channels are set up. In the notification
  sentence, the species and the channels are links to their one control instead of second
  controls, and audio-only is a switch.
- **Calm, counted confirmations.** Deleting all history asks "Delete all 882 detections, every
  cached photo and clip, and every archived favourite?" instead of "DANGER … ALL". Red is kept for
  actions that delete; repairs, backfills and the integrity scan are ordinary buttons, the scan
  turning red only while its policy deletes local data. The Data tab states its history in one
  sentence instead of four stat tiles.
- **Plainer words in Settings.** The Notifications hint for Frigate links points to Connection,
  where the Frigate public URL is set, with a button that opens the field; "Detections page" is
  now the Explorer; "nowhere yet" is "no channel yet"; the Debug switch reads "Discard results the
  model could not compute".
