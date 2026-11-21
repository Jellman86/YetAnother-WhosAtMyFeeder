- **Audio History's calls grid can show one species.** Above "Calls heard by hour and weekday"
  sits the same row of species chips as the Leaderboard's activity grid: All species, then the
  five species heard most in the window. Choosing one shows when that species calls, under the
  page's window, source and confidence filters. A species not heard in a new window goes back to
  All species, and while the page is filtered to a species the row is not shown, because the grid
  already follows that search.
- `GET /api/audio/activity-heatmap` takes an optional `scientific_name` that limits the grid to
  one species exactly, and each `top_species` row of `GET /api/audio/summary` now carries its
  `scientific_name`. See [the API reference](docs/api.md).
