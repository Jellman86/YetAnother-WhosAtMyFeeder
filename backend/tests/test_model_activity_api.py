"""`GET /api/models/activity`: downloads and hardware checks in progress, for every surface and tab."""

from datetime import datetime

import httpx
import pytest
import pytest_asyncio

from app.config import settings
from app.main import app
from app.models.ai_models import DownloadProgress
from app.routers import models as models_router
from app.services.model_activity import GARDEN_CHECK_MODEL, model_activity
from app.services.model_manager import model_manager


@pytest_asyncio.fixture
async def client(monkeypatch):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    monkeypatch.setattr(model_manager, "active_downloads", {})
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


@pytest.mark.asyncio
async def test_nothing_in_progress_is_an_empty_answer(client):
    response = await client.get("/api/models/activity")

    assert response.status_code == 200, response.text
    assert response.json() == {"activity": {}}


@pytest.mark.asyncio
async def test_a_running_download_is_reported_and_a_finished_one_is_not(client):
    model_manager.active_downloads["small_birds"] = (
        DownloadProgress(model_id="small_birds", status="downloading", progress=40),
        datetime.now(),
    )
    model_manager.active_downloads["rope"] = (
        DownloadProgress(model_id="rope", status="completed", progress=100),
        datetime.now(),
    )

    assert (await client.get("/api/models/activity")).json() == {"activity": {"small_birds": "downloading"}}


@pytest.mark.asyncio
async def test_a_validation_is_reported_while_its_request_runs(client, monkeypatch):
    seen: dict = {}

    async def probe(model_id: str) -> dict:
        seen.update((await client.get("/api/models/activity")).json())
        return {"ok": False, "reason": "stopped for the test", "model_id": model_id, "provider": "cpu"}

    async def installed():
        return [models_router.InstalledModel(id="small_birds", path="/m", labels_path="/l", is_active=False)]

    monkeypatch.setattr(models_router, "run_validation_probe", probe)
    monkeypatch.setattr(model_manager, "list_installed_models", installed)
    monkeypatch.setattr(models_router, "_require_classifier_artifact", lambda _model: None)

    await client.post("/api/models/small_birds/validate")

    assert seen == {"activity": {"small_birds": "validating"}}
    assert (await client.get("/api/models/activity")).json() == {"activity": {}}


@pytest.mark.asyncio
async def test_gardens_check_model_download_is_reported_under_its_own_name(client):
    with model_activity.working(GARDEN_CHECK_MODEL, "downloading"):
        assert (await client.get("/api/models/activity")).json() == {"activity": {GARDEN_CHECK_MODEL: "downloading"}}


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["verified", "refused"])
async def test_gardens_real_download_is_reported_while_it_runs_and_cleared_when_it_ends(
    client, tmp_path, monkeypatch, outcome
):
    """The real download path, held open: nothing here registers the activity but the download itself."""
    import asyncio
    import hashlib

    from fastapi import HTTPException

    from app.services import garden_identification as garden

    service = garden.GardenIdentificationService()
    service.models = tmp_path
    monkeypatch.setattr(garden, "MODEL_SIZES", {"4.0.3a": 3})
    monkeypatch.setattr(
        service.catalog, "load", lambda: {"model_sha256": {"4.0.3a": hashlib.sha256(b"new").hexdigest()}}
    )
    started, release = asyncio.Event(), asyncio.Event()

    async def held(_request: httpx.Request) -> httpx.Response:
        started.set()
        await release.wait()
        return httpx.Response(200, content=b"new" if outcome == "verified" else b"bad")

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        garden.httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(held), **kwargs)
    )
    assert (await client.get("/api/models/activity")).json() == {"activity": {}}

    download = asyncio.create_task(service.ensure_model("4.0.3a"))
    await asyncio.wait_for(started.wait(), timeout=5)

    # Mid-download: this is what keeps a Garden record's Manual override closed.
    assert (await client.get("/api/models/activity")).json() == {"activity": {GARDEN_CHECK_MODEL: "downloading"}}

    release.set()
    if outcome == "verified":
        await download
        assert service.model_path("4.0.3a").read_bytes() == b"new"
    else:
        with pytest.raises(HTTPException):
            await download
    # Over, whether it was verified or refused: nothing is left reporting a download.
    assert (await client.get("/api/models/activity")).json() == {"activity": {}}


@pytest.mark.asyncio
async def test_a_garden_model_that_is_already_here_reports_no_download(client, tmp_path, monkeypatch):
    import hashlib

    from app.services import garden_identification as garden

    service = garden.GardenIdentificationService()
    service.models = tmp_path
    service.model_path("4.0.3a").write_bytes(b"new")
    monkeypatch.setattr(
        service.catalog, "load", lambda: {"model_sha256": {"4.0.3a": hashlib.sha256(b"new").hexdigest()}}
    )
    seen: list[dict] = []
    monkeypatch.setattr(
        garden,
        "digest",
        lambda path: (seen.append(model_activity.phases({})), hashlib.sha256(path.read_bytes()).hexdigest())[1],
    )

    await service.ensure_model("4.0.3a")

    assert seen == [{}]
