- Updates the backend's Python dependencies to their latest patch and minor releases: pydantic
  2.14.2, pydantic-settings 2.16.2, alembic 1.20.1, and the development tools pytest 9.2.0,
  pytest-asyncio 1.4.1, coverage 7.17.0 and ruff 0.17.3. FastAPI stays at 0.143.2 for now.
- The classifier router's live proxy now forwards attribute deletion to the current classifier,
  as it already did for reads and writes, so a patch undone by deletion no longer outlives it.
