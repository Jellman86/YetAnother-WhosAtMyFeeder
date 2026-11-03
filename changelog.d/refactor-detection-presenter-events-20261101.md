- **The event list and visit captures now share one bird presenter.** Nothing changes for
  someone at their feeder. How a stored detection becomes what the owner or a guest sees
  (names in their language, nearby heard species, approximate locations, hidden cameras,
  and the owner-only diagnostics a guest never receives) moved from the events router
  into `services/detection_presenter.py`. A test compares the event list, visits, visit
  captures, the daily summary and species detail, for the owner and for a guest with
  and without shared audio, in English and German, with responses captured before the
  move.
