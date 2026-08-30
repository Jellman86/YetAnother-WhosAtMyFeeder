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


def test_worker_stderr_severity_keeps_tensorflow_faults_visible():
    # TensorFlow's own error lines carry the file path all its chatter does;
    # only the informational severity letters are noise. An E/F line is a
    # real fault and must never be demoted to debug.
    assert (
        classify_worker_stderr_severity(
            "E tensorflow/core/framework/op_kernel.cc:1616] OP_REQUIRES failed at gather_op.cc:161 : "
            "INVALID_ARGUMENT: indices[0,0,0] = 5 is not in [0, 4)"
        )
        == "warning"
    )
    assert classify_worker_stderr_severity("F tensorflow/core/util/some_check.cc:99] check failed") == "warning"
    assert (
        classify_worker_stderr_severity(
            "I0000 00:00:1788107191.829092 199 cpu_feature_guard.cc:227] I tensorflow/core banner"
        )
        == "debug"
    )
    # A buffer mixing banner chatter with a crash surfaces as a warning.
    assert (
        classify_worker_stderr_severity(
            "I tensorflow/core/platform/cpu_feature_guard.cc:210] oneDNN is on\n"
            "Traceback (most recent call last):\n  raise RuntimeError('boom')"
        )
        == "warning"
    )


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
