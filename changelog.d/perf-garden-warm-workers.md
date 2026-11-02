- Garden checks and motion scans after the first one in a while are now much faster. SpeciesNet
  and the Cedar motion detector stay loaded between requests instead of starting a new process and
  loading the model each time. On an Intel NPU a check took about 13 seconds, of which inference
  was 1 to 2. Bird inference still comes first: the loaded model is released as soon as bird work
  is waiting, after 60 seconds without Garden work, and after any failed, interrupted or timed-out
  request. A different model or device always starts a fresh process, so the CPU comparison never
  shares a process with the accelerator it is checking.
