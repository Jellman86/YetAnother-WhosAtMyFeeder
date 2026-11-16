"""Work in progress on a model, as the server knows it: the one authority every tab reads."""

import pytest

from app.services.model_activity import GARDEN_CHECK_MODEL, ModelActivity


def test_nothing_is_in_progress_until_something_starts():
    assert ModelActivity().phases({}) == {}


def test_a_download_the_model_manager_reports_is_downloading():
    activity = ModelActivity()

    assert activity.phases({"small_birds": "downloading", "rope": "pending"}) == {
        "small_birds": "downloading",
        "rope": "downloading",
    }


def test_a_download_that_ended_is_no_longer_in_progress():
    assert ModelActivity().phases({"small_birds": "completed", "rope": "error"}) == {}


def test_a_validation_is_in_progress_only_while_it_runs():
    activity = ModelActivity()

    with activity.working("small_birds", "validating"):
        assert activity.phases({}) == {"small_birds": "validating"}
    assert activity.phases({}) == {}


def test_work_that_fails_is_over():
    activity = ModelActivity()

    with pytest.raises(RuntimeError):
        with activity.working("small_birds", "validating"):
            raise RuntimeError("probe crashed")
    assert activity.phases({}) == {}


def test_two_pieces_of_work_on_one_model_end_one_at_a_time():
    activity = ModelActivity()

    with activity.working(GARDEN_CHECK_MODEL, "downloading"):
        with activity.working(GARDEN_CHECK_MODEL, "downloading"):
            assert activity.phases({}) == {GARDEN_CHECK_MODEL: "downloading"}
        assert activity.phases({}) == {GARDEN_CHECK_MODEL: "downloading"}
    assert activity.phases({}) == {}


def test_a_download_is_said_before_a_check_on_the_same_model():
    activity = ModelActivity()

    with activity.working("small_birds", "validating"):
        assert activity.phases({"small_birds": "downloading"}) == {"small_birds": "downloading"}
