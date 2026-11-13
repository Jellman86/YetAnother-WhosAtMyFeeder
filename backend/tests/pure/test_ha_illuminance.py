"""A Home Assistant lux sensor is untrusted input (#945).

The contract under test: only a numeric illuminance reading in lx is a light
level. Anything else is missing data with a stated reason, and nothing is
ever derived from the time of day or the cloud cover to fill the gap.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.services.ha_weather import (
    ILLUMINANCE_MAX_LUX,
    illuminance_at_detection,
    is_entity_id,
    read_illuminance,
    valid_illuminance_lux,
)


def _sensor(state, **attributes):
    return {"state": state, "attributes": attributes}


def test_lux_sensor_with_the_illuminance_device_class_is_measured():
    reading = read_illuminance(_sensor("1240.5", device_class="illuminance", unit_of_measurement="lx"))
    assert reading.lux == pytest.approx(1240.5)
    assert reading.reason is None


def test_lx_unit_alone_is_enough():
    assert read_illuminance(_sensor("0", unit_of_measurement="lx")).lux == 0.0
    assert read_illuminance(_sensor(88, unit_of_measurement=" LX ")).lux == pytest.approx(88.0)


def test_illuminance_device_class_without_a_unit_is_accepted():
    assert read_illuminance(_sensor("52", device_class="illuminance")).lux == pytest.approx(52.0)


@pytest.mark.parametrize(
    "payload",
    [
        _sensor("21.5", device_class="temperature", unit_of_measurement="°C"),
        _sensor("40", unit_of_measurement="%"),
        _sensor("300", attributes_missing=True),
        # A device class cannot vouch for a value scaled in another unit.
        _sensor("1.2", device_class="illuminance", unit_of_measurement="klx"),
        {"state": "sunny", "attributes": {"temperature": 12}},
    ],
)
def test_another_kind_of_entity_is_rejected_and_says_so(payload):
    reading = read_illuminance(payload)
    assert reading.lux is None
    assert reading.reason == "not_illuminance"


@pytest.mark.parametrize("state", ["unknown", "unavailable", "Unavailable", "", None, "none"])
def test_unknown_and_unavailable_are_missing_data(state):
    reading = read_illuminance(_sensor(state, device_class="illuminance", unit_of_measurement="lx"))
    assert reading.lux is None
    assert reading.reason == "unavailable"


@pytest.mark.parametrize("state", ["bright", "12 lx", "1,240", [1], {"value": 3}, True])
def test_a_state_that_is_not_a_number_is_missing_data(state):
    reading = read_illuminance(_sensor(state, device_class="illuminance", unit_of_measurement="lx"))
    assert reading.lux is None
    assert reading.reason == "not_numeric"


@pytest.mark.parametrize("state", ["-1", "nan", "inf", "-inf", str(ILLUMINANCE_MAX_LUX + 1), "1e12"])
def test_a_value_no_light_sensor_can_report_is_missing_data(state):
    reading = read_illuminance(_sensor(state, device_class="illuminance", unit_of_measurement="lx"))
    assert reading.lux is None
    assert reading.reason == "out_of_range"


def test_the_range_ends_are_measurements():
    assert read_illuminance(_sensor("0", unit_of_measurement="lx")).lux == 0.0
    assert read_illuminance(_sensor(str(ILLUMINANCE_MAX_LUX), unit_of_measurement="lx")).lux == ILLUMINANCE_MAX_LUX


@pytest.mark.parametrize("payload", [None, [], "sensor", 5])
def test_a_missing_or_malformed_answer_is_unreachable(payload):
    reading = read_illuminance(payload)
    assert reading.lux is None
    assert reading.reason == "unreachable"


def test_attributes_of_the_wrong_shape_do_not_raise():
    reading = read_illuminance({"state": "12", "attributes": "lx"})
    assert reading.lux is None
    assert reading.reason == "not_illuminance"


@pytest.mark.parametrize(
    "value, expected",
    [
        (1240.5, 1240.5),
        (0, 0.0),
        ("300", 300.0),
        (ILLUMINANCE_MAX_LUX, ILLUMINANCE_MAX_LUX),
        (None, None),
        (-0.1, None),
        (ILLUMINANCE_MAX_LUX + 0.1, None),
        (float("nan"), None),
        (float("inf"), None),
        ("bright", None),
        (True, None),
    ],
)
def test_only_a_finite_value_in_range_may_be_stored(value, expected):
    assert valid_illuminance_lux(value) == expected


@pytest.mark.parametrize(
    "entity_id, expected",
    [
        ("sensor.feeder_illuminance", True),
        ("sensor.lux_2", True),
        ("sensor.feeder illuminance", False),
        ("sensor/../config", False),
        ("sensor.feeder?x=1", False),
        ("feeder_illuminance", False),
        ("Sensor.Feeder", False),
        ("", False),
        (None, False),
    ],
)
def test_only_a_home_assistant_entity_id_is_requested(entity_id, expected):
    assert is_entity_id(entity_id) is expected


def test_a_reading_belongs_to_a_detection_only_near_its_own_moment():
    detected = datetime(2026, 11, 13, 9, 0, tzinfo=timezone.utc)
    assert illuminance_at_detection(900.0, detected_at=detected, now=detected + timedelta(seconds=20)) == 900.0
    assert illuminance_at_detection(900.0, detected_at=detected, now=detected + timedelta(minutes=5)) == 900.0
    # A backlog replayed an hour later was not measured at the detection.
    assert illuminance_at_detection(900.0, detected_at=detected, now=detected + timedelta(hours=1)) is None
    # A clock that disagrees by more than the same margin is no evidence either.
    assert illuminance_at_detection(900.0, detected_at=detected, now=detected - timedelta(hours=1)) is None
    assert illuminance_at_detection(None, detected_at=detected, now=detected) is None
    assert illuminance_at_detection(-5.0, detected_at=detected, now=detected) is None


def test_a_pathological_entity_id_is_rejected_without_pattern_matching():
    """The id is owner-typed but still untrusted: rejecting it must not scale with its length."""
    import time

    hostile = [
        "0" * 2_000_000,
        "sensor." + "0" * 2_000_000 + "!",
        "0" * 1_000_000 + "." + "0" * 1_000_000,
        "." * 500_000,
    ]
    started = time.perf_counter()
    for value in hostile:
        assert is_entity_id(value) is False
    assert time.perf_counter() - started < 0.5
    # The longest id Home Assistant allows is still accepted; one character more is not.
    assert is_entity_id("sensor." + "a" * 248) is True
    assert is_entity_id("sensor." + "a" * 249) is False


@pytest.mark.parametrize(
    "entity_id", ["sensor.", ".feeder", "sensor..feeder", "sensor.feeder.lux", "sensor.feeder\n", "sensor.fée"]
)
def test_an_entity_id_needs_exactly_one_domain_and_one_object_id(entity_id):
    assert is_entity_id(entity_id) is False


def test_a_pathological_sensor_state_is_missing_data_and_costs_nothing():
    import time

    started = time.perf_counter()
    for state in ("0" * 2_000_000, "1" + "0" * 5_000, "1e" + "9" * 1_000_000, " " * 1_000_000 + "5"):
        reading = read_illuminance(_sensor(state, unit_of_measurement="lx"))
        assert reading.lux is None
        assert reading.reason == "not_numeric"
    assert time.perf_counter() - started < 0.5
    assert read_illuminance(_sensor("0001240.500000", unit_of_measurement="lx")).lux == pytest.approx(1240.5)
