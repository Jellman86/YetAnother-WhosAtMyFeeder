import uuid
import io
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from PIL import Image

from app.auth import AuthContext, AuthLevel, require_owner
from app.main import app
from app.config import settings
from app.database import get_db, init_db, close_db
from app.routers import classifier as classifier_router


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture(autouse=True)
async def ensure_db_initialized():
    await init_db()
    try:
        yield
    finally:
        await close_db()


@pytest.fixture(autouse=True)
def reset_auth_config():
    original_auth_enabled = settings.auth.enabled
    original_public_enabled = settings.public_access.enabled
    yield
    settings.auth.enabled = original_auth_enabled
    settings.public_access.enabled = original_public_enabled
    app.dependency_overrides.pop(require_owner, None)


@pytest.mark.asyncio
async def test_classifier_status_includes_personalization_summary(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    event_prefix = f"status-{uuid.uuid4().hex[:8]}"
    async with get_db() as db:
        for idx in range(20):
            await db.execute(
                """
                INSERT INTO classification_feedback (
                    frigate_event, camera_name, model_id, predicted_label, corrected_label, predicted_score, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"{event_prefix}-{idx}",
                    "front",
                    "default",
                    "Blue Tit",
                    "Great Tit",
                    0.82,
                    "manual_tag",
                ),
            )
        await db.commit()

    try:
        response = await client.get("/api/classifier/status")
        assert response.status_code == 200, response.text
        payload = response.json()

        assert "personalized_rerank_enabled" in payload
        assert payload["personalization_min_feedback_tags"] == 20
        assert payload["personalization_feedback_rows"] >= 20
        assert payload["personalization_active_camera_models"] >= 1
    finally:
        async with get_db() as db:
            await db.execute("DELETE FROM classification_feedback WHERE frigate_event LIKE ?", (f"{event_prefix}-%",))
            await db.commit()


@pytest.mark.asyncio
async def test_classifier_test_endpoint_uses_supervised_path_in_subprocess_mode(client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch):
    original_mode = settings.classification.image_execution_mode
    original_execution_mode = classifier_router.classifier_service._image_execution_mode
    settings.classification.image_execution_mode = "subprocess"
    classifier_router.classifier_service._image_execution_mode = "subprocess"
    app.dependency_overrides[require_owner] = lambda: AuthContext(auth_level=AuthLevel.OWNER, username="owner")

    async def _fake_background_classify(_image, camera_name=None, model_id=None, input_context=None):
        assert input_context == {"is_cropped": False}
        return [{"label": "Robin", "score": 0.93, "index": 1}]

    monkeypatch.setattr(
        classifier_router.classifier_service,
        "classify",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("direct classify should not be used")),
    )
    monkeypatch.setattr(
        classifier_router.classifier_service,
        "classify_async_background",
        _fake_background_classify,
    )
    image_buffer = io.BytesIO()
    Image.new("RGB", (8, 8), color="white").save(image_buffer, format="PNG")

    try:
        response = await client.post(
            "/api/classifier/test",
            files={"image": ("bird.png", image_buffer.getvalue(), "image/png")},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["status"] == "ok"
        assert payload["results"][0]["label"] == "Robin"
    finally:
        classifier_router.classifier_service._image_execution_mode = original_execution_mode
        settings.classification.image_execution_mode = original_mode


@pytest.mark.asyncio
async def test_classifier_test_endpoint_uses_in_process_path_by_default(client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch):
    original_mode = settings.classification.image_execution_mode
    settings.classification.image_execution_mode = "in_process"

    fake_classifier = SimpleNamespace(_image_execution_mode="in_process")
    seen_input_contexts: list[object] = []

    def _fake_classify(_image, input_context=None):
        seen_input_contexts.append(input_context)
        return [{"label": "Robin", "score": 0.93, "index": 1}]

    fake_classifier.classify = _fake_classify

    classify_async_background_called = False

    async def _unexpected_async_background(*_args, **_kwargs):
        nonlocal classify_async_background_called
        classify_async_background_called = True
        raise AssertionError("async background path should not be used in in-process mode")

    fake_classifier.classify_async_background = _unexpected_async_background
    monkeypatch.setattr(classifier_router, "classifier_service", fake_classifier)
    app.dependency_overrides[require_owner] = lambda: AuthContext(auth_level=AuthLevel.OWNER, username="owner")

    image_buffer = io.BytesIO()
    Image.new("RGB", (8, 8), color="white").save(image_buffer, format="PNG")

    try:
        response = await client.post(
            "/api/classifier/test",
            files={"image": ("bird.png", image_buffer.getvalue(), "image/png")},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["status"] == "ok"
        assert payload["results"][0]["label"] == "Robin"
        assert seen_input_contexts == [{"is_cropped": False}]
        assert classify_async_background_called is False
    finally:
        settings.classification.image_execution_mode = original_mode


@pytest.mark.asyncio
async def test_classifier_probe_endpoint_returns_runtime_diagnostics_for_synthetic_gpu_probe(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    app.dependency_overrides[require_owner] = lambda: AuthContext(auth_level=AuthLevel.OWNER, username="owner")

    monkeypatch.setattr(
        classifier_router.classifier_service,
        "probe_bird_runtime",
        lambda **_kwargs: {
            "device": "GPU",
            "synthetic_image": True,
            "status": "invalid_output",
            "runtime": {
                "backend": "openvino",
                "provider": "intel_gpu",
            },
            "model": {
                "model_path": "/models/bird.onnx",
                "input_size": 384,
                "model_type": "onnx",
            },
            "compile_properties": {
                "INFERENCE_PRECISION_HINT": "f32",
                "NUM_STREAMS": "1",
            },
            "output_summary": {
                "nan_count": 10000,
                "finite_count": 0,
            },
        },
    )

    response = await client.post("/api/classifier/probe", params={"device": "GPU", "synthetic_image": "true"})
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["device"] == "GPU"
    assert payload["synthetic_image"] is True
    assert payload["runtime"]["backend"] == "openvino"
    assert payload["compile_properties"]["INFERENCE_PRECISION_HINT"] == "f32"
    assert payload["output_summary"]["nan_count"] == 10000


@pytest.mark.asyncio
async def test_classifier_status_endpoint_returns_artifact_fingerprint_and_compatibility(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        classifier_router.classifier_service,
        "get_status",
        lambda: {
            "loaded": True,
            "labels_loaded": 10000,
            "selected_provider": "auto",
            "active_provider": "intel_gpu",
            "inference_backend": "openvino",
            "openvino_runtime": {
                "selected_provider": "auto",
                "active_provider": "intel_gpu",
                "inference_backend": "openvino",
                "model": {
                    "model_path": "/models/bird.onnx",
                    "input_size": 384,
                    "model_sha256": "abc123",
                    "weights_sha256": "def456",
                    "producer_name": "pytorch",
                    "producer_version": "2.9.1",
                    "opset": [{"domain": "ai.onnx", "version": 18}],
                },
                "compatibility": {
                    "devices": {
                        "GPU": {
                            "artifact_trust_state": "untrusted",
                            "last_probe_status": "invalid_output",
                        },
                        "CPU": {
                            "artifact_trust_state": "trusted",
                            "last_probe_status": "ok",
                        },
                    },
                },
            },
        },
    )

    response = await client.get("/api/classifier/status")
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["openvino_runtime"]["model"]["model_sha256"] == "abc123"
    assert payload["openvino_runtime"]["model"]["weights_sha256"] == "def456"
    assert payload["openvino_runtime"]["model"]["producer_name"] == "pytorch"
    assert payload["openvino_runtime"]["model"]["producer_version"] == "2.9.1"
    assert payload["openvino_runtime"]["model"]["opset"] == [{"domain": "ai.onnx", "version": 18}]
    assert payload["openvino_runtime"]["compatibility"]["devices"]["GPU"]["artifact_trust_state"] == "untrusted"
    assert payload["openvino_runtime"]["compatibility"]["devices"]["GPU"]["last_probe_status"] == "invalid_output"
    assert payload["openvino_runtime"]["compatibility"]["devices"]["CPU"]["artifact_trust_state"] == "trusted"
