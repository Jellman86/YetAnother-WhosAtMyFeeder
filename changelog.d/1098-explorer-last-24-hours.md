- The field log's "earlier visits in the last 24 hours, open in Explorer" line now opens the
  Explorer on those same 24 hours instead of all time (#1098). The Explorer has a new "Last 24
  hours" choice under When, and the link names the visitors the log showed, birds alone or birds
  with Garden, so a device last left on Garden alone still shows the visits the line counted.
  "See full history" in the log's header still opens the whole history.
- `GET /api/events` and `GET /api/events/count` accept exact `start_time` and `end_time`
  instants, as `GET /api/visits` already did. They outrank `start_date` and `end_date`, include
  both bounds, and stay inside a guest's shared window. See [the API reference](docs/api.md).
- Exact `start_time` and `end_time` on the events, count and visit endpoints must now be an ISO
  8601 date and time with an offset (`Z` or `±HH:MM`). A date alone, a time with no offset, a Unix
  timestamp, an out-of-range part such as `+01:60`, or a time with no UTC date is refused with
  `422`; an end before the start, or more than 365 days after it, with `400`.
