- The Leaderboard's chart and each species' weekday and month charts now keep their history after
  cleanup deletes old captures (#949). Just before cleanup removes any capture from a day, it
  writes that day's captures and visits per species and seals the day; charts count sealed days
  from those totals, so seasonal trends reach back past your retention period. The chart says
  from which day its counts come from daily totals, since the photos and clips for those days
  are gone. A sealed day keeps its totals even if you later hide or delete one of its few kept
  captures, and **Delete all history** deletes the totals too. Totals start when you upgrade:
  days whose older captures were already gone are marked incomplete. See
  [Daily totals](docs/features/favourites.md#daily-totals-keep-the-counts).
