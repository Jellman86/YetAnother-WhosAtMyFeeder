- Backend regression checks no longer wait indefinitely when a CPU recovery test's
  request fails before reaching its worker. Checks name each running test, dump
  Python thread stacks after 110 seconds, and stop a stalled test after 120 seconds.
