- **Every owner screen now reads one status, pushed as it changes.** The sidebar, the jobs
  banner, Health, the Dashboard and Settings › Models used to ask the server for their own
  readings of the same things (jobs, the analysis queue, the broker and Frigate connections,
  camera health, the model and its provider, host load) on their own timers, so two of them could
  show different counts or verdicts for the same moment. The server now derives one status and
  pushes it over the live stream whenever something changes, with fresh figures every 15
  seconds; every screen shows that one reading. Each part carries a cause in plain words: the
  broker is disconnected, Frigate is not answering, a camera is offline, the bird finder is on
  the CPU, the media folder cannot be written, nothing has been heard yet, or no notification
  channel is on.
- **An open page no longer polls.** With the live stream connected, a page left open makes no
  status requests at all; Health reads its half-hour chart once a minute instead of four times.
  If the stream drops, the status is read once a minute until it is back. The new
  `GET /api/status` returns the same snapshot (owner only); see [the API notes](docs/api.md).
- **A stalled answer no longer leaves a screen waiting.** Health, Settings › Models and the
  sidebar's readings give up on a reply that stops halfway, including a proxy's error page that
  never finishes, and try again on the usual backoff; closing the screen cancels its read. Every
  such read now has a deadline: a bird analysis gives up after three minutes rather than never.
