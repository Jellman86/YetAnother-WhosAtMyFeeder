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
from types import SimpleNamespace

import pytest

from app.services.model_eval_service import (
    DEVICE_MATRIX_FILENAME,
    ModelEvalAlreadyRunning,
    ModelEvalRunner,
    SUMMARY_FILENAME,
    _build_summary_envelope,
    _compatibility_model_summaries,
    _drift_ratio,
    _gpu_diagnostic,
    _inference_health_for,
    _is_correct_match,
    _list_diverse_eval_images,
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
    assert _inference_health_for({}, model_id="rope")["verdict"] == "unknown"


def test_inference_health_is_the_evaluated_models_own_runtime():
    """The snapshot holds one entry per backend/provider/model and no overall verdict. The 2026-10-06
    run reported "unknown" for every model while ConvNeXt's own runtime said unhealthy, 32 of 32
    requests expired."""
    status = {
        "inference_backend": "openvino",
        "active_provider": "intel_npu",
        "inference_health": {
            "status": "unhealthy",
            "runtimes": {
                "openvino/intel_npu/convnext_large_inat21": {
                    "verdict": "unhealthy",
                    "recent_failures": 32,
                    "last_outcome": "lease_expired",
                },
                "openvino/intel_npu/rope_vit_b14_inat21": {"verdict": "healthy", "recent_failures": 0},
            },
        },
    }

    convnext = _inference_health_for(status, model_id="convnext_large_inat21")
    rope = _inference_health_for(status, model_id="rope_vit_b14_inat21")
    unseen = _inference_health_for(status, model_id="eva02_large_inat21")

    assert convnext["verdict"] == "unhealthy"
    assert convnext["runtime"]["last_outcome"] == "lease_expired"
    assert rope["verdict"] == "healthy"
    assert unseen == {"verdict": "unknown", "runtime": None}


def test_is_correct_match_taxa_id_strict():
    expected = SpeciesEntry(891696, "Pica pica", "Eurasian Magpie", "shared_core")
    assert _is_correct_match({"label": "Anything", "taxa_id": 891696}, expected) is True


def test_is_correct_match_falls_back_to_scientific_name():
    # iNat duplicate-taxa scenario: same species, different taxa_id
    expected = SpeciesEntry(891696, "Pica pica", "Eurasian Magpie", "shared_core")
    pred = {"label": "Pica pica", "taxa_id": 17550}
    assert _is_correct_match(pred, expected) is True


def test_is_correct_match_falls_back_to_common_name_case_insensitive():
    expected = SpeciesEntry(891696, "Pica pica", "Eurasian Magpie", "shared_core")
    pred = {"label": "eurasian magpie", "taxa_id": 17550}
    assert _is_correct_match(pred, expected) is True


def test_is_correct_match_strips_parenthetical():
    expected = SpeciesEntry(99, "Haemorhous mexicanus", "House Finch", "shared_core")
    pred = {"label": "House Finch (Adult Male)", "taxa_id": None}
    assert _is_correct_match(pred, expected) is True


def test_is_correct_match_rejects_different_species():
    expected = SpeciesEntry(8021, "Corvus brachyrhynchos", "American Crow", "shared_core")
    pred = {"label": "Carrion crow", "taxa_id": 144757}
    assert _is_correct_match(pred, expected) is False


def test_gpu_diagnostic_collects_relevant_signals():
    class _Meta:
        supported_inference_providers = ["openvino", "cpu"]

    class _Model:
        metadata = _Meta()

    status = {
        "selected_provider": "auto",
        "active_provider": "intel_cpu",
        "inference_backend": "openvino",
        "fallback_reason": "compile_failed",
        "openvino_available": True,
        "openvino_version": "2024.4.0",
        "openvino_devices": ["CPU", "GPU"],
        "openvino_model_compile_ok": False,
        "openvino_model_compile_device": None,
        "openvino_model_compile_error": "unsupported op MultiHeadAttention",
        "openvino_model_compile_unsupported_ops": ["MultiHeadAttention"],
        "cuda_provider_installed": False,
        "intel_gpu_available": True,
        "intel_cpu_available": True,
        "dev_dri_present": True,
        "dev_dri_entries": ["/dev/dri/card0"],
    }
    diag = _gpu_diagnostic(status, _Model())
    assert diag["registry_supported_providers"] == ["openvino", "cpu"]
    assert diag["openvino"]["model_compile_ok"] is False
    assert diag["openvino"]["model_compile_unsupported_ops"] == ["MultiHeadAttention"]
    assert diag["intel_gpu_available"] is True
    assert diag["fallback_reason"] == "compile_failed"


def test_gpu_diagnostic_handles_no_metadata():
    class _Model:
        metadata = None

    diag = _gpu_diagnostic({}, _Model())
    assert diag["registry_supported_providers"] == []
    assert diag["openvino"]["available"] is False


def test_gpu_diagnostic_surfaces_preprocessing_and_artifact_metadata():
    class _Meta:
        supported_inference_providers = ["cpu", "intel_cpu", "intel_gpu"]

    class _Model:
        metadata = _Meta()

    status = {
        "selected_provider": "auto",
        "active_provider": "intel_gpu",
        "inference_backend": "openvino",
        "openvino_runtime": {
            "model": {
                "model_type": "onnx",
                "model_sha256": "abc123",
                "weights_sha256": "def456",
                "producer_name": "pytorch",
                "producer_version": "2.1.0",
                "opset": [{"domain": "ai.onnx", "version": 17}],
                "model_config_warnings": [],
            },
        },
    }
    active_spec = {
        "input_size": 384,
        "runtime": "onnx",
        "preprocessing": {
            "color_space": "RGB",
            "resize_mode": "center_crop",
            "resize_rounding": "floor",
            "metadata_input": "inat2021_location_v1",
            "patch_size": 14,
            "max_seq_len": 576,
            "crop_pct": 0.95,
            "interpolation": "bicubic",
            "mean": [0.481, 0.458, 0.408],
            "std": [0.269, 0.261, 0.276],
            "normalization": "float32",
        },
        "model_config_warnings": ["installed config rejected legacy provider"],
    }
    diag = _gpu_diagnostic(status, _Model(), active_spec)
    pre = diag["preprocessing"]
    assert pre["input_size"] == 384
    assert pre["color_space"] == "RGB"
    assert pre["resize_mode"] == "center_crop"
    assert pre["resize_rounding"] == "floor"
    assert pre["metadata_input"] == "inat2021_location_v1"
    assert pre["patch_size"] == 14
    assert pre["max_seq_len"] == 576
    assert pre["crop_pct"] == 0.95
    assert pre["mean"] == [0.481, 0.458, 0.408]
    artifact = diag["model_artifact"]
    assert artifact["runtime"] == "onnx"
    assert artifact["model_sha256"] == "abc123"
    assert artifact["producer_name"] == "pytorch"
    assert artifact["opset"] == [{"domain": "ai.onnx", "version": 17}]
    # active_spec wins over runtime_model when both have warnings, but the
    # union is what matters operationally
    assert "installed config rejected legacy provider" in diag["model_config_warnings"]


def test_gpu_diagnostic_color_space_defaults_to_rgb():
    class _Model:
        metadata = None

    diag = _gpu_diagnostic({}, _Model(), active_spec={"preprocessing": {}})
    assert diag["preprocessing"]["color_space"] == "RGB"


def test_gpu_diagnostic_preserves_bgr_when_explicitly_set():
    class _Model:
        metadata = None

    diag = _gpu_diagnostic(
        {},
        _Model(),
        active_spec={"preprocessing": {"color_space": "BGR"}},
    )
    assert diag["preprocessing"]["color_space"] == "BGR"


def test_safe_run_id_accepts_only_canonical_run_ids():
    assert _safe_run_id("20260507-204512") == "20260507-204512"
    for invalid in ("abc_def", "../etc/passwd", "", "...", "/", "20260507-204512/../secret"):
        with pytest.raises(ValueError):
            _safe_run_id(invalid)


def test_device_matrix_is_a_supported_persisted_artifact():
    assert DEVICE_MATRIX_FILENAME == "device_matrix.json"


def test_compatibility_matrix_projects_into_setup_wizard_summary():
    summaries = _compatibility_model_summaries(
        {
            "models": {
                "rope": {
                    "best_provider": "cuda",
                    "providers": {
                        "cpu": {
                            "provider": "cpu",
                            "device": "CPUExecutionProvider",
                            "ok": True,
                            "images_evaluated": 12,
                            "latency_ms": 100.0,
                        },
                        "cuda": {
                            "provider": "cuda",
                            "device": "CUDAExecutionProvider",
                            "ok": True,
                            "images_evaluated": 12,
                            "latency_ms": 12.0,
                        },
                    },
                }
            }
        }
    )

    assert summaries[0]["model_id"] == "rope"
    assert summaries[0]["ready"] is True
    assert summaries[0]["active_provider"] == "cuda"
    assert summaries[0]["validated_providers"] == ["cpu", "cuda"]
    assert summaries[0]["mean_latency_ms"] == 12.0
    assert summaries[0]["warnings"] == []


@pytest.mark.asyncio
async def test_provider_sweep_contains_one_model_failure_and_continues(tmp_path, monkeypatch):
    from app.services import model_validation
    from app.services.model_manager import model_manager

    runner = ModelEvalRunner()

    async def activate_model(_model_id):
        return True

    async def sweep_model_devices(model_id, *, image_paths, discover_providers=False):
        assert discover_providers is True
        if model_id == "broken":
            raise RuntimeError("driver crashed")
        return {
            "image_flavor": "cuda",
            "baseline_provider": "cpu",
            "eligible_providers": ["cpu", "cuda"],
            "best": {"provider": "cuda", "latency_ms": 12.0},
            "providers": [
                {"provider": "cpu", "ok": True, "latency_ms": 100.0},
                {"provider": "cuda", "ok": True, "latency_ms": 12.0},
            ],
        }

    async def emit(*_args, **_kwargs):
        return None

    monkeypatch.setenv("YAWAMF_EVAL_RUNS_DIR", str(tmp_path))
    monkeypatch.setattr(model_manager, "activate_model", activate_model)
    monkeypatch.setattr(model_validation, "sweep_model_devices", sweep_model_devices)
    monkeypatch.setattr(runner, "_emit", emit)

    payload = await runner._device_sweep(
        "run-1",
        tmp_path,
        [SimpleNamespace(id="broken"), SimpleNamespace(id="healthy")],
        discover_providers=True,
    )

    assert payload["models"]["broken"]["error"].startswith("provider_sweep_failed")
    assert payload["models"]["healthy"]["best_provider"] == "cuda"
    assert payload["providers"] == ["cpu", "cuda"]

    from app.services.model_validation import read_validation_record

    assert read_validation_record("broken")["validated"] is False
    assert read_validation_record("healthy")["provider"] == "cuda"


@pytest.mark.asyncio
async def test_device_sweep_persists_crop_detectors_separately(tmp_path, monkeypatch):
    from app.services import model_validation

    runner = ModelEvalRunner()

    async def sweep_crop_model_devices(model_id, *, image_paths, discover_providers=False):
        assert model_id == "bird_crop_detector"
        assert discover_providers is True
        return {
            "image_flavor": "intel",
            "baseline_provider": "cpu",
            "eligible_providers": ["cpu", "intel_npu"],
            "discovered_providers": [],
            "best": {"provider": "intel_npu", "latency_ms": 4.0},
            "providers": [
                {"provider": "cpu", "ok": True, "compiles": True, "latency_ms": 20.0},
                {
                    "provider": "intel_npu",
                    "ok": True,
                    "compiles": True,
                    "latency_ms": 4.0,
                    "comparison_kind": "crop_box",
                    "detection_match_rate": 1.0,
                },
            ],
        }

    async def emit(*_args, **_kwargs):
        return None

    monkeypatch.setenv("YAWAMF_EVAL_RUNS_DIR", str(tmp_path))
    monkeypatch.setattr(model_validation, "sweep_crop_model_devices", sweep_crop_model_devices)
    monkeypatch.setattr(runner, "_emit", emit)

    payload = await runner._device_sweep(
        "run-1",
        tmp_path,
        [],
        [SimpleNamespace(id="bird_crop_detector")],
        discover_providers=True,
    )

    assert payload["schema_version"] == 3
    assert payload["models"] == {}
    assert payload["crop_detectors"]["bird_crop_detector"]["best_provider"] == "intel_npu"
    assert payload["providers"] == ["cpu", "intel_npu"]


def test_diverse_eval_image_selection_round_robins_species(tmp_path):
    for species in ("alpha", "beta", "gamma"):
        folder = tmp_path / species
        folder.mkdir()
        for index in range(3):
            (folder / f"{index}.jpg").write_bytes(b"image")

    selected = _list_diverse_eval_images(tmp_path, {".jpg"}, 5)

    assert [Path(path).parent.name for path in selected] == ["alpha", "beta", "gamma", "alpha", "beta"]


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
    (run_a / SUMMARY_FILENAME).write_text(
        json.dumps(
            {
                "started_at": "a-start",
                "finished_at": "a-end",
                "duration_seconds": 100,
                "test_set": {"total_species": 50, "total_images": 150, "region": "US-CA"},
                "models": [{"model_id": "m1"}, {"model_id": "m2"}],
            }
        )
    )
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


def test_get_run_does_not_normalize_untrusted_input_to_an_existing_run(tmp_path: Path, monkeypatch):
    _set_runs_dir(monkeypatch, tmp_path)
    run_dir = tmp_path / "20260507-200000"
    run_dir.mkdir()
    (run_dir / SUMMARY_FILENAME).write_text(json.dumps({"run_id": "20260507-200000", "models": []}))

    runner = ModelEvalRunner()

    assert runner.get_run("../20260507-200000") is None


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


STARLING_ID, BLUE_JAY_ID, ROBIN_ID = 101, 202, 303
EU_MODEL_SHA = "e" * 64
_PANEL = [
    SpeciesEntry(1, "Sturnus vulgaris", "European Starling", "shared_core"),
    SpeciesEntry(2, "Cyanocitta cristata", "Blue Jay", "shared_core"),
    SpeciesEntry(3, "Erithacus rubecula", "European Robin", "regional"),
]
_PHOTO_COLOURS = {1: (200, 0, 0), 2: (0, 0, 200), 3: (0, 200, 0)}
# A European model: it calls the starling "Common starling" and has no output for a Blue Jay.
_EU_PREDICTIONS = {
    (200, 0, 0): [{"index": 0, "label": "Common starling", "score": 0.9}],
    (0, 0, 200): [{"index": 1, "label": "European robin", "score": 0.4}],
    (0, 200, 0): [{"index": 1, "label": "European robin", "score": 0.95}],
}


async def _run_eu_model_evaluation(
    tmp_path,
    monkeypatch,
    *,
    catalogue_knows_model: bool,
    sweep_devices: bool = True,
    failing_colours=(),
    parent_knows_checksum: bool = True,
):
    from PIL import Image

    from app.services import classifier_service as classifier_module
    from app.services import model_eval_service as service
    from app.services.eval.image_fetcher import FetchedImage
    from app.services.model_manager import model_manager
    from app.services.species_catalog_resolver import species_catalog_resolver

    events: list[str] = []

    async def build_panel(**_kwargs):
        return list(_PANEL)

    async def fetch_panel_images(*, species, dest_root, **_kwargs):
        fetched = {}
        for row in species:
            folder = Path(dest_root) / str(row["taxa_id"])
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / "00.png"
            Image.new("RGB", (8, 8), _PHOTO_COLOURS[row["taxa_id"]]).save(path)
            fetched[row["taxa_id"]] = [
                FetchedImage(
                    taxa_id=row["taxa_id"],
                    scientific_name=row["scientific_name"],
                    common_name=row["common_name"],
                    source="inat",
                    source_url=f"https://example.test/{row['taxa_id']}.png",
                    local_path=str(path),
                )
            ]
        return fetched

    class EuClassifier:
        async def reload_bird_model(self):
            events.append("reload")

        async def classify_async(self, image):
            events.append("classify")
            if image.getpixel((0, 0)) in failing_colours:
                raise RuntimeError("inference failed")
            return [dict(row) for row in _EU_PREDICTIONS[image.getpixel((0, 0))]]

        def active_model_sha256(self):
            # A subprocess-mode parent never loads the model, so it may not know the checksum.
            return EU_MODEL_SHA if parent_knows_checksum else None

        def get_status(self):
            return {
                "inference_backend": "openvino",
                "active_provider": "intel_npu",
                "selected_provider": "intel_npu",
                "inference_health": {
                    "status": "ok",
                    "runtimes": {"openvino/intel_npu/eu_model": {"verdict": "healthy"}},
                },
            }

    async def list_installed_models():
        return [SimpleNamespace(id="eu_model", ready=True, reason="ready", metadata=None, labels_path="", path="")]

    async def activate_model(model_id):
        model_manager.active_model_id = model_id
        return True

    async def device_sweep(*_args, **_kwargs):
        events.append("sweep")
        return {}

    async def nothing(*_args, **_kwargs):
        return None

    species_ids = {"sturnus vulgaris": STARLING_ID, "cyanocitta cristata": BLUE_JAY_ID, "erithacus rubecula": ROBIN_ID}
    monkeypatch.setenv("YAWAMF_EVAL_RUNS_DIR", str(tmp_path))
    monkeypatch.setattr(service, "build_panel", build_panel)
    monkeypatch.setattr(service, "fetch_panel_images", fetch_panel_images)
    monkeypatch.setattr(classifier_module, "get_classifier", lambda: EuClassifier())
    monkeypatch.setattr(model_manager, "list_installed_models", list_installed_models)
    monkeypatch.setattr(model_manager, "activate_model", activate_model)
    monkeypatch.setattr(model_manager, "active_model_id", "eu_model")
    monkeypatch.setattr(
        model_manager, "get_active_model_spec", lambda: {"model_id": "eu_model", "resolved_region": None}
    )
    monkeypatch.setattr(
        "app.services.catalogue_labels.published_model_sha256",
        lambda model_id, region=None: EU_MODEL_SHA if model_id == "eu_model" else None,
    )
    monkeypatch.setattr(
        species_catalog_resolver,
        "resolve_scientific_name",
        lambda name: (species_ids.get(str(name).casefold()), "resolved"),
    )
    monkeypatch.setattr(
        species_catalog_resolver,
        "species_outputs",
        lambda sha: {0: STARLING_ID, 1: ROBIN_ID} if catalogue_knows_model and sha == EU_MODEL_SHA else None,
    )
    monkeypatch.setattr(
        species_catalog_resolver,
        "unresolved_output_labels",
        lambda sha: ("Unknown",) if catalogue_knows_model and sha == EU_MODEL_SHA else None,
    )

    runner = ModelEvalRunner()
    monkeypatch.setattr(runner, "_emit", nothing)
    monkeypatch.setattr(runner, "_device_sweep", device_sweep)
    monkeypatch.setattr(runner, "_download_all_validation_models", nothing)

    run_dir = tmp_path / "20261007-120000"
    run_dir.mkdir()
    await runner._do_run(
        run_id="20261007-120000",
        run_dir=run_dir,
        include_per_image=True,
        region_override=None,
        sweep_devices=sweep_devices,
    )
    summary = json.loads((run_dir / SUMMARY_FILENAME).read_text())
    rows = [json.loads(line) for line in (run_dir / "results.jsonl").read_text().splitlines()]
    return summary["models"][0], rows, events


@pytest.mark.asyncio
async def test_a_regional_model_is_scored_by_species_and_on_the_birds_it_can_name(tmp_path, monkeypatch):
    """The 2026-10-06 run scored the European FocalNet model 52.8% with a critical "broken install"
    warning; on the European birds it was built for it scored 83.0%."""
    model, rows, _events = await _run_eu_model_evaluation(tmp_path, monkeypatch, catalogue_knows_model=True)

    starling = next(row for row in rows if row["taxa_id"] == 1)
    assert starling["correct_top1"] is True
    assert starling["top5"][0]["species_id"] == STARLING_ID
    assert starling["expected_species_id"] == STARLING_ID
    assert next(row for row in rows if row["taxa_id"] == 2)["in_vocabulary"] is False

    assert model["top1_accuracy"] == pytest.approx(2 / 3, abs=1e-4)
    assert model["vocabulary_known"] is True
    assert model["panel_species"] == 3
    assert model["species_outside_vocabulary"] == 1
    assert model["images_in_vocabulary"] == 2
    assert model["top1_accuracy_in_vocabulary"] == 1.0
    assert model["shared_core_top1"] == 0.5
    assert model["shared_core_top1_in_vocabulary"] == 1.0
    codes = [warning["code"] for warning in model["warnings"]]
    assert "low_shared_core" not in codes
    assert "partial_vocabulary" in codes


@pytest.mark.asyncio
async def test_a_model_the_catalogue_does_not_know_falls_back_to_name_matching(tmp_path, monkeypatch):
    model, rows, _events = await _run_eu_model_evaluation(tmp_path, monkeypatch, catalogue_knows_model=False)

    assert next(row for row in rows if row["taxa_id"] == 1)["correct_top1"] is False
    assert model["vocabulary_known"] is False
    assert model["top1_accuracy_in_vocabulary"] is None
    assert model["top1_accuracy"] == pytest.approx(1 / 3, abs=1e-4)


@pytest.mark.asyncio
async def test_providers_are_validated_before_the_accuracy_pass(tmp_path, monkeypatch):
    """A model loads only on providers validated on this host. Sweeping after the accuracy pass scored
    a model the sweep then cleared for the NPU (small_birds on 2026-10-06) on its CPU fallback."""
    _model, _rows, events = await _run_eu_model_evaluation(tmp_path, monkeypatch, catalogue_knows_model=True)

    assert events.index("sweep") < events.index("reload") < events.index("classify")


@pytest.mark.asyncio
async def test_the_summary_reports_the_evaluated_models_own_health(tmp_path, monkeypatch):
    model, _rows, events = await _run_eu_model_evaluation(
        tmp_path, monkeypatch, catalogue_knows_model=True, sweep_devices=False
    )

    assert "sweep" not in events
    assert model["inference_health_verdict"] == "healthy"


@pytest.mark.asyncio
async def test_which_birds_a_model_can_name_does_not_depend_on_inference_succeeding(tmp_path, monkeypatch):
    """Every Blue Jay image failing must not move the Blue Jay into "Can name"."""
    model, rows, _events = await _run_eu_model_evaluation(
        tmp_path, monkeypatch, catalogue_knows_model=True, failing_colours={_PHOTO_COLOURS[2]}
    )

    assert all(row["taxa_id"] != 2 for row in rows)
    assert model["species_outside_vocabulary"] == 1


@pytest.mark.asyncio
async def test_a_subprocess_install_still_scores_by_species(tmp_path, monkeypatch):
    """The default subprocess mode never loads the model in the main process, so the harness takes the
    evaluated model's checksum from the registry, as the catalogue does."""
    model, _rows, _events = await _run_eu_model_evaluation(
        tmp_path, monkeypatch, catalogue_knows_model=True, parent_knows_checksum=False
    )

    assert model["vocabulary_known"] is True
    assert model["top1_accuracy_in_vocabulary"] == 1.0
