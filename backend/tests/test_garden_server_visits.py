"""Garden groups are formed before pagination and retain per-capture review state."""

from datetime import datetime, timedelta, timezone

import httpx
import pytest
import pytest_asyncio

from app.config import settings
from app.database import close_db, get_db, init_db
from app.main import app
from app.repositories.garden_repository import GardenRepository


@pytest_asyncio.fixture
async def history(monkeypatch):
    monkeypatch.setattr(settings.auth, "enabled", False)
    monkeypatch.setattr(settings.public_access, "enabled", False)
    monkeypatch.setattr(settings.system, "beta_garden_animals", True)
    await init_db()
    async with get_db() as db:
        await db.execute("DELETE FROM garden_captures")
        await db.commit()
        yield GardenRepository(db)
    await close_db()


async def add(repo, name, seconds, *, camera="patio", status="confirmed", photo=True):
    at = (datetime(2026, 10, 24, tzinfo=timezone.utc) + timedelta(seconds=seconds)).replace(tzinfo=None).isoformat()
    await repo.capture(name, camera, "cat", at, photo)
    await repo.db.execute("UPDATE garden_captures SET status=? WHERE frigate_event=?", (status, name))
    await repo.db.commit()


@pytest.mark.asyncio
async def test_visit_pages_never_split_a_long_stay_and_capture_pages_reach_every_photo(history):
    for i in range(215):
        await add(history, f"stay-{i}", i)
    await add(history, "later", 400)
    await add(history, "another-camera", 401, camera="lawn")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        pages = [(await client.get(f"/api/garden/visits?limit=1&offset={i}&order=oldest")).json() for i in range(3)]
        assert all(page.get("total") == 3 for page in pages), pages
        assert [page["visits"][0]["capture_count"] for page in pages] == [215, 1, 1]
        visit = pages[0]["visits"][0]
        seen = []
        for offset in [0, 100, 200]:
            response = await client.get(f"/api/garden/visits/{visit['id']}/captures?limit=100&offset={offset}")
            assert response.status_code == 200, response.text
            assert response.json()["total"] == 215
            seen.extend(item["id"] for item in response.json()["items"])
        assert len(seen) == len(set(seen)) == 215
    assert (await history.count("confirmed")) == 217


@pytest.mark.asyncio
async def test_scope_excludes_blocked_and_photoless_pending_and_keeps_review_states_apart(history):
    for name, status, photo in [
        ("owned", "confirmed", False),
        ("pending", "pending", True),
        ("no-photo", "pending", False),
        ("dismissed", "dismissed", True),
        ("person", "pending", True),
    ]:
        await add(history, name, 0, status=status, photo=photo)
    await history.block("person", create=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/garden/visits")
        assert response.status_code == 200, response.text
        assert response.json()["total"] == 2
        assert {v["representative"]["status"] for v in response.json()["visits"]} == {"pending", "confirmed"}
        assert (await client.get("/api/garden/visits?status=dismissed")).json()["total"] == 1
        assert (await client.get("/api/garden/visits?start=2026-10-25T00:00:00Z")).json()["total"] == 0


@pytest.mark.asyncio
async def test_canonical_identity_ignores_display_name_but_never_joins_different_species(history):
    import json
    from app.models.garden import GardenIdentification

    for index, (name, species) in enumerate([("Cat", 101), ("Domestic cat", 101), ("Fox", 102)]):
        await add(history, f"named-{index}", index)
        result = GardenIdentification(
            outcome="suggestion",
            reason="garden",
            review="accepted",
            automatic=True,
            species_id=species,
            name=name,
            country="GBR",
            variant="4.0.3a",
            provider="cpu",
            devices=["CPU"],
            model_sha256="a" * 64,
            package_sha256="b" * 64,
            image_sha256="c" * 64,
            output_index=0,
            input_kind="tracked_crop",
            frame_size=(640, 480),
            identified_at="2026-10-24T00:00:00Z",
        )
        await history.db.execute(
            "INSERT INTO garden_identifications(capture_id,result_json) SELECT id,? FROM garden_captures WHERE frigate_event=?",
            (json.dumps(result.model_dump()), f"named-{index}"),
        )
    await history.db.commit()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/garden/visits")
        assert sorted(v["capture_count"] for v in response.json()["visits"]) == [1, 2]


@pytest.mark.asyncio
async def test_mixed_page_bounds_select_whole_visits_by_latest_capture_without_duplicates(history):
    for seconds in [0, 50, 100]:
        await add(history, str(seconds), seconds)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        first = (await client.get("/api/garden/visits?page_start=2026-10-24T00:01:00Z")).json()
        second = (await client.get("/api/garden/visits?page_end=2026-10-24T00:01:00Z")).json()
        assert first["visits"][0]["capture_count"] == 3
        assert second["total"] == 0
        anchor = first["visits"][0]["end_time"]
        assert (await client.get(f"/api/garden/visits?page_start={anchor}")).json()["total"] == 1
        assert (await client.get(f"/api/garden/visits?page_end={anchor}")).json()["total"] == 0


@pytest.mark.asyncio
async def test_review_and_revocation_recompute_membership_without_rewriting_other_captures(history):
    await add(history, "one", 0)
    await add(history, "two", 30)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        visit = (await client.get("/api/garden/visits")).json()["visits"][0]
        page = (await client.get(f"/api/garden/visits/{visit['id']}/captures")).json()
        await history.review(page["items"][0]["id"], "dismissed")
        fresh = (await client.get(f"/api/garden/visits/{visit['id']}/captures")).json()
        assert fresh["total"] == 1 and fresh["items"][0]["status"] == "confirmed"
        await history.block("one", create=False)
        assert (await client.get(f"/api/garden/visits/{visit['id']}/captures")).status_code == 404
    assert await history.count("dismissed") == 1


@pytest.mark.asyncio
async def test_motion_stacks_compare_fixed_boxes_and_never_swallow_other_positions(history):
    import hashlib
    from app.models.garden_motion import MotionSource
    from app.utils.api_datetime import utc_naive_now

    now = utc_naive_now().replace(tzinfo=timezone.utc).timestamp()
    ids = []
    for i, box in enumerate([(0.1, 0.1, 0.1, 0.1), (0.6, 0.6, 0.2, 0.2), (0.1, 0.1, 0.1, 0.1)]):
        source = MotionSource(
            camera="patio",
            clip_start=now - i * 20 - 10,
            clip_end=now - i * 20,
            frame_index=1,
            frame_offset=1,
            clip_sha256=str(i) * 64,
            image_sha256=hashlib.sha256(b"photo").hexdigest(),
            detector_sha256="b" * 64,
            detector_score=0.9,
            box_xywh=box,
        )
        ids.append(await history.capture_motion(source, b"photo"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        page = (await client.get("/api/garden/visits?limit=1")).json()
        assert page["total"] == 2 and page["visits"][0]["capture_count"] == 2
        assert page["visits"][0]["kind"] == "position"
        members = (await client.get(f"/api/garden/visits/{page['visits'][0]['id']}/captures")).json()
        assert {item["id"] for item in members["items"]} == {ids[0], ids[2]}


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/api/garden/visits", "/api/garden/visits/unknown/captures"])
async def test_visits_need_a_login_or_public_access_and_are_beta_gated(history, monkeypatch, path):
    monkeypatch.setattr(settings.system, "beta_garden_animals", False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get(path)).status_code == 404
    monkeypatch.setattr(settings.system, "beta_garden_animals", True)
    monkeypatch.setattr(settings.auth, "enabled", True)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get(path)).status_code == 401


@pytest.mark.parametrize(
    "box,detector,expected",
    [
        ((0.1, 0.1, 0.1, 0.1), "b", True),
        ((0.1, 0.1, 0.1, 0.15), "b", True),
        ((0.6, 0.6, 0.2, 0.2), "b", False),
        ((0.1, 0.1, 0.1, 0.1), "c", False),
    ],
)
def test_position_comparison_requires_same_camera_detector_and_bounded_extent(box, detector, expected):
    from app.models.garden_motion import MotionSource
    from app.services.garden_visit_grouping import same_position

    first = MotionSource(
        camera="patio",
        clip_start=1,
        clip_end=9,
        frame_index=1,
        frame_offset=1,
        clip_sha256="a" * 64,
        image_sha256="a" * 64,
        detector_sha256="b" * 64,
        detector_score=0.9,
        box_xywh=(0.1, 0.1, 0.1, 0.1),
    )
    other = first.model_copy(update={"box_xywh": box, "detector_sha256": detector * 64})
    assert same_position(first, other) is expected
    assert not same_position(first, other.model_copy(update={"camera": "lawn"}))
