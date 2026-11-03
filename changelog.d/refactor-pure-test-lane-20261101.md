- **Pure backend tests now run on their own, without a database or the app.** Nothing
  changes for someone at their feeder. 126 decision-logic test files moved to
  `backend/tests/pure`, which neither migrates the suite database nor imports the FastAPI
  app; its conftest fails a test that opens a database or imports `app.main`. The backend
  gate runs that lane first in its own process, then every other test, and combines their
  coverage. The suite database is now migrated once, after collection, and only when an
  application test is collected, and the suite's temporary directory is removed at exit.
  Schema checks and four integration modules copy that freshly migrated database instead
  of running Alembic again. See [the testing guide](docs/development/testing.md#normal-gate).
