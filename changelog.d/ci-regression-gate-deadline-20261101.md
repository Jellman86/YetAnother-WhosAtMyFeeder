- **The backend test gate allows ten minutes instead of eight for application tests.** Nothing
  changes for someone at their feeder. On GitHub-hosted runners the application lane took
  297 to 450 seconds across eleven recent runs, and one slower runner timed out at 480
  seconds with 93% of the tests finished and nothing hung. Ten minutes still stops a real
  teardown hang well inside the CI job's limit, and a test now keeps the deadline there.
