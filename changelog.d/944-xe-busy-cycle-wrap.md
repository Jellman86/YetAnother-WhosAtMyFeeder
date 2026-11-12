- Fixes the Intel GPU reading on the xe driver sinking towards zero after a while, even
  when the GPU was busy (#944). xe's busy counter for each client wraps at 2^32 cycles,
  and every client that wrapped had stopped counting. YA-WAMF now follows a busy counter
  through the wrap and counts the work done across it. When that work can't be bounded by
  the clock interval beside it, YA-WAMF leaves that one interval unmeasured instead of
  guessing. Support bundles mark these samples `counter_wrapped`, so they're no longer
  shown as `counter_regressed`.
