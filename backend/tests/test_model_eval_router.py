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
