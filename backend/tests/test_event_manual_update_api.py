from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
import uuid

import httpx
import pytest
import pytest_asyncio

from app.main import app
from app.database import get_db, init_db, close_db
from app.config import settings


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
    original_blocked_labels = list(settings.classification.blocked_labels)
    original_blocked_species = list(getattr(settings.classification, "blocked_species", []))
    yield
    settings.auth.enabled = original_auth_enabled
    settings.public_access.enabled = original_public_enabled
    settings.classification.blocked_labels = original_blocked_labels
    settings.classification.blocked_species = original_blocked_species


async def _seed_detection_and_taxonomy(event_id: str, taxa_id: int) -> None:
    now = datetime.now(timezone.utc).isoformat(sep=" ")
    async with get_db() as db:
        await db.execute(
            "INSERT OR REPLACE INTO taxonomy_cache (scientific_name, common_name, taxa_id) VALUES (?, ?, ?)",
            ("Cyanistes caeruleus", "Blue Tit", taxa_id),
        )
        await db.execute(
            "INSERT OR REPLACE INTO taxonomy_translations (taxa_id, language_code, common_name) VALUES (?, ?, ?)",
            (taxa_id, "es", "Herrerillo comun"),
        )
        await db.execute(
            """
            INSERT INTO detections (
                detection_time, detection_index, score, display_name, category_name,
                frigate_event, camera_name, is_hidden, manual_tagged,
                scientific_name, common_name, taxa_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?, ?)
            """,
            (
                now,
                1,
                0.91,
                "Blue Tit",
                "Blue Tit",
                event_id,
                "test-camera",
                "Cyanistes caeruleus",
                "Blue Tit",
                taxa_id,
            ),
        )
        await db.commit()


async def _cleanup_detection_and_taxonomy(event_id: str, taxa_id: int) -> None:
    async with get_db() as db:
        await db.execute("DELETE FROM classification_feedback WHERE frigate_event = ?", (event_id,))
        await db.execute("DELETE FROM detections WHERE frigate_event = ?", (event_id,))
        await db.execute("DELETE FROM taxonomy_translations WHERE taxa_id = ?", (taxa_id,))
        await db.execute("DELETE FROM taxonomy_cache WHERE taxa_id = ?", (taxa_id,))
        await db.commit()


@pytest.mark.asyncio
async def test_manual_update_treats_localized_alias_of_same_species_as_unchanged(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    event_id = f"manual-{uuid.uuid4().hex[:10]}"
    taxa_id = 910000 + int(uuid.uuid4().hex[:4], 16)
    await _seed_detection_and_taxonomy(event_id=event_id, taxa_id=taxa_id)

    try:
        with patch("app.routers.events.taxonomy_service.get_names", new=AsyncMock()) as mock_get_names, \
             patch("app.routers.events.audio_service.correlate_species", new=AsyncMock()) as mock_audio, \
             patch("app.routers.events.broadcaster.broadcast", new=AsyncMock()) as mock_broadcast:
            response = await client.patch(
                f"/api/events/{event_id}",
                json={"display_name": "Herrerillo com\u00fan"},
                headers={"Accept-Language": "es"},
            )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["status"] == "unchanged"

        mock_get_names.assert_not_awaited()
        mock_audio.assert_not_awaited()
        mock_broadcast.assert_not_awaited()

        async with get_db() as db:
            async with db.execute(
                "SELECT display_name, category_name, scientific_name, common_name, taxa_id, manual_tagged FROM detections WHERE frigate_event = ?",
                (event_id,),
            ) as cursor:
                row = await cursor.fetchone()

        assert row is not None
        assert row[0] == "Blue Tit"
        assert row[1] == "Blue Tit"
        assert row[2] == "Cyanistes caeruleus"
        assert row[3] == "Blue Tit"
        assert row[4] == taxa_id
        assert row[5] == 0
    finally:
        await _cleanup_detection_and_taxonomy(event_id=event_id, taxa_id=taxa_id)


@pytest.mark.asyncio
async def test_manual_update_writes_classification_feedback_row(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    event_id = f"manual-{uuid.uuid4().hex[:10]}"
    taxa_id = 920000 + int(uuid.uuid4().hex[:4], 16)
    await _seed_detection_and_taxonomy(event_id=event_id, taxa_id=taxa_id)

    try:
        with patch(
            "app.routers.events.taxonomy_service.get_names",
            new=AsyncMock(return_value={"scientific_name": "Parus major", "common_name": "Great Tit", "taxa_id": 145252}),
        ) as mock_get_names, patch(
            "app.routers.events.audio_service.correlate_species",
            new=AsyncMock(return_value=(False, None, None)),
        ) as mock_audio, patch(
            "app.routers.events.broadcaster.broadcast",
            new=AsyncMock(),
        ) as mock_broadcast:
            response = await client.patch(
                f"/api/events/{event_id}",
                json={"display_name": "Great Tit"},
                headers={"Accept-Language": "en"},
            )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["status"] == "updated"
        assert payload["event_id"] == event_id
        assert payload["old_species"] == "Blue Tit"
        assert payload["new_species"] == "Great Tit"

        mock_get_names.assert_awaited()
        mock_audio.assert_awaited()
        mock_broadcast.assert_awaited()

        async with get_db() as db:
            async with db.execute(
                """
                SELECT camera_name, model_id, predicted_label, corrected_label, predicted_score, source
                FROM classification_feedback
                WHERE frigate_event = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (event_id,),
            ) as cursor:
                feedback_row = await cursor.fetchone()

        assert feedback_row is not None
        assert feedback_row[0] == "test-camera"
        assert feedback_row[1]
        assert feedback_row[2] == "Blue Tit"
        assert feedback_row[3] == "Parus major"
        assert feedback_row[4] == pytest.approx(0.91, rel=1e-6)
        assert feedback_row[5] == "manual_tag"
    finally:
        await _cleanup_detection_and_taxonomy(event_id=event_id, taxa_id=taxa_id)


@pytest.mark.asyncio
async def test_manual_update_backfills_canonical_common_name_from_cache_when_taxonomy_is_partial(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    event_id = f"manual-{uuid.uuid4().hex[:10]}"
    taxa_id = 930000 + int(uuid.uuid4().hex[:4], 16)
    replacement_taxa_id = 145252
    await _seed_detection_and_taxonomy(event_id=event_id, taxa_id=taxa_id)

    try:
        async with get_db() as db:
            await db.execute(
                "INSERT OR REPLACE INTO taxonomy_cache (scientific_name, common_name, taxa_id) VALUES (?, ?, ?)",
                ("Parus major", "Great Tit", replacement_taxa_id),
            )
            await db.commit()

        with patch(
            "app.routers.events.DetectionRepository.resolve_species_aliases",
            new=AsyncMock(return_value={}),
        ), patch(
            "app.routers.events.taxonomy_service.get_names",
            new=AsyncMock(return_value={"scientific_name": "Parus major", "common_name": None, "taxa_id": None}),
        ) as mock_get_names, patch(
            "app.routers.events.audio_service.correlate_species",
            new=AsyncMock(return_value=(False, None, None)),
        ), patch(
            "app.routers.events.broadcaster.broadcast",
            new=AsyncMock(),
        ):
            response = await client.patch(
                f"/api/events/{event_id}",
                json={"display_name": "Parus major"},
                headers={"Accept-Language": "en"},
            )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["status"] == "updated"
        assert payload["new_species"] == "Great Tit"
        mock_get_names.assert_awaited_once_with("Parus major", force_refresh=True)

        async with get_db() as db:
            async with db.execute(
                "SELECT display_name, category_name, scientific_name, common_name, taxa_id, manual_tagged FROM detections WHERE frigate_event = ?",
                (event_id,),
            ) as cursor:
                row = await cursor.fetchone()

        assert row is not None
        assert row[0] == "Great Tit"
        assert row[1] == "Parus major"
        assert row[2] == "Parus major"
        assert row[3] == "Great Tit"
        assert row[4] == replacement_taxa_id
        assert row[5] == 1
    finally:
        async with get_db() as db:
            await db.execute("DELETE FROM taxonomy_cache WHERE taxa_id = ?", (replacement_taxa_id,))
            await db.commit()
        await _cleanup_detection_and_taxonomy(event_id=event_id, taxa_id=taxa_id)


@pytest.mark.asyncio
async def test_manual_update_rejects_parenthetical_variant_of_blocked_species(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    settings.classification.blocked_labels = ["Cassin's Finch"]

    event_id = f"manual-{uuid.uuid4().hex[:10]}"
    taxa_id = 935000 + int(uuid.uuid4().hex[:4], 16)
    await _seed_detection_and_taxonomy(event_id=event_id, taxa_id=taxa_id)

    try:
        with patch(
            "app.routers.events.DetectionRepository.resolve_species_aliases",
            new=AsyncMock(return_value={}),
        ), patch(
            "app.routers.events.taxonomy_service.get_names",
            new=AsyncMock(return_value={}),
        ), patch(
            "app.routers.events.audio_service.correlate_species",
            new=AsyncMock(return_value=(False, None, None)),
        ) as mock_audio, patch(
            "app.routers.events.broadcaster.broadcast",
            new=AsyncMock(),
        ) as mock_broadcast:
            response = await client.patch(
                f"/api/events/{event_id}",
                json={"display_name": "Cassin's Finch (Adult Male)"},
                headers={"Accept-Language": "en"},
            )

        assert response.status_code == 422, response.text
        assert response.json()["detail"] == "This species is on your blocked labels list. Remove it from the blocklist first."
        mock_audio.assert_not_awaited()
        mock_broadcast.assert_not_awaited()
    finally:
        await _cleanup_detection_and_taxonomy(event_id=event_id, taxa_id=taxa_id)


@pytest.mark.asyncio
async def test_manual_update_rejects_structured_blocked_species(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    settings.classification.blocked_species = [
        {
            "scientific_name": "Haemorhous cassinii",
            "common_name": "Cassin's Finch",
            "taxa_id": 4567,
        }
    ]

    event_id = f"manual-{uuid.uuid4().hex[:10]}"
    taxa_id = 940000 + int(uuid.uuid4().hex[:4], 16)
    await _seed_detection_and_taxonomy(event_id=event_id, taxa_id=taxa_id)

    try:
        with patch(
            "app.routers.events.DetectionRepository.resolve_species_aliases",
            new=AsyncMock(return_value={}),
        ), patch(
            "app.routers.events.taxonomy_service.get_names",
            new=AsyncMock(return_value={"scientific_name": "Haemorhous cassinii", "common_name": "Cassin's Finch", "taxa_id": 4567}),
        ), patch(
            "app.routers.events.audio_service.correlate_species",
            new=AsyncMock(return_value=(False, None, None)),
        ) as mock_audio, patch(
            "app.routers.events.broadcaster.broadcast",
            new=AsyncMock(),
        ) as mock_broadcast:
            response = await client.patch(
                f"/api/events/{event_id}",
                json={"display_name": "Cassin's Finch"},
                headers={"Accept-Language": "en"},
            )

        assert response.status_code == 422, response.text
        assert response.json()["detail"] == "This species is on your blocked labels list. Remove it from the blocklist first."
        mock_audio.assert_not_awaited()
        mock_broadcast.assert_not_awaited()
    finally:
        await _cleanup_detection_and_taxonomy(event_id=event_id, taxa_id=taxa_id)


@pytest.mark.asyncio
async def test_bulk_manual_update_applies_same_species_to_multiple_events(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    base_taxa_id = 940000 + int(uuid.uuid4().hex[:4], 16)
    replacement_taxa_id = 145252
    event_ids = [f"manual-{uuid.uuid4().hex[:10]}", f"manual-{uuid.uuid4().hex[:10]}"]
    for index, event_id in enumerate(event_ids):
        await _seed_detection_and_taxonomy(event_id=event_id, taxa_id=base_taxa_id + index)

    try:
        async with get_db() as db:
            await db.execute(
                "INSERT OR REPLACE INTO taxonomy_cache (scientific_name, common_name, taxa_id) VALUES (?, ?, ?)",
                ("Parus major", "Great Tit", replacement_taxa_id),
            )
            await db.commit()

        with patch(
            "app.routers.events.taxonomy_service.get_names",
            new=AsyncMock(return_value={"scientific_name": "Parus major", "common_name": "Great Tit", "taxa_id": replacement_taxa_id}),
        ) as mock_get_names, patch(
            "app.routers.events.audio_service.correlate_species",
            new=AsyncMock(return_value=(False, None, None)),
        ) as mock_audio, patch(
            "app.routers.events.broadcaster.broadcast",
            new=AsyncMock(),
        ) as mock_broadcast:
            response = await client.patch(
                "/api/events/bulk/manual-tag",
                json={"event_ids": event_ids, "display_name": "Great Tit"},
                headers={"Accept-Language": "en"},
            )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["status"] == "updated"
        assert payload["requested_count"] == 2
        assert payload["updated_count"] == 2
        assert payload["updated_event_ids"] == event_ids
        assert payload["new_species"] == "Great Tit"

        assert mock_get_names.await_count == 2
        assert mock_audio.await_count == 2
        assert mock_broadcast.await_count == 2

        async with get_db() as db:
            async with db.execute(
                """
                SELECT frigate_event, display_name, category_name, scientific_name, common_name, taxa_id, manual_tagged
                FROM detections
                WHERE frigate_event IN (?, ?)
                ORDER BY frigate_event
                """,
                (event_ids[0], event_ids[1]),
            ) as cursor:
                rows = await cursor.fetchall()

        assert len(rows) == 2
        for row in rows:
            assert row[1] == "Great Tit"
            assert row[2] == "Parus major"
            assert row[3] == "Parus major"
            assert row[4] == "Great Tit"
            assert row[5] == replacement_taxa_id
            assert row[6] == 1
    finally:
        async with get_db() as db:
            await db.execute("DELETE FROM taxonomy_cache WHERE taxa_id = ?", (replacement_taxa_id,))
            await db.commit()
        for index, event_id in enumerate(event_ids):
            await _cleanup_detection_and_taxonomy(event_id=event_id, taxa_id=base_taxa_id + index)


@pytest.mark.asyncio
async def test_bulk_manual_update_reports_partial_failures_without_aborting_batch(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    base_taxa_id = 950000 + int(uuid.uuid4().hex[:4], 16)
    event_ids = [f"manual-{uuid.uuid4().hex[:10]}", f"manual-{uuid.uuid4().hex[:10]}"]
    for index, event_id in enumerate(event_ids):
        await _seed_detection_and_taxonomy(event_id=event_id, taxa_id=base_taxa_id + index)

    try:
        with patch(
            "app.routers.events._apply_manual_tag_update",
            new=AsyncMock(side_effect=[
                {"status": "updated", "event_id": event_ids[0], "new_species": "Great Tit"},
                RuntimeError("boom"),
            ]),
        ):
            response = await client.patch(
                "/api/events/bulk/manual-tag",
                json={"event_ids": event_ids, "display_name": "Great Tit"},
                headers={"Accept-Language": "en"},
            )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["status"] == "updated"
        assert payload["requested_count"] == 2
        assert payload["updated_count"] == 1
        assert payload["failed_count"] == 1
        assert payload["updated_event_ids"] == [event_ids[0]]
        assert payload["failed_event_ids"] == [event_ids[1]]
        assert payload["new_species"] == "Great Tit"
    finally:
        for index, event_id in enumerate(event_ids):
            await _cleanup_detection_and_taxonomy(event_id=event_id, taxa_id=base_taxa_id + index)
