- Keep a working CPU fallback eligible when a bird finder accelerator check fails,
  and automatically recheck a saved accelerator after runtime changes even if an
  earlier check erased its eligibility. Checks now use RF-DETR's full frame and
  tiles and match every admitted bird independently of score order. The status API
  retains historical failures with their date and runtime freshness, and finder
  checks log box differences for diagnosis.
- RF-DETR now prefers NPU, then a verified GPU, before CPU. Automatic checks try
  GPU if NPU fails and stop early when NPU passes. Any RF-DETR CPU use produces a
  structured warning and an actionable Health incident counted in System status.
  CPU detector threads and provider-check priority are bounded to reduce load.
