- Keep a working CPU fallback eligible when a bird finder accelerator check fails,
  and automatically recheck a saved accelerator after runtime changes even if an
  earlier check erased its eligibility. Checks now use RF-DETR's full frame and
  tiles and match every admitted bird independently of score order. The status API
  retains historical failures with their date and runtime freshness, and finder
  checks log box differences for diagnosis.
- RF-DETR now prefers NPU, then a verified GPU, before CPU. Automatic checks try
  GPU if NPU fails and stop early when NPU passes. Unchosen RF-DETR CPU use on
  hosts offering an Intel accelerator produces a structured warning and an actionable
  Health incident counted in System status. Only disposable provider probes cap CPU
  threads and run at reduced priority. Interrupted or unfinished checks retry with
  capped backoff; inconclusive checks preserve previous passing evidence.
- Finder checks tolerate score-floor jitter and full-frame/tile NMS survivor swaps,
  including chained groups where one device keeps two overlapping boxes and the
  other keeps one. A check with no birds in the CPU baseline reruns on a changed
  photo set at most every four hours. The Settings finder card names the backend's
  planned device for the running finder.
  Settings uses stable failure codes and completed execution evidence, including
  verified GPU recovery when the saved NPU cannot run the model.
- Automatic finder checks no longer spend power proving nothing. An Intel image on
  a host without an NPU or GPU never runs a CPU-only sweep, and a sweep that opened
  no accelerator is final instead of retrying as "could not finish". RF-DETR stops
  after an unusable CPU baseline instead of compiling the NPU and GPU, never probes
  OpenVINO CPU, and an empty baseline backs off from four hours to once a day. An
  owner-run Check devices is recorded so the automatic check does not repeat it.
- Finder checks no longer pass two surviving boxes that only share a suppressed
  neighbour, and report the survivors' own overlap.
- An Intel CPU (OpenVINO) choice no longer raises the CPU Health incident. A check
  that passed after the last frame clears it without waiting for the next bird,
  one ongoing CPU condition is one incident, and a damaged check record says to run
  Check devices instead of promising a retry.
