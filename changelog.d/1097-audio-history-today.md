- **Audio History has a Today window.** Choose **Today** to see the calls heard since your local
  midnight; the page reads the new day on its own at midnight and says "No calls heard yet today"
  until the first call arrives. The windows now use the same names as the rest of the app: **Last 24
  hours**, **Last 7 days**, **Last 30 days** (still the default), **Last 90 days** and **Last 365
  days**. The list, the figures and the calls grid all count the same instants. When a guest's shared
  history starts later than their midnight, the page says so. `GET /api/audio/summary` now reports
  the `window_start` and `window_end` it counted (#1097).
