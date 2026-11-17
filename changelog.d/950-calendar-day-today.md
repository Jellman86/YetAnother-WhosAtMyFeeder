- The API can now return everything from today in one go (#950). `GET /api/events`,
  `GET /api/events/count` and `GET /api/visits` accept `start_date=today` and `end_date=today`,
  and `GET /api/stats/daily-summary?window=today` counts from local midnight instead of the
  last 24 hours (still the default). "Today", and any date you pass, is a calendar day in your
  zone: the browser's, which the web interface sends as `X-Timezone`, or for scripts and Home
  Assistant the container's `TZ` (UTC when it is unset). A bird at 23:30 local time is no longer
  counted on the next day; dates used to be read as UTC days. One `/api/visits` request now
  returns up to 500 visits (was 100) and asks Frigate about each visit's photo only;
  `/api/events` adds an `X-Next-Offset` header while more events remain, and captures saved in
  the same instant keep one order between pages. Guests can never see more than before.
  Timezone data now ships with every image, and a `TZ` that names no real zone is logged once.
  See [Calendar days](docs/api.md#calendar-days-and-today).
