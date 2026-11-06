from app.services.bird_crop_service import BirdCropService


def test_loaded_crop_adopts_a_new_host_recommendation_without_a_worker_restart(monkeypatch):
    service = BirdCropService()
    preference = ["cpu"]
    loads = []
    monkeypatch.setattr(service, "_provider_for_tier", lambda tier: preference[0])
    monkeypatch.setattr(service, "_registry_model_id_for_tier", lambda tier: "rfdetr")

    def load(tier):
        model = {"provider": preference[0]}
        loads.append(model)
        return model

    monkeypatch.setattr(service, "_load_model_for_tier", load)
    cpu = service._ensure_model_for_tier("accurate")
    preference[0] = "intel_gpu"
    gpu = service._ensure_model_for_tier("accurate")
    assert cpu["provider"] == "cpu"
    assert gpu["provider"] == "intel_gpu"
    assert service._ensure_model_for_tier("accurate") is gpu
    assert len(loads) == 2
    preference[0] = "cpu"
    assert service._ensure_model_for_tier("accurate")["provider"] == "cpu"
    assert len(loads) == 3


def test_cpu_recovery_is_not_retried_on_every_frame_while_recommendation_is_unchanged(monkeypatch):
    service = BirdCropService()
    loads = []
    monkeypatch.setattr(service, "_provider_for_tier", lambda tier: "intel_gpu")
    monkeypatch.setattr(service, "_registry_model_id_for_tier", lambda tier: "rfdetr")

    def load(tier):
        loads.append(tier)
        service._active_providers[tier] = "cpu"
        service._provider_fallbacks[tier] = "intel_gpu"
        return {"provider": "cpu"}

    monkeypatch.setattr(service, "_load_model_for_tier", load)
    first = service._ensure_model_for_tier("accurate")
    assert service._ensure_model_for_tier("accurate") is first
    assert loads == ["accurate"]
    assert service._provider_fallbacks["accurate"] == "intel_gpu"
