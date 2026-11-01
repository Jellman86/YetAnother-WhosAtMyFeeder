"""Hold pure tests to their contract, so a test that needs application resources says so by moving out.

A pure test passes inputs in and checks outputs. It must not open a database or
build the FastAPI app; either belongs in `backend/tests/`, which migrates the
suite database and restores application singletons around every test.
"""

import sqlite3
import sys

import aiosqlite
import pytest

from tests.pure_lane import PURE_ONLY_SESSION

_MOVE_OUT = "Pure tests may not {}; move this test to backend/tests/, which provides application resources."


@pytest.fixture(autouse=True)
def refuse_database_connections(monkeypatch):
    def refuse(*_args, **_kwargs):
        raise AssertionError(_MOVE_OUT.format("open a database"))

    monkeypatch.setattr(sqlite3, "connect", refuse)
    monkeypatch.setattr(aiosqlite, "connect", refuse)


@pytest.fixture(autouse=True)
def refuse_application_import(request):
    # Another test in a mixed session may already have imported the app, so
    # this can only be judged when nothing but pure tests runs in the process.
    judged = request.config.stash.get(PURE_ONLY_SESSION, False)
    if judged and "app.main" in sys.modules:
        pytest.fail(_MOVE_OUT.format("import app.main, as a module collected before this test did"))
    yield
    if judged and "app.main" in sys.modules:
        pytest.fail(_MOVE_OUT.format("import app.main"))


# The suite conftest restores application singletons around every test. Pure
# tests touch none of them, so these same-named fixtures replace that work here:
# no app modules imported for it, and no event loop opened for a synchronous test.


@pytest.fixture
def enable_garden_beta_for_garden_tests():
    pass


@pytest.fixture
def disable_rate_limiting():
    pass


@pytest.fixture
def restore_media_storage_availability():
    pass


@pytest.fixture
def clear_species_alias_cache_between_tests():
    pass


@pytest.fixture
def cleanup_async_singletons():
    pass
