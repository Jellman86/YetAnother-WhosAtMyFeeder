- **Backend tests now fail when they leave a connection open or a clock patched.** Nothing
  changes for someone at their feeder. After every test, the suite fails it if it left an
  aiosqlite connection running or a process-wide clock or sleep patched, and names what
  leaked. That found a test whose fake clock outlived it and made unrelated Garden checks
  fail or hang when run after it, and three tests that left a five-connection pool open. All
  are fixed. Seventeen copies of the same pool fixture became one shared `history_pool`
  fixture. See [the testing guide](docs/development/testing.md#normal-gate).
