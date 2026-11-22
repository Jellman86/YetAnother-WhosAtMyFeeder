- **The Leaderboard and the species list keep their counts after cleanup.** The ranked day, week
  and month boards and the all-time species list now count a day that cleanup sealed from its
  daily totals, as the charts already did, instead of from the few captures it kept, so a count no
  longer drops when old captures are removed. A day is counted once: its kept favourites are inside
  its total, not added to it. A rolling window that opens part way through a sealed day counts only
  the captures still stored from that day. A species seen only on sealed days keeps its place with
  no confidence or first and last sighting, because a daily total has neither. See
  [Daily totals keep the counts](docs/features/favourites.md#daily-totals-keep-the-counts).
- **Hours and weekdays follow your instance's time zone when a client sends none.** curl, Home
  Assistant and other scripts that send no `X-Timezone` header now get the daily summary's hour
  buckets, the timeline, both activity heatmaps, the species charts, custom backfill dates and the
  local time given to an AI analysis in the container's `TZ`, so they agree with the day they
  already got. Before, those hours were UTC. The web interface is unchanged: it sends the browser's
  zone. See [Calendar days and `today`](docs/api.md#calendar-days-and-today).
- **The history range limit is stated as the code applies it.** The end day may be up to 365 days
  after the start day, so a range holds a whole calendar year, leap years included.
- **The live classifier worker's hard deadline has one default, 35 seconds.** It is what has always
  applied; the settings model no longer declares a different 60 seconds. The unused `LOG_LEVEL`
  setting is gone.
- **Wording.** The Dashboard's checks link says "Open the checks on the Leaderboard", the Garden
  device note points to **Settings › Identifying birds › More options › Hardware**, and English
  spells "Favourite" one way throughout. The Intel GPU and NPU chips' "verified" and "unverified"
  are translated. The Unraid template says the media cache lives in `/config/media_cache`.
