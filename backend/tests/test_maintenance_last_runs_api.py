"""Each Maintenance job reports when it last ran and what it found, across restarts."""

import httpx
import pytest
import pytest_asyncio

from app.auth import AuthContext, AuthLevel, require_owner
from app.database import get_db
from app.main import app
from app.repositories.maintenance_job_repository import MaintenanceJobRepository
from app.services.canonical_identity_repair_service import canonical_identity_repair_service
from app.services.maintenance_run_history import MAINTENANCE_RUN_KINDS, record_maintenance_run
from app.services.timezone_repair_service import timezone_repair_service


@pytest_asyncio.fixture
async def client(history_pool):
    await _forget_recorded_runs()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    await _forget_recorded_runs()


async def _forget_recorded_runs() -> None:
    async with get_db() as db:
        placeholders = ",".join("?" for _ in MAINTENANCE_RUN_KINDS)
        await db.execute(f"DELETE FROM maintenance_job_history WHERE kind IN ({placeholders})", MAINTENANCE_RUN_KINDS)
        await db.commit()


@pytest.fixture(autouse=True)
def owner_auth_override():
    app.dependency_overrides[require_owner] = lambda: AuthContext(auth_level=AuthLevel.OWNER, username="owner")
    try:
        yield
    finally:
        app.dependency_overrides.pop(require_owner, None)


def _run(payload: dict, kind: str) -> dict | None:
    return next((run for run in payload["runs"] if run["kind"] == kind), None)


@pytest.mark.asyncio
async def test_a_job_that_never_ran_has_no_last_run(client: httpx.AsyncClient):
    response = await client.get("/api/maintenance/last-runs")

    assert response.status_code == 200, response.text
    for kind in MAINTENANCE_RUN_KINDS:
        assert _run(response.json(), kind) is None


@pytest.mark.asyncio
async def test_timezone_scan_records_what_it_scanned_and_found(client: httpx.AsyncClient, monkeypatch):
    async def _fake_preview():
        return {
            "summary": {
                "scanned_count": 40,
                "repair_candidate_count": 3,
                "ok_count": 37,
                "missing_frigate_event_count": 0,
                "unsupported_delta_count": 0,
            },
            "candidates": [],
        }

    monkeypatch.setattr(timezone_repair_service, "preview", _fake_preview)
    assert (await client.get("/api/maintenance/timezone-repair/preview")).status_code == 200

    run = _run((await client.get("/api/maintenance/last-runs")).json(), "timezone_scan")
    assert run is not None
    assert run["status"] == "completed"
    assert run["checked"] == 40
    assert run["changed"] == 3
    assert run["finished_at"]


@pytest.mark.asyncio
async def test_timezone_repair_records_how_many_rows_it_changed(client: httpx.AsyncClient, monkeypatch):
    async def _fake_apply(*, confirm: bool):
        return {
            "status": "ok",
            "repaired_count": 2,
            "skipped_count": 1,
            "preview": {
                "summary": {
                    "scanned_count": 3,
                    "repair_candidate_count": 2,
                    "ok_count": 1,
                    "missing_frigate_event_count": 0,
                    "unsupported_delta_count": 0,
                },
                "candidates": [],
            },
        }

    monkeypatch.setattr(timezone_repair_service, "apply", _fake_apply)
    assert (await client.post("/api/maintenance/timezone-repair/apply", json={"confirm": True})).status_code == 200

    run = _run((await client.get("/api/maintenance/last-runs")).json(), "timezone_repair")
    assert run is not None
    assert (run["status"], run["checked"], run["changed"]) == ("completed", 3, 2)


@pytest.mark.asyncio
async def test_taxonomy_repair_records_its_outcome_when_the_background_run_ends(client: httpx.AsyncClient, monkeypatch):
    async def _fake_run(**_kwargs):
        return {"processed": 120, "updated": 7, "rollups_rebuilt": True}

    monkeypatch.setattr(canonical_identity_repair_service, "run", _fake_run)
    assert (await client.post("/api/maintenance/taxonomy/sync")).status_code == 200

    run = _run((await client.get("/api/maintenance/last-runs")).json(), "taxonomy")
    assert run is not None
    assert (run["status"], run["checked"], run["changed"]) == ("completed", 120, 7)


@pytest.mark.asyncio
async def test_a_failed_taxonomy_repair_is_recorded_as_failed(client: httpx.AsyncClient, monkeypatch):
    async def _failing_run(**_kwargs):
        raise RuntimeError("lookup service unreachable")

    monkeypatch.setattr(canonical_identity_repair_service, "run", _failing_run)
    with pytest.raises(RuntimeError):
        await client.post("/api/maintenance/taxonomy/sync")

    run = _run((await client.get("/api/maintenance/last-runs")).json(), "taxonomy")
    assert run is not None
    assert run["status"] == "failed"


@pytest.mark.asyncio
async def test_the_newest_run_of_a_kind_wins(client: httpx.AsyncClient):
    await record_maintenance_run("analyze_unknowns", status="completed", checked=10, changed=4)
    await record_maintenance_run("analyze_unknowns", status="completed", checked=12, changed=0)

    run = _run((await client.get("/api/maintenance/last-runs")).json(), "analyze_unknowns")
    assert run is not None
    assert (run["checked"], run["changed"]) == (12, 0)


@pytest.mark.asyncio
async def test_a_recorded_maintenance_run_is_never_read_back_as_a_backfill_job(client: httpx.AsyncClient):
    await record_maintenance_run("taxonomy", status="completed", checked=1, changed=1)

    async with get_db() as db:
        repo = MaintenanceJobRepository(db)
        assert all(
            job["kind"] not in MAINTENANCE_RUN_KINDS for job in await repo.recent(kinds=("detections", "weather"))
        )
        latest = await repo.latest(kinds=("detections", "weather"))
    assert latest is None or latest["kind"] in ("detections", "weather")
