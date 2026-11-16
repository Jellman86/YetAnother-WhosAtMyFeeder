"""What YA-WAMF learned when it asked Frigate about an event.

The record used to say "Frigate no longer has this event or media" whenever the
answer was not "here it is", including when Frigate was down and nothing had
been learned at all. Only a 404 is evidence that the event is gone; every other
failure is a question that went unanswered, and the record must be able to say
which one.
"""

import pytest

from app.services.frigate_event_check import classify_event_check
from app.services.frigate_readiness import FRIGATE_NOT_READY


def test_an_event_frigate_returned_is_found():
    assert classify_event_check({"id": "evt"}, None) == "found"


def test_only_a_not_found_answer_says_the_event_is_gone():
    assert classify_event_check(None, "event_not_found") == "not_found"


def test_a_connection_that_could_not_be_made_is_unreachable_not_gone():
    assert classify_event_check(None, "event_request_error") == "unreachable"
    assert classify_event_check(None, FRIGATE_NOT_READY, "connection") == "unreachable"


def test_a_frigate_that_did_not_answer_in_time_timed_out():
    assert classify_event_check(None, "event_timeout") == "timed_out"
    assert classify_event_check(None, FRIGATE_NOT_READY, "timeout") == "timed_out"


def test_a_server_error_behind_a_closed_gate_is_a_failed_check_not_unreachable():
    assert classify_event_check(None, FRIGATE_NOT_READY, "server_error") == "failed"


def test_a_read_put_off_for_a_cause_nobody_recorded_says_only_that_it_was_not_checked():
    assert classify_event_check(None, FRIGATE_NOT_READY) == "not_checked"


@pytest.mark.parametrize("error", ["event_http_401", "event_http_403"])
def test_refused_credentials_are_their_own_cause(error):
    assert classify_event_check(None, error) == "unauthorized"


@pytest.mark.parametrize("error", ["event_http_500", "event_http_418", "event_unknown_error", None, ""])
def test_any_other_failure_is_a_failed_check_never_an_absence(error):
    assert classify_event_check(None, error) == "failed"
