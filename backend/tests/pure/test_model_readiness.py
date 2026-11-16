"""The server and the SPA read a classifier report as the same readiness.

The wizard's review called a model "installed" because its weights file
existed, while the model step, reading the same install, showed a classifier
that had failed to load (weights present, labels unreadable). Both now read
the classifier's runtime report, and both are held to one shared set of cases.
"""

import json
from pathlib import Path

import pytest

from app.services.model_readiness import identification_readiness

CASES = json.loads((Path(__file__).parent.parent / "fixtures" / "model_readiness_cases.json").read_text())["cases"]


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_a_classifier_report_means_one_readiness(case):
    assert identification_readiness(case["status"]) == case["readiness"]


def test_weights_on_disk_are_not_readiness_when_the_runtime_could_not_load_them():
    status = {
        "active_model_installed": True,
        "runtime_source": "in_process",
        "loaded": False,
        "error": "labels unreadable",
    }
    assert identification_readiness(status) == "failed"


def test_running_needs_positive_evidence_not_the_absence_of_a_failure():
    # During an in-app reload the report has no `loaded` at all.
    assert identification_readiness({"active_model_installed": True, "runtime_source": "in_process"}) == "loading"
    assert (
        identification_readiness({"active_model_installed": True, "runtime_source": "in_process", "loaded": True})
        == "running"
    )
    assert identification_readiness({"active_model_installed": True}) == "unknown"
