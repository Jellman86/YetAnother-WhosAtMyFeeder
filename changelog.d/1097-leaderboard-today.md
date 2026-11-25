- The Leaderboard has a **Today** period, counted from your local midnight, and its other
  periods now say what they count: Last 24 hours, Last 7 days, Last 30 days and All time (they
  were Day, Week, Month and Total). Seen, Heard, the photo wall, the charts and the heatmaps all
  count the same stretch. Today's trend compares with yesterday up to the same time, and is left
  out when a clock change makes the two different lengths. Early in the day the board says no
  visits have arrived yet, and a guest whose shared history starts after their midnight sees the
  time counting starts from. Links with `span=day` still open Last 24 hours; the API takes
  `span=today` ([docs/api.md](docs/api.md)) (part of #1097).
