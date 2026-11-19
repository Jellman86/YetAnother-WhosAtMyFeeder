- **You can choose how far apart captures can be and still count as one visit.** On a busy
  feeder, birds of one species that come back every few seconds were all merged into one long
  visit by the fixed 60-second gap. **Settings → Identifying birds → Counting visits** now sets
  the gap, from 5 to 300 seconds (60 by default), or `VISITS__GAP_SECONDS` in the environment.
  The Dashboard, Explorer, Leaderboard, statistics and Garden animal visits all group with it,
  for guests as well as the owner, from the next page you open, with no restart. A shorter gap
  splits a busy feeder into more, shorter visits, but it cannot count individual birds. Days
  already kept as daily totals keep the visit counts they were saved with. `/api/visits` reports
  the gap it used in `gap_seconds`, and `/api/settings/public` carries `visit_gap_seconds`
  ([docs/api.md](docs/api.md)). Thanks to @darkslen1 for the request.
