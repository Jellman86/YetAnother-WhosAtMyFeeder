"""The post-install selection gate on POST /api/models/{id}/activate.

An installed-but-unvalidated model must be rejected (409) through the API no
matter the caller; a validated (or grandfathered) model activates normally.
"""

import httpx
import pytest
import pytest_asyncio

from app.config import settings
from app.main import app
from app.models.ai_models import InstalledModel
from app.routers import models as models_router


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture(autouse=True)
def no_auth():
    original = settings.auth.enabled
    settings.auth.enabled = False
    yield
    settings.auth.enabled = original


def _installed(model_id: str, *, validated: bool) -> InstalledModel:
    return InstalledModel(
        id=model_id,
        path=f"/data/models/{model_id}/model.onnx",
        labels_path=f"/data/models/{model_id}/labels.txt",
        is_active=False,
        validated=validated,
        validation_reason="probe" if validated else "unvalidated",
    )


@pytest.fixture
def stub_activation(monkeypatch):
    """Neutralise the real activation side effects (settings write + classifier reload)
    so the tests exercise only the gate."""
    activated: dict = {}

    async def fake_activate(model_id: str) -> bool:
        activated["id"] = model_id
        return True

    async def fake_save(self):
        return None

    class _Stub:
        async def reload_bird_model(self):
            return None

    monkeypatch.setattr(models_router.model_manager, "activate_model", fake_activate)
    monkeypatch.setattr(type(settings), "save", fake_save)
    monkeypatch.setattr(models_router, "get_classifier", lambda: _Stub())
    return activated


@pytest.mark.asyncio
async def test_activate_unvalidated_model_is_blocked(client, monkeypatch, stub_activation):
    async def fake_installed():
        return [_installed("eva02_large_inat21", validated=False)]

    monkeypatch.setattr(models_router.model_manager, "list_installed_models", fake_installed)

    resp = await client.post("/api/models/eva02_large_inat21/activate")
    assert resp.status_code == 409, resp.text
    assert "validated" in resp.json()["detail"].lower()
    assert "id" not in stub_activation  # activation never ran


@pytest.mark.asyncio
async def test_activate_validated_model_succeeds(client, monkeypatch, stub_activation):
    async def fake_installed():
        return [_installed("small_birds", validated=True)]

    monkeypatch.setattr(models_router.model_manager, "list_installed_models", fake_installed)

    resp = await client.post("/api/models/small_birds/activate")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "success"
    assert stub_activation["id"] == "small_birds"


@pytest.mark.asyncio
async def test_activation_applies_the_verified_provider_only_after_model_activation(
    client, monkeypatch, stub_activation
):
    async def fake_installed():
        return [_installed("small_birds", validated=True)]

    monkeypatch.setattr(models_router.model_manager, "list_installed_models", fake_installed)
    monkeypatch.setattr(
        models_router,
        "activation_provider_recommendation",
        lambda _model_id: "cuda",
    )
    original_provider = settings.classification.inference_provider
    try:
        resp = await client.post("/api/models/small_birds/activate")
        assert resp.status_code == 200, resp.text
        assert stub_activation["id"] == "small_birds"
        assert settings.classification.inference_provider == "cuda"
    finally:
        settings.classification.inference_provider = original_provider


@pytest.mark.asyncio
async def test_activate_missing_model_is_404(client, monkeypatch, stub_activation):
    async def fake_installed():
        return [_installed("small_birds", validated=True)]

    monkeypatch.setattr(models_router.model_manager, "list_installed_models", fake_installed)

    resp = await client.post("/api/models/does_not_exist/activate")
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_validate_route_runs_probe_and_returns_result(client, monkeypatch):
    async def fake_installed():
        return [_installed("small_birds", validated=False)]

    async def fake_probe(model_id):
        return {"model_id": model_id, "ok": True, "provider": "cpu", "reason": "finite"}

    monkeypatch.setattr(models_router.model_manager, "list_installed_models", fake_installed)
    monkeypatch.setattr(models_router, "run_validation_probe", fake_probe)

    resp = await client.post("/api/models/small_birds/validate")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["model_id"] == "small_birds"
    assert body["provider_set"] is False


@pytest.mark.asyncio
async def test_validate_route_404_for_missing_model(client, monkeypatch):
    async def fake_installed():
        return []

    monkeypatch.setattr(models_router.model_manager, "list_installed_models", fake_installed)

    resp = await client.post("/api/models/nope/validate")
    assert resp.status_code == 404, resp.text
