- **Health stops listing expected events as problems.** A snapshot Frigate no longer has, because
  it discarded the object after announcing it, is logged once per event at info and counted in
  `event_pipeline.snapshot_not_found_events` instead of three to five warnings. An event every
  fallback fails for is still recorded as lost.
  - One Garden motion recording that falls back to CPU decoding and recovers on the next is
    information. A second fallback in a row is the `hardware_decode_fallback_repeated` warning,
    and 3 fallbacks in the last 10 GPU decodes, even with recoveries between them, is the
    `hardware_decode_fallback_frequent` warning. The third in a row still switches GPU decode off,
    as before.
  - A Frigate restart blip is shown in incident history as resolved once Frigate reports it is
    online again. An outage stays open while Frigate is offline or its availability is unknown.
  - A slow database hold taken through the guest privacy check now names the route that held it,
    rather than the check, so the warning points at the code to fix
    ([docs/troubleshooting/slow-interface.md](docs/troubleshooting/slow-interface.md)).
