"""A decision taken on a visit as it was shown must not overwrite a newer one.

The review queue works from a snapshot. If another tab corrects the visit first, a late
"Confirm" from the snapshot would put the old species back. The request names the
identification it was shown; the write happens only while the stored identification
still matches, in one conditional UPDATE, and otherwise the server answers 409 with what
the visit says now.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
import uuid

import httpx
import pytest
import pytest_asyncio

from app.config import settings
from app.database import get_db
from app.main import app
from app.repositories.detection_repository import DetectionRepository

pytestmark = pytest.mark.usefixtures("history_pool")


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture(autouse=True)
def open_owner_access():
    original_auth_enabled = settings.auth.enabled
    original_public_enabled = settings.public_access.enabled
    settings.auth.enabled = False
    settings.public_access.enabled = False
    yield
    settings.auth.enabled = original_auth_enabled
    settings.public_access.enabled = original_public_enabled


async def _seed(event_id: str, name: str = "Eurasian Bullfinch", scientific: str = "Pyrrhula pyrrhula") -> None:
    now = datetime.now(timezone.utc).isoformat(sep=" ")
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO detections (
                detection_time, detection_index, score, display_name, category_name,
                frigate_event, camera_name, is_hidden, manual_tagged, scientific_name, common_name
            ) VALUES (?, 1, 0.57, ?, ?, ?, 'feeder', 0, 0, ?, ?)
            """,
            (now, name, scientific, event_id, scientific, name),
        )
        await db.commit()


async def _correct_elsewhere(event_id: str, name: str, scientific: str) -> None:
    """Another tab's correction, written as the manual tag writes it."""
    async with get_db() as db:
        await db.execute(
            """UPDATE detections SET display_name = ?, category_name = ?, scientific_name = ?,
               common_name = ?, manual_tagged = 1 WHERE frigate_event = ?""",
            (name, scientific, scientific, name, event_id),
        )
        await db.commit()


async def _stored(event_id: str) -> tuple:
    async with get_db() as db:
        async with db.execute(
            "SELECT display_name, category_name, manual_tagged FROM detections WHERE frigate_event = ?",
            (event_id,),
        ) as cursor:
            return await cursor.fetchone()


async def _cleanup(event_id: str) -> None:
    async with get_db() as db:
        await db.execute("DELETE FROM classification_feedback WHERE frigate_event = ?", (event_id,))
        await db.execute("DELETE FROM detections WHERE frigate_event = ?", (event_id,))
        await db.commit()


def _quiet_services():
    return (
        patch("app.routers.events.taxonomy_service.get_names", new=AsyncMock(return_value={})),
        patch("app.routers.events.audio_service.correlate_species", new=AsyncMock(return_value=(False, None, None))),
        patch("app.routers.events.broadcaster.broadcast", new=AsyncMock()),
    )


@pytest.mark.asyncio
async def test_confirm_applies_while_the_shown_identification_still_stands(client: httpx.AsyncClient):
    event_id = f"precondition-{uuid.uuid4().hex[:10]}"
    await _seed(event_id)
    try:
        names, audio, broadcast = _quiet_services()
        with names, audio, broadcast:
            response = await client.patch(
                f"/api/events/{event_id}",
                json={"display_name": "Eurasian Bullfinch", "expected_category_name": "Pyrrhula pyrrhula"},
            )
        assert response.status_code == 200, response.text
        assert response.json()["manual_tagged"] is True
        assert await _stored(event_id) == ("Eurasian Bullfinch", "Pyrrhula pyrrhula", 1)
    finally:
        await _cleanup(event_id)


@pytest.mark.asyncio
async def test_a_stale_confirm_is_refused_and_says_what_the_visit_reads_now(client: httpx.AsyncClient):
    event_id = f"precondition-{uuid.uuid4().hex[:10]}"
    await _seed(event_id)
    try:
        await _correct_elsewhere(event_id, "Common Chaffinch", "Fringilla coelebs")
        names, audio, broadcast = _quiet_services()
        with names, audio, broadcast as mock_broadcast:
            response = await client.patch(
                f"/api/events/{event_id}",
                json={"display_name": "Eurasian Bullfinch", "expected_category_name": "Pyrrhula pyrrhula"},
            )
        assert response.status_code == 409, response.text
        detail = response.json()["detail"]
        assert detail["code"] == "identification_changed"
        assert "changed elsewhere" in detail["message"]
        assert "Common Chaffinch" in detail["message"]
        assert detail["current"]["display_name"] == "Common Chaffinch"
        assert detail["current"]["category_name"] == "Fringilla coelebs"
        assert detail["current"]["manual_tagged"] is True
        mock_broadcast.assert_not_awaited()
        # The newer correction stands.
        assert await _stored(event_id) == ("Common Chaffinch", "Fringilla coelebs", 1)
    finally:
        await _cleanup(event_id)


@pytest.mark.asyncio
async def test_a_stale_pick_of_another_species_is_refused_too(client: httpx.AsyncClient):
    event_id = f"precondition-{uuid.uuid4().hex[:10]}"
    await _seed(event_id)
    try:
        await _correct_elsewhere(event_id, "Common Chaffinch", "Fringilla coelebs")
        names, audio, broadcast = _quiet_services()
        with names, audio, broadcast:
            response = await client.patch(
                f"/api/events/{event_id}",
                json={"display_name": "House Sparrow", "expected_category_name": "Pyrrhula pyrrhula"},
            )
        assert response.status_code == 409, response.text
        assert await _stored(event_id) == ("Common Chaffinch", "Fringilla coelebs", 1)
    finally:
        await _cleanup(event_id)


@pytest.mark.asyncio
async def test_a_change_between_the_read_and_the_write_is_still_refused(client: httpx.AsyncClient):
    """The window the early check cannot close: the conditional UPDATE closes it."""
    event_id = f"precondition-{uuid.uuid4().hex[:10]}"
    await _seed(event_id)
    try:

        async def correct_while_correlating(**_kwargs):
            await _correct_elsewhere(event_id, "Common Chaffinch", "Fringilla coelebs")
            return False, None, None

        with (
            patch("app.routers.events.taxonomy_service.get_names", new=AsyncMock(return_value={})),
            patch(
                "app.routers.events.audio_service.correlate_species",
                new=AsyncMock(side_effect=correct_while_correlating),
            ),
            patch("app.routers.events.broadcaster.broadcast", new=AsyncMock()) as mock_broadcast,
        ):
            response = await client.patch(
                f"/api/events/{event_id}",
                json={"display_name": "House Sparrow", "expected_category_name": "Pyrrhula pyrrhula"},
            )
        assert response.status_code == 409, response.text
        assert response.json()["detail"]["current"]["display_name"] == "Common Chaffinch"
        mock_broadcast.assert_not_awaited()
        assert await _stored(event_id) == ("Common Chaffinch", "Fringilla coelebs", 1)
        async with get_db() as db:
            async with db.execute(
                "SELECT COUNT(*) FROM classification_feedback WHERE frigate_event = ?", (event_id,)
            ) as cursor:
                assert (await cursor.fetchone())[0] == 0
    finally:
        await _cleanup(event_id)


@pytest.mark.asyncio
async def test_identify_without_a_shown_identification_behaves_as_before(client: httpx.AsyncClient):
    """The record and bulk retag send no precondition and keep last-write-wins."""
    event_id = f"precondition-{uuid.uuid4().hex[:10]}"
    await _seed(event_id)
    try:
        await _correct_elsewhere(event_id, "Common Chaffinch", "Fringilla coelebs")
        names, audio, broadcast = _quiet_services()
        with names, audio, broadcast:
            response = await client.patch(f"/api/events/{event_id}", json={"display_name": "House Sparrow"})
        assert response.status_code == 200, response.text
        assert (await _stored(event_id))[0] == "House Sparrow"
    finally:
        await _cleanup(event_id)


@pytest.mark.asyncio
async def test_repository_writes_only_while_the_expected_identification_stands():
    event_id = f"precondition-{uuid.uuid4().hex[:10]}"
    await _seed(event_id)
    try:
        async with get_db() as db:
            repo = DetectionRepository(db)
            assert (
                await repo.confirm_manual_species_tag(
                    frigate_event=event_id, expected_category_name="Fringilla coelebs"
                )
                is False
            )
            applied = await repo.apply_manual_species_tag(
                frigate_event=event_id,
                display_name="House Sparrow",
                category_name="Passer domesticus",
                scientific_name="Passer domesticus",
                common_name="House Sparrow",
                taxa_id=None,
                audio_confirmed=False,
                audio_species=None,
                audio_score=None,
                expected_category_name="Fringilla coelebs",
            )
            assert applied is False
            await db.commit()
        assert await _stored(event_id) == ("Eurasian Bullfinch", "Pyrrhula pyrrhula", 0)

        async with get_db() as db:
            repo = DetectionRepository(db)
            # Matching ignores case and surrounding space, as species names do elsewhere.
            assert (
                await repo.confirm_manual_species_tag(
                    frigate_event=event_id, expected_category_name=" pyrrhula PYRRHULA "
                )
                is True
            )
            await db.commit()
        assert await _stored(event_id) == ("Eurasian Bullfinch", "Pyrrhula pyrrhula", 1)
    finally:
        await _cleanup(event_id)
