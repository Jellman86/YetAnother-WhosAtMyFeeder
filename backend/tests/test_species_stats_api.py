from datetime import datetime, timezone
from urllib.parse import quote
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
    yield
    settings.auth.enabled = original_auth_enabled
    settings.public_access.enabled = original_public_enabled


async def _seed_taxon_and_detections(
    taxa_id: int,
    event_prefix: str,
    scientific_name: str,
    common_name: str,
    localized_common_name: str,
) -> None:
    now = datetime.now(timezone.utc).isoformat(sep=" ")
    async with get_db() as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO taxonomy_cache (scientific_name, common_name, taxa_id)
            VALUES (?, ?, ?)
            """,
            (scientific_name, common_name, taxa_id),
        )
        await db.execute(
            """
            INSERT OR REPLACE INTO taxonomy_translations (taxa_id, language_code, common_name)
            VALUES (?, ?, ?)
            """,
            (taxa_id, "es", localized_common_name),
        )
        for idx, display_name in enumerate([common_name, scientific_name], start=1):
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
                    idx,
                    0.9,
                    display_name,
                    display_name,
                    f"{event_prefix}_{idx}",
                    "test-camera",
                    scientific_name,
                    common_name,
                    taxa_id,
                ),
            )
        await db.commit()


async def _cleanup_taxon_and_detections(taxa_id: int, event_prefix: str) -> None:
    async with get_db() as db:
        await db.execute("DELETE FROM detections WHERE frigate_event LIKE ?", (f"{event_prefix}_%",))
        await db.execute("DELETE FROM taxonomy_translations WHERE taxa_id = ?", (taxa_id,))
        await db.execute("DELETE FROM taxonomy_cache WHERE taxa_id = ?", (taxa_id,))
        await db.commit()


async def _insert_hidden_unknown_detection(event_id: str) -> None:
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO detections (
                detection_time, detection_index, score, display_name, category_name,
                frigate_event, camera_name, is_hidden, manual_tagged,
                scientific_name, common_name, taxa_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?, ?)
            """,
            (
                datetime.now(timezone.utc).isoformat(sep=" "),
                1,
                0.81,
                "Great tit and allies",
                "Great tit and allies",
                event_id,
                "test-camera",
                "Great tit and allies",
                "Great tit and allies",
                None,
            ),
        )
        await db.commit()


async def _delete_detection(event_id: str) -> None:
    async with get_db() as db:
        await db.execute("DELETE FROM detections WHERE frigate_event = ?", (event_id,))
        await db.commit()


@pytest.mark.asyncio
async def test_species_stats_accepts_localized_common_name_and_aggregates_aliases(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    suffix = uuid.uuid4().hex[:8]
    taxa_id = 900000 + int(suffix[:4], 16)
    event_prefix = f"speciesstats-{suffix}"
    scientific_name = f"Aves{suffix} testus"
    common_name = f"Test Bird {suffix}"
    localized_common_name = f"Pajaro Prueba {suffix}"
    await _seed_taxon_and_detections(
        taxa_id=taxa_id,
        event_prefix=event_prefix,
        scientific_name=scientific_name,
        common_name=common_name,
        localized_common_name=localized_common_name,
    )

    try:
        response = await client.get(
            f"/api/species/{quote(localized_common_name, safe='')}/stats",
            headers={"Accept-Language": "es"},
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["species_name"] == localized_common_name
        assert data["taxa_id"] == taxa_id
        assert data["scientific_name"] == scientific_name
        assert data["common_name"] == localized_common_name
        assert data["total_sightings"] == 2
        assert data["first_seen"].endswith("Z")
        assert data["last_seen"].endswith("Z")
        assert len(data["recent_sightings"]) == 2
        assert all(item["detection_time"].endswith("Z") for item in data["recent_sightings"])
    finally:
        await _cleanup_taxon_and_detections(taxa_id=taxa_id, event_prefix=event_prefix)


@pytest.mark.asyncio
async def test_species_stats_handles_mixed_naive_and_aware_detection_times(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    suffix = uuid.uuid4().hex[:8]
    taxa_id = 900000 + int(suffix[:4], 16)
    event_prefix = f"speciesstats-mixed-{suffix}"
    scientific_name = f"Aves{suffix} mixtus"
    common_name = f"Mixed Bird {suffix}"
    localized_common_name = f"Pajaro Mixto {suffix}"
    aware_now = datetime.now(timezone.utc).replace(microsecond=0)
    naive_now = aware_now.replace(tzinfo=None)

    async with get_db() as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO taxonomy_cache (scientific_name, common_name, taxa_id)
            VALUES (?, ?, ?)
            """,
            (scientific_name, common_name, taxa_id),
        )
        await db.execute(
            """
            INSERT OR REPLACE INTO taxonomy_translations (taxa_id, language_code, common_name)
            VALUES (?, ?, ?)
            """,
            (taxa_id, "es", localized_common_name),
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
                aware_now.isoformat(sep=" "),
                1,
                0.9,
                common_name,
                common_name,
                f"{event_prefix}_1",
                "test-camera",
                scientific_name,
                common_name,
                taxa_id,
            ),
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
                naive_now.isoformat(sep=" "),
                2,
                0.88,
                scientific_name,
                scientific_name,
                f"{event_prefix}_2",
                "test-camera",
                scientific_name,
                common_name,
                taxa_id,
            ),
        )
        await db.commit()

    try:
        response = await client.get(
            f"/api/species/{quote(localized_common_name, safe='')}/stats",
            headers={"Accept-Language": "es"},
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["total_sightings"] == 2
        assert data["first_seen"].endswith("Z")
        assert data["last_seen"].endswith("Z")
        assert len(data["recent_sightings"]) == 2
        assert all(item["detection_time"].endswith("Z") for item in data["recent_sightings"])
    finally:
        await _cleanup_taxon_and_detections(taxa_id=taxa_id, event_prefix=event_prefix)


@pytest.mark.asyncio
async def test_leaderboard_species_includes_unknown_bird_without_sql_binding_error(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    event_id = f"leaderboard-unknown-{uuid.uuid4().hex[:8]}"
    await _insert_hidden_unknown_detection(event_id)

    try:
        response = await client.get("/api/leaderboard/species?span=month")
        assert response.status_code == 200, response.text
        payload = response.json()
        unknown_rows = [row for row in payload["species"] if row["species"] == "Unknown Bird"]
        assert len(unknown_rows) == 1
        assert unknown_rows[0]["window_count"] >= 1
        assert unknown_rows[0]["window_first_seen"].endswith("Z")
        assert unknown_rows[0]["window_last_seen"].endswith("Z")
    finally:
        await _delete_detection(event_id)


@pytest.mark.asyncio
async def test_species_stats_accepts_cyrillic_common_name_and_aggregates_aliases(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    suffix = uuid.uuid4().hex[:8]
    taxa_id = 900000 + int(suffix[:4], 16)
    event_prefix = f"speciesstats-ru-{suffix}"
    scientific_name = f"Aves{suffix} cyrillica"
    common_name = f"Test Bird {suffix}"
    localized_common_name = f"Лазоревка {suffix}"
    async with get_db() as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO taxonomy_cache (scientific_name, common_name, taxa_id)
            VALUES (?, ?, ?)
            """,
            (scientific_name, common_name, taxa_id),
        )
        await db.execute(
            """
            INSERT OR REPLACE INTO taxonomy_translations (taxa_id, language_code, common_name)
            VALUES (?, ?, ?)
            """,
            (taxa_id, "ru", localized_common_name),
        )
        now = datetime.now(timezone.utc).isoformat(sep=" ")
        for idx, display_name in enumerate([localized_common_name, scientific_name], start=1):
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
                    idx,
                    0.9,
                    display_name,
                    display_name,
                    f"{event_prefix}_{idx}",
                    "test-camera",
                    scientific_name,
                    localized_common_name,
                    taxa_id,
                ),
            )
        await db.commit()

    try:
        response = await client.get(
            f"/api/species/{quote(localized_common_name, safe='')}/stats",
            headers={"Accept-Language": "ru"},
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["species_name"] == localized_common_name
        assert data["taxa_id"] == taxa_id
        assert data["scientific_name"] == scientific_name
        assert data["common_name"] == localized_common_name
        assert data["total_sightings"] == 2
        assert len(data["recent_sightings"]) == 2
    finally:
        await _cleanup_taxon_and_detections(taxa_id=taxa_id, event_prefix=event_prefix)


@pytest.mark.asyncio
async def test_species_stats_unknown_bird_includes_hidden_noncanonical_labels(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    event_id = f"speciesstats-unknown-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat(sep=" ")
    async with get_db() as db:
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
                0.74,
                "Great tit and allies",
                "Great tit and allies",
                event_id,
                "test-camera",
                "Great tit and allies",
                "Great tit and allies",
                None,
            ),
        )
        await db.commit()

    try:
        response = await client.get("/api/species/Unknown%20Bird/stats")
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["species_name"] == "Unknown Bird"
        assert data["total_sightings"] == 1
        assert len(data["recent_sightings"]) == 1
        sighting = data["recent_sightings"][0]
        assert sighting["frigate_event"] == event_id
        assert sighting["display_name"] == "Unknown Bird"
        assert sighting["category_name"] == "Unknown Bird"
        assert sighting["scientific_name"] is None
        assert sighting["common_name"] is None
        assert sighting["taxa_id"] is None
    finally:
        async with get_db() as db:
            await db.execute("DELETE FROM detections WHERE frigate_event = ?", (event_id,))
            await db.commit()
