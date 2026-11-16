"""How ready the identification model is, read from the classifier's own status report.

This is the server's copy of the rule the SPA applies to the same report
(`identificationStatus` in `apps/ui/src/lib/settings/identification-models.ts`).
Both are tested against `tests/fixtures/model_readiness_cases.json`, so the
setup review and the model step cannot disagree about one install.

A weights file on disk is not readiness: a model inside the app that could not
be loaded has failed, whatever exists on disk.
"""

from __future__ import annotations

from typing import Literal

ModelReadiness = Literal["checking", "missing", "failed", "ready", "running"]

_IN_APP_SOURCES = frozenset({"in_process", "in_process_fallback"})
_WORKER_SOURCES = frozenset({"worker", "planned"})


def identification_readiness(status: dict | None) -> ModelReadiness:
    """Name the classifier report's state: no report, weights absent, load failed, waiting or working."""
    if not status:
        return "checking"
    if status.get("active_model_installed") is False:
        return "missing"
    runtime_source = status.get("runtime_source")
    # Only a model held inside the app reports whether it loaded. Isolated workers load on their
    # first detection, so there "not loaded" is the normal idle state, never a failure.
    in_app = runtime_source in _IN_APP_SOURCES or (
        status.get("image_execution_mode") == "in_process" and runtime_source not in _WORKER_SOURCES
    )
    if in_app and status.get("loaded") is False:
        return "failed"
    return "ready" if runtime_source == "planned" else "running"
