- The Leaderboard has a **Today** period, counted from your local midnight, and its other
  periods now say what they count: Last 24 hours, Last 7 days, Last 30 days and All time (they
  were Day, Week, Month and Total). Seen, Heard, the photo wall, the charts and the heatmaps all
  count the same stretch, and a page loaded across midnight asks again rather than mixing two
  days. Today's trend compares with yesterday up to the same time, and is left out, with the
  reason, when a clock change, the history shared with guests or cleanup would make the
  comparison uneven. Early in the day the board says no visits have arrived yet, and a guest
  whose shared history starts after their midnight sees the time counting starts from. While a
  new period loads, the rows on screen keep the name of the period they were counted over.
  Links with `span=day` still open Last 24 hours; the API takes `span=today`
  ([docs/api.md](docs/api.md)) (part of #1097).
- In time zones whose offset is not a whole hour, such as India and Nepal, the Leaderboard's
  timeline and activity heatmaps now put each visit in its own local hour and day; a visit just
  after midnight no longer lands in the hour before.
