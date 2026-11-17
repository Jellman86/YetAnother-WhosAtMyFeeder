- The API can now return everything from today in one go (#950). `GET /api/events`,
  `GET /api/events/count` and `GET /api/visits` accept `start_date=today` and `end_date=today`,
  and `GET /api/stats/daily-summary?window=today` counts from local midnight instead of the
  last 24 hours (still the default). "Today", and any date you pass, is the calendar day in the
  instance's timezone (the container's `TZ`, or UTC when it is unset), so a bird at 23:30 local
  time is no longer counted on the next day. A day's dates used to be read as UTC days. One
  `/api/visits` request now returns up to 500 visits (was 100), and `/api/events` adds an
  `X-Next-Offset` header while more events remain, so clients no longer guess when to stop
  paging. Guests keep exactly the history window they had. See
  [Calendar days](docs/api.md#calendar-days-and-today).
