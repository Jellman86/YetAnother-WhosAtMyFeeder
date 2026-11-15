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
- Finder checks tolerate score-floor jitter and full-frame/tile NMS survivor swaps.
  Settings uses stable failure codes and completed execution evidence, including
  verified GPU recovery when the saved NPU cannot run the model.
