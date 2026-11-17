- The Leaderboard's chart and each species' weekday and month charts now keep their history after
  cleanup deletes old captures (#949). Before cleanup, scheduled or **Purge Old Records**, removes
  any capture from a day, it writes that day's captures and visits per species and seals the day;
  charts count sealed days from those totals, so seasonal trends reach back past your retention
  period. If the totals cannot be saved, nothing is deleted and Health says "Retention paused". A
  capture deleted because Frigate no longer has it keeps its count, and its day stays live. The
  chart says from which day its counts come from daily totals, since the photos and clips for
  those days are gone, and the hour-and-weekday grid says older days have no time of day. A
  sealed day keeps its totals even if you later hide or delete one of its few kept captures, and
  **Delete all history** deletes the totals too. Totals start when you upgrade: days that began
  before then are marked as possibly low. Downgrading below this release deletes the daily totals
  for good. See [Daily totals](docs/features/favourites.md#daily-totals-keep-the-counts).
