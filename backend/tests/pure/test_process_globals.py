import time

from tests import process_globals


def test_a_clock_left_patched_is_named_and_put_back():
    originals = process_globals.snapshot()
    real_time = time.time
    time.time = lambda: 0.0
    try:
        assert process_globals.restore_leaked(originals) == ["time.time"]
        assert time.time is real_time
    finally:
        time.time = real_time


def test_untouched_globals_report_nothing():
    assert process_globals.restore_leaked(process_globals.snapshot()) == []
