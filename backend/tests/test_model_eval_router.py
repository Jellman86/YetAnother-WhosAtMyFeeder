from pathlib import Path

import pytest

from app.routers import model_eval as router


@pytest.mark.asyncio
async def test_device_matrix_artifact_is_downloadable(tmp_path: Path, monkeypatch):
    artifact = tmp_path / "device_matrix.json"
    artifact.write_text('{"providers":["cpu"]}', encoding="utf-8")
    monkeypatch.setattr(router.model_eval_runner, "artifact_path", lambda _run_id, _filename: artifact)

    response = await router.get_artifact("20260721-120000", router.DEVICE_MATRIX_FILENAME, _auth=object())

    assert Path(response.path) == artifact
    assert response.media_type == "application/json"
