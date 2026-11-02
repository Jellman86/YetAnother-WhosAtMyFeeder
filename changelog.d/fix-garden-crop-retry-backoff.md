- Garden no longer retries crops it cannot build every hour. A failed crop is retried after 1, 2,
  4, 8 and 16 hours, then once a day, which cuts the repeated "crop unavailable" log lines for old
  captures whose Frigate snapshots are past retention to one a day each. A crop is never
  abandoned, so one that failed during a Frigate outage is still built later.
