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
