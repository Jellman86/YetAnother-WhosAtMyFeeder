- **The sidebar's System status is a plain list that says each state in words.** Three rows,
  **Frigate events** (Live, Waiting for events, Not connected, Frigate not answering), **Audio**
  (Listening, Not listening, Off) and **Alerts** (On, Off), each with a small dot whose shape as
  well as colour tells working from needs-you from off. Amber appears only when something needs
  you. CPU and accelerator load is one muted line of text instead of a graph behind the card, and
  the collapsed sidebar now shows the same statuses as named icons. Audio reads **Listening** only
  while the MQTT broker session is up, because that is how audio detections arrive.
- **The System health link counts open issues.** It reads **2 issues need attention** only while
  the System health page lists that many open items, and plain **System health** otherwise.
- **A restart no longer fills the log with a warning per event.** While Frigate is still starting
  it answers every request with an error; opening the Explorer in that window logged one
  `Failed to fetch event` warning for each event on the page. YA-WAMF now recognises that Frigate
  as a whole is not answering, stops asking about individual events, checks again with a growing
  delay, and logs one line with the number of reads put off. Queued video analysis waits for
  Frigate instead of failing. A Frigate error about a single event is still a warning. See
  [Troubleshooting](docs/troubleshooting/diagnostics.md#while-frigate-is-starting).
- **Repeated faults are one diagnostics entry.** Backend warnings and errors on the System health page
  shows a fault that keeps happening once, with how many times it was recorded and when it was
  first and last seen. `GET /api/diagnostics/errors`, `/workspace` and `/bundle` events carry
  `count`, `first_seen` and `last_seen`, and the snapshot adds `total_occurrences`
  (see [the API reference](docs/api.md#debug-owner)).
