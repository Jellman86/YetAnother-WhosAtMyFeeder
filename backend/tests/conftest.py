"""Pytest configuration and fixtures for all tests.

Tests under `tests/pure/` exercise decision logic only. They get the private
paths every test gets, but no migrated database, and `tests/pure/conftest.py`
overrides the application-state fixtures below with no-ops, so running them
alone neither migrates a schema nor imports the FastAPI app. Every other test
runs against the application and gets both.
"""

import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import closing
from pathlib import Path

import pytest
import pytest_asyncio

from tests.model_fixture_support import group_model_cases
from tests.pure_lane import PURE_ONLY_SESSION, is_pure_test

BACKEND_DIR = Path(__file__).parent.parent.resolve()

_suite_dir: Path | None = None
_history_template: Path | None = None


def pytest_collection_modifyitems(items):
    group_model_cases(items)


def _make_aiosqlite_threads_daemon() -> None:
    """Force aiosqlite connection worker threads to be daemon threads.

    aiosqlite runs each connection on a dedicated worker thread. Across the suite,
    connections are opened on many short-lived (pytest-asyncio) event loops and are
    not always closed before their loop goes away, leaving non-daemon worker threads
    alive. Those threads then block interpreter shutdown *after* the tests have
    already passed, hanging CI until the `timeout` wrapper kills the run (exit 124).
    Marking the threads daemon lets the process exit promptly once testing is done;
    the temporary test database is discarded regardless.
    """
    import aiosqlite.core

    connection_cls = aiosqlite.core.Connection

    if hasattr(connection_cls, "start"):
        # aiosqlite < 0.20: Connection subclasses Thread, so it starts itself.
        original_start = connection_cls.start

        def start_as_daemon(self, *args, **kwargs):
            self.daemon = True
            return original_start(self, *args, **kwargs)

        connection_cls.start = start_as_daemon
    else:
        # aiosqlite >= 0.20: Connection composes a worker Thread as self._thread.
        # Mark it daemon right after construction, before it is started in _connect().
        original_init = connection_cls.__init__

        def init_with_daemon_thread(self, *args, **kwargs):
            original_init(self, *args, **kwargs)
            worker = getattr(self, "_thread", None)
            if worker is not None:
                worker.daemon = True

        connection_cls.__init__ = init_with_daemon_thread


def pytest_configure(config):
    """Point every path the application reads at a private directory before any test module imports it."""
    global _suite_dir
    _make_aiosqlite_threads_daemon()

    _suite_dir = Path(tempfile.mkdtemp(prefix="yawamf_test_"))
    os.environ["MEDIA_CACHE_DIR"] = str(_suite_dir / "media_cache")
    os.environ["DATA_DIR"] = str(_suite_dir / "data")
    os.environ["CONFIG_DIR"] = str(_suite_dir / "config")
    os.environ["CONFIG_FILE"] = str(_suite_dir / "config" / "config.json")
    os.environ["DB_PATH"] = str(_suite_dir / "test_speciesid.db")
    for directory in ("MEDIA_CACHE_DIR", "DATA_DIR", "CONFIG_DIR"):
        Path(os.environ[directory]).mkdir(parents=True, exist_ok=True)

    # Alembic's env.py imports `app`, so the backend must be importable.
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))


def pytest_collection_finish(session):
    """Migrate the suite database once, and only when a collected test runs against the application."""
    pure_only = bool(session.items) and all(is_pure_test(item.path) for item in session.items)
    session.config.stash[PURE_ONLY_SESSION] = pure_only
    if session.config.option.collectonly or pure_only or not session.items:
        return
    _migrate_suite_database()


def _migrate_suite_database() -> None:
    global _history_template
    db_path = Path(os.environ["DB_PATH"])
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(BACKEND_DIR),
        env={**os.environ, "PYTHONPATH": str(BACKEND_DIR), "DB_PATH": str(db_path)},
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        # Every test then runs against an empty database and reports "no such
        # table", which buries the one real cause under hundreds of downstream
        # errors. Stop here and say what actually failed.
        raise RuntimeError(
            "Could not build the test database schema, so the suite cannot run.\n"
            f"`alembic upgrade head` exited {result.returncode}.\n\n"
            f"{result.stderr.strip()}\n\n"
            "A 'Multiple head revisions are present' error here usually means a "
            "duplicated migration file, such as a file-sync copy named "
            "'<revision> 2.py', is sitting in migrations/versions. Those are "
            "git-ignored but Alembic still reads them off disk."
        )
    # Taken before any test writes, so every copy starts from the same empty schema at head.
    _history_template = db_path.with_name("history_schema_at_head.db")
    with closing(sqlite3.connect(db_path)) as source, closing(sqlite3.connect(_history_template)) as target:
        source.backup(target)
    # Tells app.database.init_db that the schema is already at head.
    os.environ["YA_WAMF_TEST_DB_INITIALIZED"] = "1"


def pytest_unconfigure(config):
    if _suite_dir is not None:
        shutil.rmtree(_suite_dir, ignore_errors=True)


@pytest.fixture
def migrated_history_db(tmp_path) -> Path:
    """A private history database at the head revision, copied rather than migrated again.

    For tests that inspect the schema or seed their own rows. Tests about a
    migration itself must still run the real upgrade and downgrade chain.
    """
    if _history_template is None:
        pytest.fail("The suite database was not migrated; pure tests cannot use a history database.")
    path = tmp_path / "speciesid.db"
    shutil.copyfile(_history_template, path)
    return path


@pytest.fixture(autouse=True)
def isolate_config_hostname_resolution(monkeypatch):
    """Configuration tests must not depend on host DNS or Docker service names."""
    import socket

    def unresolved(_hostname):
        raise socket.gaierror("No external DNS in unit tests")

    monkeypatch.setattr(socket, "gethostbyname_ex", unresolved)


@pytest.fixture(autouse=True)
def enable_garden_beta_for_garden_tests(request, monkeypatch):
    """Garden is a beta feature that defaults off; its own tests exercise it switched on."""
    if "garden" in request.node.path.name:
        from app.config import settings

        monkeypatch.setattr(settings.system, "beta_garden_animals", True)


@pytest.fixture(autouse=True)
def disable_rate_limiting():
    """Disable rate limiting for all tests by default."""
    from app.ratelimit import limiter

    old_enabled = limiter.enabled
    limiter.enabled = False
    yield
    limiter.enabled = old_enabled


@pytest.fixture(autouse=True)
def restore_media_storage_availability():
    """Tests that need storage to be unwritable set the media cache unavailable; it must not
    leak, because photographs are always kept now (#622) and every later test relies on them."""
    from app.services.media_cache import media_cache

    available = media_cache._available
    yield
    media_cache._available = available


@pytest.fixture(autouse=True)
def clear_species_alias_cache_between_tests():
    """Each test owns its rows; a cached alias set from another test's data
    would leak across the per-test DELETE."""
    from app.repositories.detection_repository import clear_species_alias_cache

    clear_species_alias_cache()
    yield
    clear_species_alias_cache()


@pytest_asyncio.fixture(autouse=True)
async def cleanup_async_singletons():
    yield
    from app.services.notification_dispatcher import notification_dispatcher

    await notification_dispatcher.stop()


async def rollup_counts_by_display_name(repo, days: int = 7) -> dict[str, int]:
    """Detections per display name in the daily rollup, read straight from it.

    Tests that check `ensure_recent_rollups` want to know the rollup was
    populated, so they read the table. Routing that through a repository method
    kept a second, name-keyed way of reading rollups alive purely for tests,
    long after production had moved to the leaderboard's unified key.
    """
    query = (
        "SELECT display_name, SUM(detection_count) FROM species_daily_rollup"
        f" WHERE rollup_date >= date('now', '-{int(days)} day') GROUP BY display_name"
    )
    async with repo.db.execute(query) as cursor:
        rows = await cursor.fetchall()
    return {str(row[0]): int(row[1] or 0) for row in rows}
