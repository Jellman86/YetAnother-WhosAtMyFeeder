- **Audio History has a Today window.** Choose **Today** to see the calls heard since your local
  midnight. The page does not follow new calls as they are heard: when nothing has been heard yet it
  says "No calls heard yet today. Select Refresh to check for new calls." If the page is left open,
  it reads the new day at midnight. The windows now use the same names as the rest of the app: **Last
  24 hours**, **Last 7 days**, **Last 30 days** (still the default), **Last 90 days** and **Last 365
  days**. The list, the figures and the calls grid all count the same instants, and the dates beside
  the window's name only appear once that window has been read. When a guest's shared history starts
  later than their midnight, the page says from what time it is shown.
- **Calls over time are counted on your own calendar.** Audio History's daily chart used to file
  calls by UTC date, so near midnight a call could appear under yesterday or tomorrow. Each call is
  now counted on the date it was heard in your time zone. `GET /api/audio/summary` also reports the
  `window_start` and `window_end` it counted (#1097).
