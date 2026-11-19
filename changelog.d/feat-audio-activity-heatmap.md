- **Audio history shows calls heard by weekday and hour.** The "Time of day" bar chart is replaced
  by the Leaderboard's activity grid, counting calls heard rather than captures, in your own time
  zone. It follows the page's window and filters, so its total always matches the "Calls heard"
  figure, and its data is a table under "Show the data as a table". The busiest hour figure now
  comes from the same grid, so it is your local hour; before, it was the hour in UTC.
- **Audio history reads like the Leaderboard.** The window sits at the top as the same segmented
  bar (a select on a phone) and applies as soon as you choose it; species, source and confidence
  still wait for Apply, and Clear leaves the window as it is. The figures strip, the Analytics
  heading with its dates, and the chart order, frames and captions now match the Leaderboard's,
  and every figure says "calls heard". On a phone the figures now come before the call list, as
  the Leaderboard's do. If only the grid cannot be read, it says so with Retry and the list stays.
- **New endpoint:** `GET /api/audio/activity-heatmap` counts calls heard by weekday and hour over
  the same window and filters as `GET /api/audio/summary`, with the same guest rules
  ([API reference](docs/api.md)).
