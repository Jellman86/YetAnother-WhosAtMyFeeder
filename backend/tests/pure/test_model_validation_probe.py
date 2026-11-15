"""The image-aware validation probe: judging, record-writing, and restore-on-exit.

The probe is exercised with a fake classifier and fake manager so no real model,
network, or accelerator is touched.
"""

from PIL import Image
import pytest

from app.services import model_validation as mv
from app.services.bird_crop_service import BirdCropService
from scripts.probe_crop_model_provider import _load_images, _top_detection


def test_judge_accepts_finite_positive_scores():
    ok, reason = mv._judge_predictions([{"label": "a", "score": 0.8}, {"label": "b", "score": 0.1}])
    assert ok is True
    assert "finite" in reason


def test_judge_rejects_nan_scores():
    ok, reason = mv._judge_predictions([{"label": "a", "score": float("nan")}])
    assert ok is False
    assert "non-finite" in reason.lower()


def test_judge_rejects_empty():
    ok, reason = mv._judge_predictions([])
    assert ok is False


def test_judge_rejects_all_zero_scores():
    ok, reason = mv._judge_predictions([{"label": "a", "score": 0.0}])
    assert ok is False


@pytest.mark.parametrize(
    ("image_flavor", "expected"),
    [
        ("cpu", ["cpu"]),
        ("rpi", ["cpu"]),
        ("cuda", ["cpu", "cuda"]),
        ("intel", ["cpu", "intel_cpu", "intel_gpu", "intel_npu"]),
        ("full", ["cpu", "intel_cpu", "cuda", "intel_gpu", "intel_npu"]),
    ],
)
def test_validation_provider_candidates_respect_image_host_and_model_contract(image_flavor, expected):
    caps = {
        "ort_available": True,
        "cuda_available": True,
        "openvino_available": True,
        "intel_cpu_available": True,
        "intel_gpu_available": True,
        "intel_npu_available": True,
    }

    candidates = mv.validation_provider_candidates(
        image_flavor=image_flavor,
        capabilities=caps,
        supported_providers=["cpu", "cuda", "intel_cpu", "intel_gpu", "intel_npu"],
        model_runtime="onnx",
    )

    assert [candidate.provider for candidate in candidates] == expected


def test_validation_provider_candidates_never_probe_a_provider_the_model_excludes():
    candidates = mv.validation_provider_candidates(
        image_flavor="full",
        capabilities={
            "ort_available": True,
            "cuda_available": True,
            "openvino_available": True,
            "intel_cpu_available": True,
            "intel_gpu_available": True,
            "intel_npu_available": True,
        },
        supported_providers=["cpu", "intel_npu"],
        model_runtime="onnx",
    )

    assert [candidate.provider for candidate in candidates] == ["cpu", "intel_npu"]


def test_validation_provider_discovery_can_probe_packaged_host_providers_outside_the_registry():
    candidates = mv.validation_provider_candidates(
        image_flavor="intel",
        capabilities={
            "ort_available": True,
            "cuda_available": False,
            "openvino_available": True,
            "intel_cpu_available": True,
            "intel_gpu_available": True,
            "intel_npu_available": True,
        },
        supported_providers=["cpu", "intel_cpu"],
        model_runtime="onnx",
        discover_providers=True,
    )

    assert [candidate.provider for candidate in candidates] == ["cpu", "intel_cpu", "intel_gpu", "intel_npu"]


def test_validation_provider_candidates_keep_tflite_on_cpu():
    candidates = mv.validation_provider_candidates(
        image_flavor="full",
        capabilities={
            "ort_available": True,
            "cuda_available": True,
            "openvino_available": True,
            "intel_cpu_available": True,
            "intel_gpu_available": True,
            "intel_npu_available": True,
        },
        supported_providers=["cpu", "cuda", "intel_gpu"],
        model_runtime="tflite",
    )

    assert [candidate.provider for candidate in candidates] == ["cpu"]


@pytest.mark.asyncio
async def test_provider_discovery_reports_undeclared_success_without_widening_eligibility(monkeypatch):
    from app.services import classifier_service
    from app.services.model_manager import model_manager

    monkeypatch.setenv("YAWAMF_IMAGE_FLAVOR", "intel")
    monkeypatch.setattr(
        classifier_service,
        "_detect_acceleration_capabilities",
        lambda: {
            "ort_available": True,
            "cuda_available": False,
            "openvino_available": True,
            "intel_cpu_available": True,
            "intel_gpu_available": True,
            "intel_npu_available": True,
        },
    )
    monkeypatch.setattr(
        model_manager,
        "get_active_model_spec",
        lambda: {
            "model_id": "small_birds",
            "runtime": "onnx",
            "supported_inference_providers": ["cpu", "intel_cpu"],
        },
    )

    async def successful_probe(provider, **_kwargs):
        return {
            "provider": provider,
            "compile": {"ok": True},
            "output_summary": {"finite_count": 2, "element_count": 2},
            "per_image_top_indices": [[3, 2, 1]],
            "inference_latency_ms": 10.0 if provider == "intel_npu" else 20.0,
        }

    monkeypatch.setattr(mv, "_probe_one_provider", successful_probe)

    result = await mv.sweep_model_devices("small_birds", image_paths=["bird.jpg"], discover_providers=True)

    assert result["eligible_providers"] == ["cpu", "intel_cpu"]
    assert result["discovered_providers"] == ["intel_gpu", "intel_npu"]
    assert result["best"]["provider"] == "cpu"
    assert result["best_discovered"]["provider"] == "intel_npu"
    by_provider = {row["provider"]: row for row in result["providers"]}
    assert by_provider["intel_npu"]["declared"] is False
    assert by_provider["intel_npu"]["ok"] is True


def test_crop_detection_comparison_covers_positive_and_empty_images():
    baseline = [
        {
            "image": "real:small-bird.jpg",
            "top_detection": {"normalized_box": [0.1, 0.2, 0.4, 0.6], "confidence": 0.6},
        },
        {"image": "negative_foliage", "top_detection": None},
    ]
    provider = [
        {
            "image": "real:small-bird.jpg",
            "top_detection": {"normalized_box": [0.101, 0.2, 0.401, 0.6], "confidence": 0.61},
        },
        {"image": "negative_foliage", "top_detection": None},
    ]

    result = mv._compare_crop_detections(baseline, provider)

    assert result["images_compared"] == 2
    assert result["matches"] == 2
    assert result["agrees"] is True
    assert result["mean_box_iou"] > 0.98


def test_crop_detection_comparison_rejects_provider_only_false_positive():
    result = mv._compare_crop_detections(
        [{"image": "negative_foliage", "top_detection": None}],
        [
            {
                "image": "negative_foliage",
                "top_detection": {"normalized_box": [0.1, 0.1, 0.8, 0.8], "confidence": 0.8},
            }
        ],
    )

    assert result["agrees"] is False
    assert result["match_rate"] == 0.0


def test_crop_detection_comparison_rejects_incomplete_provider_panel():
    baseline = [
        {"image": "real:000:image.jpg", "top_detection": None},
        {"image": "real:001:image.jpg", "top_detection": None},
    ]
    provider = [{"image": "real:000:image.jpg", "top_detection": None}]

    result = mv._compare_crop_detections(baseline, provider)

    assert result["matches"] == 1
    assert result["coverage_complete"] is False
    assert result["missing_images"] == 1
    assert result["agrees"] is False


def test_crop_detection_comparison_rejects_duplicate_image_keys():
    duplicated = [
        {"image": "real:image.jpg", "top_detection": None},
        {"image": "real:image.jpg", "top_detection": None},
    ]

    result = mv._compare_crop_detections(duplicated, duplicated)

    assert result["duplicate_image_keys"] is True
    assert result["coverage_complete"] is False
    assert result["agrees"] is False


@pytest.mark.asyncio
async def test_crop_provider_sweep_keeps_discovered_hardware_informational(monkeypatch):
    from app.services import classifier_service
    from app.services.model_manager import model_manager

    monkeypatch.setenv("YAWAMF_IMAGE_FLAVOR", "intel")
    monkeypatch.setattr(
        classifier_service,
        "_detect_acceleration_capabilities",
        lambda: {
            "ort_available": True,
            "cuda_available": False,
            "openvino_available": True,
            "intel_cpu_available": True,
            "intel_gpu_available": True,
            "intel_npu_available": True,
        },
    )
    monkeypatch.setattr(
        model_manager,
        "get_crop_detector_spec_by_model_id",
        lambda model_id: {
            "model_id": model_id,
            "healthy": True,
            "metadata": {
                "runtime": "onnx",
                "supported_inference_providers": ["cpu", "intel_cpu"],
            },
        },
    )

    async def successful_probe(provider, **_kwargs):
        offset = 0.001 if provider == "intel_npu" else 0.0
        return {
            "provider": provider,
            "compile": {"ok": True},
            "output_summary": {"finite_count": 100, "element_count": 100},
            "per_image_detections": [
                {
                    "image": "real:bird-a.jpg",
                    "kind": "real",
                    "top_detection": {
                        "normalized_box": [0.1 + offset, 0.2, 0.5 + offset, 0.7],
                        "confidence": 0.7,
                    },
                },
                {"image": "negative_foliage", "kind": "negative", "top_detection": None},
            ],
            "inference_latency_ms": 5.0 if provider == "intel_npu" else 20.0,
        }

    monkeypatch.setattr(mv, "_probe_one_crop_provider", successful_probe)

    result = await mv.sweep_crop_model_devices(
        "bird_crop_detector",
        image_paths=["bird-a.jpg"],
        discover_providers=True,
    )

    assert result["eligible_providers"] == ["cpu", "intel_cpu"]
    assert result["discovered_providers"] == ["intel_gpu", "intel_npu"]
    assert result["best"]["provider"] == "cpu"
    assert result["best_discovered"]["provider"] == "intel_npu"
    npu = next(row for row in result["providers"] if row["provider"] == "intel_npu")
    assert npu["comparison_kind"] == "crop_box"
    assert npu["detection_match_rate"] == 1.0


@pytest.mark.asyncio
async def test_crop_provider_sweep_probes_only_the_requested_providers(monkeypatch):
    from app.services import classifier_service
    from app.services.model_manager import model_manager

    monkeypatch.setenv("YAWAMF_IMAGE_FLAVOR", "intel")
    monkeypatch.setattr(
        classifier_service,
        "_detect_acceleration_capabilities",
        lambda: {
            "ort_available": True,
            "cuda_available": False,
            "openvino_available": True,
            "intel_cpu_available": True,
            "intel_gpu_available": True,
            "intel_npu_available": True,
        },
    )
    monkeypatch.setattr(
        model_manager,
        "get_crop_detector_spec_by_model_id",
        lambda model_id: {
            "model_id": model_id,
            "healthy": True,
            "metadata": {
                "runtime": "onnx",
                "supported_inference_providers": ["cpu", "intel_cpu", "intel_gpu", "intel_npu"],
            },
        },
    )
    probed: list[str] = []

    async def probe(provider, **_kwargs):
        probed.append(provider)
        return {
            "provider": provider,
            "compile": {"ok": True},
            "output_summary": {"finite_count": 1, "element_count": 1},
            "per_image_detections": [
                {
                    "image": "real:bird-a.jpg",
                    "kind": "real",
                    "top_detection": {"normalized_box": [0.1, 0.2, 0.5, 0.7], "confidence": 0.7},
                }
            ],
            "inference_latency_ms": 10.0,
        }

    monkeypatch.setattr(mv, "_probe_one_crop_provider", probe)

    result = await mv.sweep_crop_model_devices(
        "bird_crop_detector_accurate_yolox_tiny",
        image_paths=["bird-a.jpg"],
        only_providers={"cpu", "intel_npu"},
    )

    assert sorted(probed) == ["cpu", "intel_npu"]
    assert sorted(result["eligible_providers"]) == ["cpu", "intel_npu"]


def test_probe_report_parser_ignores_structured_logs_before_the_final_report():
    stdout = b'{"event":"loading"}\nnoise\n{"provider":"cuda","compile":{"ok":true}}\n'

    assert mv._parse_probe_report(stdout) == {"provider": "cuda", "compile": {"ok": True}}


def test_crop_probe_labels_reused_basenames_uniquely(tmp_path):
    first = tmp_path / "species-a" / "image.jpg"
    second = tmp_path / "species-b" / "image.jpg"
    first.parent.mkdir()
    second.parent.mkdir()
    Image.new("RGB", (8, 8), "red").save(first)
    Image.new("RGB", (8, 8), "blue").save(second)

    rows = _load_images([str(first), str(second)], input_size=64)

    real_labels = [label for label, _image in rows if label.startswith("real:")]
    assert real_labels == ["real:000:image.jpg", "real:001:image.jpg"]
    assert len(real_labels) == len(set(real_labels))


def test_crop_probe_ignores_raw_proposals_below_the_runtime_evidence_floor():
    service = BirdCropService(detector_tier="accurate")
    image = Image.new("RGB", (200, 200), "black")

    below = _top_detection(
        service,
        [{"box": [20, 20, 180, 180], "confidence": 0.004}],
        image,
        tier="accurate",
    )
    admitted = _top_detection(
        service,
        [{"box": [20, 20, 180, 180], "confidence": 0.021}],
        image,
        tier="accurate",
    )

    assert below is None
    assert admitted is not None
    assert admitted["confidence"] == pytest.approx(0.021)


class _FakeManager:
    def __init__(self, active):
        self.active_model_id = active
        self.activations = []

    async def activate_model(self, model_id):
        self.activations.append(model_id)
        self.active_model_id = model_id
        return True

    async def restore_active_model(self, model_id):
        self.activations.append(model_id)
        self.active_model_id = model_id


class _FakeClassifier:
    def __init__(self, results, provider="cpu"):
        self._results = results
        self._provider = provider
        self.reloads = 0

    async def reload_bird_model(self):
        self.reloads += 1

    def get_status(self):
        return {"active_provider": self._provider}

    def classify(self, image, input_context=None):
        return self._results


def _patch(monkeypatch, tmp_path, manager, classifier):
    monkeypatch.setenv("YAWAMF_EVAL_RUNS_DIR", str(tmp_path))
    monkeypatch.setattr("app.services.model_manager.model_manager", manager)
    monkeypatch.setattr("app.services.classifier_service.get_classifier", lambda: classifier)

    # These tests exercise the last-resort live-classifier fallback. Keep them
    # independent of runtimes exposed by the developer machine.
    async def _no_provider_sweep(_model_id):
        return {
            "image_flavor": "unknown",
            "providers": [],
            "devices": [],
            "eligible_providers": [],
            "best": None,
        }

    monkeypatch.setattr(mv, "sweep_model_devices", _no_provider_sweep)


@pytest.mark.asyncio
async def test_probe_success_writes_validated_record(tmp_path, monkeypatch):
    manager = _FakeManager(active="rope_vit")
    classifier = _FakeClassifier([{"label": "House Finch", "score": 0.9}], provider="intel_gpu")
    _patch(monkeypatch, tmp_path, manager, classifier)

    result = await mv.run_validation_probe("small_birds")

    assert result["ok"] is True
    assert result["provider"] == "intel_gpu"
    # Inference latency is measured and recorded so the wizard can report it.
    assert isinstance(result["latency_ms"], float)
    assert result["latency_ms"] >= 0
    record = mv.read_validation_record("small_birds")
    assert record["validated"] is True
    assert record["provider"] == "intel_gpu"
    assert "latency_ms" in record


@pytest.mark.asyncio
async def test_probe_restores_previous_active_model(tmp_path, monkeypatch):
    manager = _FakeManager(active="rope_vit")
    classifier = _FakeClassifier([{"label": "x", "score": 0.5}])
    _patch(monkeypatch, tmp_path, manager, classifier)

    await mv.run_validation_probe("small_birds")

    # trial-activated the candidate, then restored the original
    assert manager.activations == ["small_birds", "rope_vit"]
    assert manager.active_model_id == "rope_vit"


@pytest.mark.asyncio
async def test_probe_failure_writes_failed_record_and_restores(tmp_path, monkeypatch):
    manager = _FakeManager(active="rope_vit")
    classifier = _FakeClassifier([{"label": "x", "score": float("nan")}])
    _patch(monkeypatch, tmp_path, manager, classifier)

    result = await mv.run_validation_probe("eva02_large_inat21")

    assert result["ok"] is False
    assert mv.read_validation_record("eva02_large_inat21")["validated"] is False
    # gate stays closed for a failed model
    ok, _ = mv.is_model_validated("eva02_large_inat21", active_model_id="rope_vit", bundled_ids=set())
    assert ok is False
    # original model still restored
    assert manager.active_model_id == "rope_vit"


@pytest.mark.asyncio
async def test_probe_restores_even_when_classify_raises(tmp_path, monkeypatch):
    manager = _FakeManager(active="rope_vit")

    class _Boom(_FakeClassifier):
        def classify(self, image, input_context=None):
            raise RuntimeError("driver crash")

    classifier = _Boom([])
    _patch(monkeypatch, tmp_path, manager, classifier)

    result = await mv.run_validation_probe("eva02_large_inat21")

    assert result["ok"] is False
    assert "errored" in result["reason"]
    assert manager.active_model_id == "rope_vit"


@pytest.mark.asyncio
async def test_published_image_without_a_candidate_fails_closed_and_clears_stale_evidence(tmp_path, monkeypatch):
    manager = _FakeManager(active="rope_vit")

    class _MustNotClassify(_FakeClassifier):
        def classify(self, image, input_context=None):
            raise AssertionError("live fallback must not validate a different model in a published image")

    classifier = _MustNotClassify([])
    monkeypatch.setenv("YAWAMF_IMAGE_FLAVOR", "cpu")
    _patch(monkeypatch, tmp_path, manager, classifier)
    mv.write_eligibility_entry("small_birds", ["cpu"], image_flavor="cpu")

    async def _no_packaged_candidate(_model_id):
        return {
            "image_flavor": "cpu",
            "providers": [],
            "devices": [],
            "eligible_providers": [],
            "best": None,
        }

    monkeypatch.setattr(mv, "sweep_model_devices", _no_packaged_candidate)

    result = await mv.run_validation_probe("small_birds")

    assert result["ok"] is False
    assert "no compatible provider runtime" in result["reason"]
    assert mv.host_eligible_providers("small_birds") == []
    assert mv.read_validation_record("small_birds")["validated"] is False


@pytest.mark.asyncio
async def test_provider_guard_prevents_quarantined_native_probe(monkeypatch):
    from app.services import classifier_service
    from app.services.model_manager import model_manager
    from app.services.native_crash_quarantine import NativeCrashQuarantinedError

    monkeypatch.setenv("YAWAMF_IMAGE_FLAVOR", "intel")
    monkeypatch.setattr(
        classifier_service,
        "_detect_acceleration_capabilities",
        lambda: {
            "ort_available": True,
            "openvino_available": True,
            "intel_cpu_available": True,
            "intel_gpu_available": True,
        },
    )
    monkeypatch.setattr(
        model_manager,
        "get_active_model_spec",
        lambda: {
            "model_id": "bird",
            "runtime": "onnx",
            "supported_inference_providers": ["cpu", "intel_cpu", "intel_gpu"],
        },
    )
    calls = []

    def guard(provider):
        if provider == "intel_cpu":
            raise NativeCrashQuarantinedError("retained fault")

    async def probe(provider, **_kwargs):
        calls.append(provider)
        return {
            "compile": {"ok": True},
            "output_summary": {"finite_count": 2, "element_count": 2},
            "per_image_top_indices": [[1, 0]],
            "inference_latency_ms": 10,
        }

    monkeypatch.setattr(mv, "_probe_one_provider", probe)
    result = await mv.sweep_model_devices("bird", provider_guard=guard)
    assert calls == ["cpu", "intel_gpu"]
    assert result["eligible_providers"] == ["cpu", "intel_gpu"]
    assert next(p for p in result["providers"] if p["provider"] == "intel_cpu")["ok"] is False


@pytest.mark.parametrize("cpu_detects_bird", [False, True])
@pytest.mark.asyncio
async def test_crop_sweep_keeps_finite_cpu_without_accelerator_agreement(monkeypatch, tmp_path, cpu_detects_bird):
    from app.services import classifier_service
    from app.services.model_manager import model_manager

    monkeypatch.setenv("YAWAMF_EVAL_RUNS_DIR", str(tmp_path))
    monkeypatch.setenv("YAWAMF_IMAGE_FLAVOR", "intel")
    monkeypatch.setattr(
        classifier_service,
        "_detect_acceleration_capabilities",
        lambda: {
            "ort_available": True,
            "openvino_available": True,
            "intel_npu_available": True,
        },
    )
    monkeypatch.setattr(
        model_manager,
        "get_crop_detector_spec_by_model_id",
        lambda _: {
            "healthy": True,
            "metadata": {"runtime": "onnx", "supported_inference_providers": ["cpu", "intel_npu"]},
        },
    )

    async def probe(provider, **kwargs):
        return {
            "compile": {"ok": True},
            "output_summary": {"finite_count": 1, "element_count": 1},
            "per_image_detections": [
                {
                    "image": "bird.jpg",
                    "kind": "real",
                    "top_detection": (
                        {"normalized_box": [0.1, 0.1, 0.5, 0.5], "confidence": 0.8}
                        if cpu_detects_bird and provider == "cpu"
                        else None
                    ),
                }
            ],
        }

    monkeypatch.setattr(mv, "_probe_one_crop_provider", probe)
    result = await mv.sweep_crop_model_devices("finder")
    assert result["eligible_providers"] == ["cpu"]
    mv.write_eligibility_entry(
        "finder",
        result["eligible_providers"],
        provider_results=result["providers"],
        artifact_sha256="abc",
        image_flavor="intel",
    )
    assert mv.host_eligible_providers("finder", artifact_sha256="abc") == ["cpu"]
    data = mv._read_current_eligibility_payload()
    assert data["model_provider_signatures"]["finder"]["cpu"] == mv.current_provider_runtime_signature("cpu")


def test_crop_comparison_matches_all_boxes_independently_of_score_order():
    left = {"normalized_box": [0.1, 0.2, 0.3, 0.5], "confidence": 0.8}
    right = {"normalized_box": [0.6, 0.2, 0.8, 0.5], "confidence": 0.79}
    baseline = [{"image": "birds", "detections": [left, right], "top_detection": left}]
    provider = [
        {
            "image": "birds",
            "detections": [dict(right, confidence=0.80), dict(left, confidence=0.79)],
            "top_detection": right,
        }
    ]
    result = mv._compare_crop_detections(baseline, provider)
    assert result["agrees"] is True
    assert result["baseline_boxes"] == result["provider_boxes"] == result["matched_boxes"] == 2
    assert result["worst_box_iou"] == 1.0


@pytest.mark.parametrize("extra", [True, False])
def test_crop_comparison_rejects_extra_or_missing_birds(extra):
    bird = {"normalized_box": [0.1, 0.2, 0.3, 0.5], "confidence": 0.8}
    other = {"normalized_box": [0.6, 0.2, 0.8, 0.5], "confidence": 0.8}
    baseline = [{"image": "birds", "detections": [bird], "top_detection": bird}]
    provider = [{"image": "birds", "detections": [bird, other] if extra else [], "top_detection": bird}]
    assert mv._compare_crop_detections(baseline, provider)["agrees"] is False


def test_crop_comparison_uses_the_same_score_floor_on_both_sides():
    bird = {"normalized_box": [0.1, 0.2, 0.3, 0.5], "confidence": 0.8}
    noise = {"normalized_box": [0.6, 0.2, 0.8, 0.5], "confidence": 0.01}
    result = mv._compare_crop_detections(
        [{"image": "birds", "detections": [noise, bird]}],
        [{"image": "birds", "detections": [bird]}],
    )
    assert result["agrees"] is True


def test_crop_comparison_allows_small_localization_drift_but_rejects_a_different_bird():
    bird = {"normalized_box": [0.1, 0.2, 0.3, 0.5], "confidence": 0.8}
    baseline = [{"image": "birds", "detections": [bird]}]
    shifted = dict(bird, normalized_box=[0.11, 0.2, 0.31, 0.5])
    assert mv._compare_crop_detections(baseline, [{"image": "birds", "detections": [shifted]}])["agrees"] is True
    shifted["normalized_box"] = [0.6, 0.2, 0.8, 0.5]
    assert mv._compare_crop_detections(baseline, [{"image": "birds", "detections": [shifted]}])["agrees"] is False


def test_crop_probe_reads_tiles_and_merges_the_same_boxes_as_runtime():
    from scripts.probe_crop_model_provider import _ProbeCropService, _admitted_detections

    import numpy as np

    calls = []

    class Session:
        def run(self, *_args):
            calls.append(True)
            return [np.ones((1, 2))]

    service = _ProbeCropService(detector_tier="accurate")
    service._parse_detector_outputs = lambda outputs, **kwargs: [{"box": [20, 20, 120, 120], "confidence": 0.8}]
    model = {
        "session": Session(),
        "input_width": 384,
        "input_height": 384,
        "detector_config": {"frame_scan": {"tile_grid": 2, "tile_overlap": 0.2}},
    }
    image = Image.new("RGB", (1920, 1080))
    candidates = service._infer_candidates_on_model(model, image)
    assert len(calls) == 5
    assert len(service.outputs) == 5
    detections = _admitted_detections(service, candidates, image, tier="accurate")
    assert len(detections) > 1


def test_crop_box_matching_reassigns_an_ambiguous_box_to_cover_both_birds():
    def bird(left):
        return {"normalized_box": [left, 0.1, left + 0.5, 0.6], "confidence": 0.8}

    baseline = [{"image": "birds", "detections": [bird(0.1), bird(0.135)]}]
    provider = [{"image": "birds", "detections": [bird(0.115), bird(0.07)]}]
    result = mv._compare_crop_detections(baseline, provider)
    assert result["agrees"] is True
    assert result["matched_boxes"] == 2


@pytest.mark.parametrize("delta", [0.01, 0.031])
def test_crop_box_matching_keeps_confidence_agreement_as_a_separate_gate(delta):
    box = {"normalized_box": [0.1, 0.2, 0.3, 0.5], "confidence": 0.8}
    result = mv._compare_crop_detections(
        [{"image": "bird", "detections": [box]}],
        [{"image": "bird", "detections": [dict(box, confidence=0.8 + delta)]}],
    )
    assert result["agrees"] is (delta <= 0.03)


@pytest.mark.parametrize("score, agrees", [(0.021, True), (0.05, False), (0.2, False)])
def test_unmatched_boxes_only_disagree_above_the_score_tolerance_band(score, agrees):
    left = [{"image": "bird", "detections": [{"normalized_box": [0.1, 0.1, 0.4, 0.4], "confidence": score}]}]
    right = [{"image": "bird", "detections": [{"normalized_box": [0.1, 0.1, 0.4, 0.4], "confidence": 0.019}]}]
    assert mv._compare_crop_detections(left, right)["agrees"] is agrees
    assert mv._compare_crop_detections(right, left)["agrees"] is agrees


def test_comparison_matches_nms_survivor_groups_without_lowering_localization_iou():
    full = {"normalized_box": [0.1, 0.1, 0.5, 0.5], "confidence": 0.81}
    cut = {"normalized_box": [0.2, 0.1, 0.5, 0.5], "confidence": 0.80}
    cpu = dict(full, alternatives=[full, cut])
    npu = dict(cut, confidence=0.81, alternatives=[dict(full, confidence=0.80), dict(cut, confidence=0.81)])
    assert mv._normalized_box_iou(full["normalized_box"], cut["normalized_box"]) < 0.85
    assert (
        mv._compare_crop_detections([{"image": "bird", "detections": [cpu]}], [{"image": "bird", "detections": [npu]}])[
            "agrees"
        ]
        is True
    )


def test_probe_retains_actual_nms_suppression_groups():
    from scripts.probe_crop_model_provider import _ProbeCropService

    boxes = [{"box": [10, 10, 50, 50], "confidence": 0.81}, {"box": [20, 10, 50, 50], "confidence": 0.80}]
    groups = _ProbeCropService._merge_duplicate_boxes(boxes)
    assert len(groups) == 1
    assert len(groups[0]["comparison_alternatives"]) == 2


def test_nms_alternatives_do_not_hide_a_strong_confidence_regression():
    def row(score):
        return {
            "image": "bird",
            "detections": [
                {
                    "normalized_box": [0.1, 0.1, 0.5, 0.5],
                    "confidence": score,
                    "alternatives": [{"normalized_box": [0.1, 0.1, 0.5, 0.5], "confidence": 0.4}],
                }
            ],
        }

    assert not mv._compare_crop_detections([row(0.9)], [row(0.7)])["agrees"]
