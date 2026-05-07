"""Tests for the ModelEvalRunner orchestrator and its helpers.

The orchestrator's full run path needs ClassifierService + ModelManager which
are heavy to mock. We test the pieces that don't require a live classifier:
- run-id sanitization, percentile/safe-div helpers
- run history listing/reading from disk
- artifact path resolution and traversal protection
- start() rejects when a run is already in progress
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.services.model_eval_service import (
    ModelEvalAlreadyRunning,
    ModelEvalRunner,
    SUMMARY_FILENAME,
    _build_summary_envelope,
    _drift_ratio,
    _inference_health_for,
    _percentile,
    _provider_summary,
    _resolve_label_taxa,
    _safe_div,
    _safe_run_id,
)
from app.services.eval.species_panel import SpeciesEntry


def _set_runs_dir(monkeypatch, path: Path) -> None:
    monkeypatch.setenv("YAWAMF_EVAL_RUNS_DIR", str(path))


def test_safe_div_zero_denominator():
    assert _safe_div(5, 0) == 0.0


def test_safe_div_rounds():
    assert _safe_div(1, 3) == round(1 / 3, 4)


def test_percentile_basic():
    assert _percentile([1, 2, 3, 4, 5], 50) == 3
    assert _percentile([], 50) == 0.0


def test_drift_ratio_handles_missing():
    assert _drift_ratio([], 100) is None
    assert _drift_ratio([100, 200], 0) is None
    assert _drift_ratio([100, 200], None) is None


def test_drift_ratio_computes():
    ratio = _drift_ratio([100, 200, 300], 100)
    assert ratio == 2.0


def test_resolve_label_taxa_panel_exact_match():
    panel = {"passer domesticus": 12345, "house sparrow": 12345}
    assert _resolve_label_taxa("Passer domesticus", panel, {}) == 12345
    assert _resolve_label_taxa("HOUSE sparrow", panel, {}) == 12345


def test_resolve_label_taxa_strips_parenthetical():
    panel = {"haemorhous mexicanus": 99}
    assert _resolve_label_taxa("Haemorhous mexicanus (Adult Male)", panel, {}) == 99


def test_resolve_label_taxa_uses_cache():
    cache = {"weird label": 555}
    assert _resolve_label_taxa("weird label", {}, cache) == 555


def test_resolve_label_taxa_returns_none_when_unknown():
    assert _resolve_label_taxa("Mystery bird", {}, {}) is None


def test_provider_summary_pulls_active_provider_and_benchmark():
    status = {
        "active_provider": "intel_gpu",
        "inference_backend": "openvino",
        "selected_provider": "openvino",
        "fallback_reason": None,
        "openvino_model_compile_device": "GPU",
        "runtime_benchmarks": {
            "openvino/intel_gpu": {"candidate_latency_seconds": 0.290, "status": "passed"},
        },
    }
    out = _provider_summary(status)
    assert out["active_provider"] == "intel_gpu"
    assert out["startup_benchmark_ms"] == 290.0
    assert out["device"] == "GPU"


def test_provider_summary_safe_when_status_missing():
    out = _provider_summary({})
    assert out["active_provider"] is None
    assert out["startup_benchmark_ms"] is None


def test_inference_health_for_defaults_to_unknown():
    assert _inference_health_for({})["verdict"] == "unknown"
    assert _inference_health_for({"inference_health": {"verdict": "healthy"}})["verdict"] == "healthy"


def test_safe_run_id_sanitizes_and_rejects():
    assert _safe_run_id("20260507-204512") == "20260507-204512"
    assert _safe_run_id("abc_def") == "abc_def"
    # path-traversal characters get filtered out, leaving a benign string
    assert "/" not in _safe_run_id("../etc/passwd")
    assert ".." not in _safe_run_id("../etc/passwd")
    with pytest.raises(ValueError):
        _safe_run_id("")
    with pytest.raises(ValueError):
        _safe_run_id("...")
    with pytest.raises(ValueError):
        _safe_run_id("/")


def test_build_summary_envelope_counts_panels():
    panel = [
        SpeciesEntry(1, "A a", "A", "shared_core"),
        SpeciesEntry(2, "B b", "B", "shared_core"),
        SpeciesEntry(3, "C c", "C", "regional"),
    ]
    from datetime import datetime, timezone
    started = datetime(2026, 5, 7, tzinfo=timezone.utc)
    finished = datetime(2026, 5, 7, 0, 5, tzinfo=timezone.utc)
    envelope = _build_summary_envelope(
        run_id="x",
        started_at=started,
        finished_at=finished,
        panel=panel,
        total_images=9,
        image_sources={"inat": 7, "wikimedia": 2},
        region_label="US-CA",
        models=[],
    )
    assert envelope["test_set"]["shared_core_species"] == 2
    assert envelope["test_set"]["regional_species"] == 1
    assert envelope["test_set"]["region"] == "US-CA"
    assert envelope["duration_seconds"] == 300.0


def test_list_runs_reads_summary_briefs(tmp_path: Path, monkeypatch):
    _set_runs_dir(monkeypatch, tmp_path)
    run_a = tmp_path / "20260507-100000"
    run_b = tmp_path / "20260507-110000"
    run_a.mkdir()
    run_b.mkdir()
    (run_a / SUMMARY_FILENAME).write_text(json.dumps({
        "started_at": "a-start",
        "finished_at": "a-end",
        "duration_seconds": 100,
        "test_set": {"total_species": 50, "total_images": 150, "region": "US-CA"},
        "models": [{"model_id": "m1"}, {"model_id": "m2"}],
    }))
    # run_b has no summary yet (in flight or never written)

    runner = ModelEvalRunner()
    rows = runner.list_runs()
    ids = [r["run_id"] for r in rows]
    assert "20260507-100000" in ids
    assert "20260507-110000" in ids
    a = next(r for r in rows if r["run_id"] == "20260507-100000")
    assert a["model_count"] == 2
    assert a["total_species"] == 50


def test_list_runs_caps_to_twenty(tmp_path: Path, monkeypatch):
    _set_runs_dir(monkeypatch, tmp_path)
    for i in range(25):
        d = tmp_path / f"2026-{i:02d}"
        d.mkdir()
    runner = ModelEvalRunner()
    assert len(runner.list_runs()) == 20


def test_get_run_returns_none_for_missing(tmp_path: Path, monkeypatch):
    _set_runs_dir(monkeypatch, tmp_path)
    runner = ModelEvalRunner()
    assert runner.get_run("does-not-exist") is None


def test_get_run_reads_summary_and_runtime(tmp_path: Path, monkeypatch):
    _set_runs_dir(monkeypatch, tmp_path)
    run_dir = tmp_path / "20260507-200000"
    run_dir.mkdir()
    (run_dir / SUMMARY_FILENAME).write_text(json.dumps({"run_id": "20260507-200000", "models": []}))
    (run_dir / "runtime.json").write_text(json.dumps({"m1": {"verdict": "healthy"}}))
    runner = ModelEvalRunner()
    payload = runner.get_run("20260507-200000")
    assert payload is not None
    assert payload["run_id"] == "20260507-200000"
    assert payload["runtime"]["m1"]["verdict"] == "healthy"


def test_artifact_path_rejects_unknown_filename(tmp_path: Path, monkeypatch):
    _set_runs_dir(monkeypatch, tmp_path)
    runner = ModelEvalRunner()
    assert runner.artifact_path("any", "../../etc/passwd") is None
    assert runner.artifact_path("any", "config.json") is None


def test_artifact_path_returns_only_existing(tmp_path: Path, monkeypatch):
    _set_runs_dir(monkeypatch, tmp_path)
    run_dir = tmp_path / "20260507-200000"
    run_dir.mkdir()
    (run_dir / SUMMARY_FILENAME).write_text("{}")
    runner = ModelEvalRunner()
    assert runner.artifact_path("20260507-200000", SUMMARY_FILENAME) is not None
    assert runner.artifact_path("20260507-200000", "results.jsonl") is None


def test_delete_run_removes_dir(tmp_path: Path, monkeypatch):
    _set_runs_dir(monkeypatch, tmp_path)
    run_dir = tmp_path / "20260507-200000"
    run_dir.mkdir()
    (run_dir / SUMMARY_FILENAME).write_text("{}")
    runner = ModelEvalRunner()
    assert runner.delete_run("20260507-200000") is True
    assert not run_dir.exists()


def test_delete_run_returns_false_for_missing(tmp_path: Path, monkeypatch):
    _set_runs_dir(monkeypatch, tmp_path)
    runner = ModelEvalRunner()
    assert runner.delete_run("does-not-exist") is False


@pytest.mark.asyncio
async def test_start_rejects_when_already_running(tmp_path: Path, monkeypatch):
    _set_runs_dir(monkeypatch, tmp_path)
    runner = ModelEvalRunner()

    # Simulate an in-flight run by stubbing the task without actually running.
    async def _never_finish(**kwargs):
        await asyncio.sleep(60)

    monkeypatch.setattr(runner, "_run_async", _never_finish)
    await runner.start()
    try:
        with pytest.raises(ModelEvalAlreadyRunning):
            await runner.start()
    finally:
        if runner._task:
            runner._task.cancel()
            try:
                await runner._task
            except asyncio.CancelledError:
                pass
