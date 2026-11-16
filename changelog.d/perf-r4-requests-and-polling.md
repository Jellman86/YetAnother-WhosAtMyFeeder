- An open Dashboard now follows the live stream instead of polling while nothing happens. The
  backend announces each newly stored BirdNET-Go call to the owner's open pages
  (`audio_detected` over `GET /api/sse`, with no detection in it; see
  [the API reference](docs/api.md)), so the Heard card, the day's call figures and the species
  checks read when a call is heard, hidden or restored, no more often than they used to poll, and
  the day's summary, visit log, species checks and review queue read when a visit, correction or
  Garden review is announced, with one safety read every five minutes. A read that fails is tried
  again at the old pace rather than trusted, and a stream that comes back after a drop is followed
  by a fresh read at once. A guest, or an owner whose live stream is down, polls as before. An idle
  Dashboard makes 9 requests a minute instead of 20.
- Opening a page asks each status question once. The shell, the page and its cards each read the
  same camera, version, update, classifier, analysis-queue and connection status, so most pages
  sent two or three of the same request on every load; readers asking at the same moment now
  share one answer, and only within one session and language. A failed read is never reused, a
  change the server announces is read fresh, a model change or settings save drops the shared
  reading of what names birds, and a view that has just changed something reads for itself and
  hands that reading on. The Dashboard's first read of the
  day waits for the owner's Garden switch instead of reading the day twice.
- Settings reads Frigate's cameras, the storage figures, the cache measurement and the version
  only on the tabs that show them. Settings › Appearance now makes 18 API requests on opening
  instead of 24.
- The Leaderboard opens on three rows of its photo wall (four on a phone), with every photograph
  sized to its cell and the full wall one press of **Show more visits** away, so the rankings are
  in reach and a cold load asks for 42 photographs instead of 84. The ranking is built once, as
  rows or as a table, whichever fits, instead of both with one hidden; its large readings are no
  longer wrapped in reactive proxies; and dates across the app are formatted with one reused
  formatter per format. On a slow phone the page blocks for half as long while it opens.
- The Health page and Settings › Models no longer jump as they load. Health shows the sections
  beneath its verdict once the first health reading is in, since the verdict's length depends on
  what it finds; Models shows what follows the model list once the list has its first answer, and
  **Refresh** keeps the list in place while it reads again.
