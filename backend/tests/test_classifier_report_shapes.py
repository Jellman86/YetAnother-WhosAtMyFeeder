"""The classifier's health and status reports carry exactly the keys their shapes name."""

from app.models.classifier_reports import ClassifierHealthReport, ClassifierStatusReport
from app.services.classifier_service import get_classifier


def _keys_outside(report: dict, shape: type) -> tuple[set[str], set[str]]:
    keys = set(report)
    missing = set(shape.__required_keys__) - keys
    unnamed = keys - set(shape.__required_keys__) - set(shape.__optional_keys__)
    return missing, unnamed


def test_the_health_report_carries_the_keys_its_shape_names():
    missing, unnamed = _keys_outside(dict(get_classifier().check_health()), ClassifierHealthReport)

    assert not missing, f"ClassifierHealthReport names keys the report lacks: {sorted(missing)}"
    assert not unnamed, f"The health report carries keys ClassifierHealthReport does not name: {sorted(unnamed)}"


def test_the_status_report_carries_the_keys_its_shape_names():
    missing, unnamed = _keys_outside(dict(get_classifier().get_status()), ClassifierStatusReport)

    assert not missing, f"ClassifierStatusReport names keys the report lacks: {sorted(missing)}"
    assert not unnamed, f"The status report carries keys ClassifierStatusReport does not name: {sorted(unnamed)}"
