"""Errors only when there are actual errors.

The production log carried three kinds of noise at the wrong level: expected
Frigate states (a clip it never stored) as warnings, real worker crash
tracebacks relayed at info, and the nested-DB-acquire detector naming only the
inner acquirer - repeating itself without saying who held the connection.
"""

import inspect

from app.services.classifier_worker_client import classify_worker_stderr_severity


def test_worker_stderr_severity_reflects_content():
    # Real faults surface as warnings - a traceback at info hides a crash.
    assert classify_worker_stderr_severity("Traceback (most recent call last):") == "warning"
    assert classify_worker_stderr_severity("ValueError: Separator is not found") == "warning"
    assert classify_worker_stderr_severity("  raise ValueError(e.args[0])") == "warning"
    # Known runtime banners are debug: they say a worker started, nothing more.
    assert (
        classify_worker_stderr_severity(
            "WARNING: All log messages before absl::InitializeLog() is called are written to STDERR"
        )
        == "debug"
    )
    # Anything else stays visible at info.
    assert classify_worker_stderr_severity("loading model catalogue") == "info"


def test_expected_frigate_absences_are_not_warnings():
    from app.services import frigate_client

    source = inspect.getsource(frigate_client.FrigateClient.get_clip_with_error)
    assert 'log.info("Clip not found"' in source
    assert 'log.info("Clip recordings not retained"' in source
    assert 'log.warning("Clip not found"' not in source


def test_nested_acquire_warning_names_the_holder_and_says_it_once():
    import app.database as database

    source = inspect.getsource(database.DatabasePool.acquire)
    assert "outer_held_by=" in source
    # Each unique (holder, nested) pair warns once per process; the counter
    # still counts every occurrence for the stats endpoint.
    assert "_nested_acquire_warned" in source
    get_db_source = inspect.getsource(database.get_db)
    assert "_acquire_label" in get_db_source
