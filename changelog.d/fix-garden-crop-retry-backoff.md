- Garden no longer retries crops it can never build every hour, forever. A failed crop is retried
  after 1, 2, 4, 8 and 16 hours, then left without a crop, which stops the repeated "crop
  unavailable" log lines for old captures whose Frigate snapshots are past retention.
