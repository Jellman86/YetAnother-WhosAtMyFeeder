"""The host-agnostic validation probe: judging, record-writing, and restore-on-exit.

The probe is exercised with a fake classifier and fake manager so no real model,
network, or accelerator is touched.
"""

import pytest

from app.services import model_validation as mv


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
