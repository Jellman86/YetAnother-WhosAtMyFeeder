- Garden checks and motion scans in a burst are now much faster. SpeciesNet and the Cedar motion
  detector can stay loaded between requests instead of starting a new process and loading the model
  each time. On an Intel NPU a check took about 13 seconds, of which inference was 1 to 2. Bird
  inference still comes first: an accelerator model leaves its device, and its process has exited,
  before Garden lets other work start, unless another automatic check is already due and no bird
  work is waiting. A model on CPU is released after 60 seconds without Garden work. Any model is
  released as soon as bird work is waiting, after any failed, interrupted or timed-out request, and
  after 500 requests. A different model or device always starts a fresh process, so the CPU
  comparison never shares a process with the accelerator it is checking.
