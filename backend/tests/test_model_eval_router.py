import json
from pathlib import Path

import pytest
import httpx
from fastapi import FastAPI

from app.auth import AuthLevel, create_access_token
from app.config import settings
from app.routers import model_eval as router


@pytest.mark.asyncio
async def test_device_matrix_artifact_is_downloadable(tmp_path: Path, monkeypatch):
    artifact = tmp_path / "device_matrix.json"
    artifact.write_text('{"providers":["cpu"]}', encoding="utf-8")
    monkeypatch.setattr(router.model_eval_runner, "artifact_path", lambda _run_id, _filename: artifact)

    response = await router.get_artifact("20260721-120000", router.DEVICE_MATRIX_FILENAME, _auth=object())

    assert Path(response.path) == artifact
    assert response.media_type == "application/json"


@pytest.mark.asyncio
@pytest.mark.parametrize("artifact", ["summary.json", "runtime.json", "confusions.csv"])
async def test_eval_download_requires_owner_header_and_survives_username_change(tmp_path, monkeypatch, artifact):
    monkeypatch.setattr(settings.auth, "enabled", True)
    monkeypatch.setattr(settings.public_access, "enabled", True)
    monkeypatch.setattr(settings.auth, "username", "renamed-owner")
    monkeypatch.setattr(settings, "api_key", None)
    path = tmp_path / artifact
    path.write_text("retained evaluation")
    monkeypatch.setattr(router.model_eval_runner, "artifact_path", lambda _run_id, _filename: path)
    app = FastAPI()
    app.include_router(router.router, prefix="/api")
    token = create_access_token("original-owner", AuthLevel.OWNER)
    url = f"/api/diagnostics/model-eval/runs/test-run/{artifact}"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        denied = await client.get(url)
        assert denied.status_code == 403
        allowed = await client.get(url, headers={"Authorization": f"Bearer {token}"})
        assert allowed.status_code == 200
        assert allowed.text == "retained evaluation"
        assert allowed.headers["content-disposition"].endswith(f'filename="{artifact}"')


def _write_run(root: Path, run_id: str, summary: dict) -> None:
    run_dir = root / run_id
    run_dir.mkdir()
    (run_dir / "summary.json").write_text(json.dumps({"run_id": run_id, **summary}), encoding="utf-8")


async def _owner_get(path: str) -> httpx.Response:
    app = FastAPI()
    app.include_router(router.router, prefix="/api")
    app.dependency_overrides[router.require_owner] = lambda: object()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        return await client.get(path)


@pytest.mark.asyncio
async def test_a_run_is_answered_in_its_declared_shape(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("YAWAMF_EVAL_RUNS_DIR", str(tmp_path))
    _write_run(
        tmp_path,
        "20261114-081500",
        {
            "started_at": "2026-11-14T08:15:00+00:00",
            "finished_at": "2026-11-14T08:31:12+00:00",
            "duration_seconds": 972,
            "test_set": {
                "total_species": 141,
                "total_images": 423,
                "region": "GB-ENG",
                "image_sources": {"inaturalist": 401},
            },
            "models": [
                {
                    "model_id": "small_birds",
                    "ready": True,
                    "active_provider": "cpu",
                    "top1_accuracy": 0.74,
                    "warnings": [
                        {"code": "high_abstention", "message": "abstained on 12.0% of images", "severity": "warning"}
                    ],
                    "labels_file_present": True,
                }
            ],
            "skipped_models": [{"model_id": "eva02", "reason": "reload_failed", "detail": "Traceback: boom at 0x7f"}],
            "config_snapshot": {"min_confidence": 0.4},
        },
    )

    response = await _owner_get("/api/diagnostics/model-eval/runs/20261114-081500")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "run_id",
        "started_at",
        "finished_at",
        "duration_seconds",
        "test_set",
        "models",
        "skipped_models",
        "error_code",
        "available_artifacts",
        "in_progress",
    }
    assert body["available_artifacts"] == ["summary.json"]
    assert body["in_progress"] is False
    assert body["error_code"] is None
    assert body["test_set"]["total_species"] == 141
    assert body["models"][0]["model_id"] == "small_birds"
    assert body["models"][0]["warnings"] == [
        {"code": "high_abstention", "message": "abstained on 12.0% of images", "severity": "warning"}
    ]
    # A skipped model says why with a code; what the loader raised stays in the log.
    assert body["skipped_models"] == [{"model_id": "eva02", "reason": "reload_failed"}]
    assert "Traceback" not in response.text


@pytest.mark.asyncio
async def test_a_failed_run_answers_with_a_stable_code_and_never_the_exception_text(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("YAWAMF_EVAL_RUNS_DIR", str(tmp_path))
    _write_run(tmp_path, "20261114-090000", {"error_code": "no_test_photos", "models": []})
    # A run written before failures carried a code holds only what was raised.
    _write_run(tmp_path, "20261101-090000", {"error": "ConnectError('[Errno 111] refused') at 0x7f", "models": []})

    coded = await _owner_get("/api/diagnostics/model-eval/runs/20261114-090000")
    legacy = await _owner_get("/api/diagnostics/model-eval/runs/20261101-090000")
    listing = await _owner_get("/api/diagnostics/model-eval/runs")

    assert coded.json()["error_code"] == "no_test_photos"
    assert legacy.json()["error_code"] == "unexpected"
    assert "error" not in legacy.json()
    rows = {row["run_id"]: row for row in listing.json()["runs"]}
    assert rows["20261114-090000"]["error_code"] == "no_test_photos"
    assert rows["20261101-090000"]["error_code"] == "unexpected"
    assert listing.json()["active"] is None
    for response in (coded, legacy, listing):
        assert "ConnectError" not in response.text


def test_the_run_contract_is_part_of_the_openapi_schema():
    app = FastAPI()
    app.include_router(router.router, prefix="/api")
    schema = app.openapi()

    run = schema["paths"]["/api/diagnostics/model-eval/runs/{run_id}"]["get"]["responses"]["200"]["content"]
    assert run["application/json"]["schema"] == {"$ref": "#/components/schemas/ModelEvalRunResponse"}
    properties = schema["components"]["schemas"]["ModelEvalRunResponse"]["properties"]
    assert properties["available_artifacts"]["items"] == {"type": "string"}
    assert "error" not in properties
    listing = schema["paths"]["/api/diagnostics/model-eval/runs"]["get"]["responses"]["200"]["content"]
    assert listing["application/json"]["schema"] == {"$ref": "#/components/schemas/ModelEvalListResponse"}
