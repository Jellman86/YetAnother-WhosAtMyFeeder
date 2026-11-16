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


@pytest.mark.parametrize("error", [FRIGATE_NOT_READY, "event_request_error"])
def test_a_frigate_that_could_not_be_reached_is_unreachable_not_gone(error):
    assert classify_event_check(None, error) == "unreachable"


def test_a_frigate_that_did_not_answer_in_time_timed_out():
    assert classify_event_check(None, "event_timeout") == "timed_out"


@pytest.mark.parametrize("error", ["event_http_500", "event_http_401", "event_unknown_error", None, ""])
def test_any_other_failure_is_a_failed_check_never_an_absence(error):
    assert classify_event_check(None, error) == "failed"
