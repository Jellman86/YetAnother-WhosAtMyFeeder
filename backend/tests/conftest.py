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
import weakref
from contextlib import closing
from pathlib import Path

import aiosqlite.core
import pytest
import pytest_asyncio

from tests import process_globals
from tests.model_fixture_support import group_model_cases
from tests.pure_lane import PURE_ONLY_SESSION, is_pure_test

BACKEND_DIR = Path(__file__).parent.parent.resolve()

_suite_dir: Path | None = None
_history_template: Path | None = None


def pytest_collection_modifyitems(items):
    group_model_cases(items)


# Every aiosqlite connection the process opens, so a test that leaves one open can be named.
_aiosqlite_connections: "weakref.WeakSet[aiosqlite.Connection]" = weakref.WeakSet()
_OPEN_BEFORE_TEST = pytest.StashKey[set[int]]()


def _track_aiosqlite_connections() -> None:
    """Record every aiosqlite connection, and run its worker thread as a daemon.

    Each connection runs on a dedicated worker thread. A connection left open
    on a short-lived pytest-asyncio loop keeps a non-daemon thread alive, which
    blocks interpreter shutdown after the tests have passed and hangs CI until
    the gate's deadline. The teardown check below now fails the test that
    leaves one open; the daemon flag stays as a backstop until a run of the
    whole suite under that check has proved it unnecessary.
    """
    connection_cls = aiosqlite.core.Connection
    original_init = connection_cls.__init__

    def init_tracked_daemon(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self._thread.daemon = True
        _aiosqlite_connections.add(self)

    connection_cls.__init__ = init_tracked_daemon


def _running_aiosqlite_connections() -> set[int]:
    return {id(connection) for connection in list(_aiosqlite_connections) if connection._running}


def pytest_configure(config):
    """Point every path the application reads at a private directory before any test module imports it."""
    global _suite_dir
    _track_aiosqlite_connections()

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


# Taken at import, before any test could have patched them.
_REAL_PROCESS_GLOBALS = process_globals.snapshot()


@pytest.hookimpl(wrapper=True)
def pytest_runtest_setup(item):
    item.stash[_OPEN_BEFORE_TEST] = _running_aiosqlite_connections()
    return (yield)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_teardown(item, nextitem):
    """Fail the test that leaves a clock patched or a database connection open.

    Checked after every fixture has been torn down, because fixture teardown
    order does not follow the order patches and connections were made in. A
    leaked clock is also put back, so one leak cannot fail every later test.
    """
    result = yield
    leaked = process_globals.restore_leaked(_REAL_PROCESS_GLOBALS)
    if leaked:
        pytest.fail(f"This test left {', '.join(leaked)} patched for every later test in the process.")
    left_open = _running_aiosqlite_connections() - item.stash.get(_OPEN_BEFORE_TEST, set())
    if left_open:
        pytest.fail(
            f"This test left {len(left_open)} aiosqlite connection(s) open; close them, or take the"
            " `history_pool` fixture instead of calling init_db() directly."
        )
    return result


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


@pytest_asyncio.fixture
async def history_pool():
    """The application's connection pool on the suite database, opened and closed in this test's loop.

    A pool opened on one test's event loop and left for the next one is the
    leak the daemon-thread workaround above papers over; a test that needs the
    pool takes this fixture rather than calling `init_db()` itself.
    """
    from app.database import close_db, init_db

    await init_db()
    try:
        yield
    finally:
        await close_db()


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
