- **Health no longer fails on a busy feeder.** `/health` and the diagnostics workspace
  could answer HTTP 500 with "deque mutated during iteration" while detections were
  arriving, which the Health page, external monitors and the container healthcheck all
  saw as errors. The report had started reading the services' live state from a worker
  thread while the event loop was changing it. That state is now read on the event
  loop, and only the report's file, SQLite and `/proc` reads stay in a worker thread.
  The same applies to the classifier status behind Settings, the setup wizard and the
  live status stream. Two quieter effects of the same race are gone too: a health read
  could drop a running photo worker from tracking, and could leave the worker pools
  out of the classifier status.
