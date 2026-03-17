import csv
import io
import uuid
from datetime import datetime

import httpx
import pytest
import pytest_asyncio

from app.config import settings
from app.database import get_db
from app.main import app


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture(autouse=True)
def reset_auth_and_ebird_settings():
    original_auth_enabled = settings.auth.enabled
    original_public_enabled = settings.public_access.enabled
    original_ebird_enabled = settings.ebird.enabled
    original_ebird_api_key = settings.ebird.api_key
    original_ebird_locale = settings.ebird.locale
    original_lat = settings.location.latitude
    original_lng = settings.location.longitude
    original_state = getattr(settings.location, "state", None)
    original_country = getattr(settings.location, "country", None)

    settings.auth.enabled = False
    settings.public_access.enabled = False
    settings.location.latitude = 51.501
    settings.location.longitude = -0.142

    yield

    settings.auth.enabled = original_auth_enabled
    settings.public_access.enabled = original_public_enabled
    settings.ebird.enabled = original_ebird_enabled
    settings.ebird.api_key = original_ebird_api_key
    settings.ebird.locale = original_ebird_locale
    settings.location.latitude = original_lat
    settings.location.longitude = original_lng
    settings.location.state = original_state
    settings.location.country = original_country


@pytest_asyncio.fixture(autouse=True)
async def clear_detections():
    async with get_db() as db:
        await db.execute("DELETE FROM detections")
        await db.execute("DELETE FROM taxonomy_cache")
        await db.commit()
    yield
    async with get_db() as db:
        await db.execute("DELETE FROM detections")
        await db.execute("DELETE FROM taxonomy_cache")
        await db.commit()


async def _insert_detection(
    *,
    frigate_event: str,
    detection_time: datetime,
    score: float,
    display_name: str,
    scientific_name: str,
    common_name: str,
    taxa_id: int | None = None,
    camera_name: str = "feeder",
    is_hidden: bool = False,
    video_classification_provider: str | None = None,
    video_classification_backend: str | None = None,
) -> None:
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO detections (
                detection_time, detection_index, score, display_name, category_name,
                frigate_event, camera_name, is_hidden, scientific_name, common_name, taxa_id,
                video_classification_provider, video_classification_backend
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                detection_time,
                0,
                score,
                display_name,
                display_name,
                frigate_event,
                camera_name,
                1 if is_hidden else 0,
                scientific_name,
                common_name,
                taxa_id,
                video_classification_provider,
                video_classification_backend,
            ),
        )
        await db.commit()


async def _insert_taxonomy_cache(*, scientific_name: str, common_name: str, taxa_id: int) -> None:
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO taxonomy_cache (scientific_name, common_name, taxa_id, is_not_found)
            VALUES (?, ?, ?, 0)
            """,
            (scientific_name, common_name, taxa_id),
        )
        await db.commit()


def _read_csv_rows(payload: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(payload)))


@pytest.mark.asyncio
async def test_ebird_export_is_strict_19_column_csv_without_header(client: httpx.AsyncClient):
    settings.ebird.enabled = False
    settings.ebird.api_key = None

    event_id = f"evt-{uuid.uuid4().hex[:8]}"
    await _insert_detection(
        frigate_event=event_id,
        detection_time=datetime(2026, 3, 12, 7, 5, 22),
        score=0.8421,
        display_name="Localized Name",
        scientific_name="Turdus merula",
        common_name="Common Blackbird",
        camera_name="garden",
    )

    response = await client.get("/api/ebird/export")

    assert response.status_code == 200, response.text
    rows = _read_csv_rows(response.text)
    assert len(rows) == 1

    row = rows[0]
    assert len(row) == 19
    assert row[0] == "Common Blackbird"
    assert row[1] == "Turdus"
    assert row[2] == "merula"
    assert row[8] == "03/12/2026"
    assert row[9] == "07:05"
    assert row[10] == ""
    assert row[11] == ""
    assert row[12] == "Stationary"
    assert row[14] == "0"
    assert row[18] == "Exported from YA-WAMF; confidence 0.84"


@pytest.mark.asyncio
async def test_ebird_export_omits_hidden_detections(client: httpx.AsyncClient):
    settings.ebird.enabled = False
    settings.ebird.api_key = None

    await _insert_detection(
        frigate_event=f"evt-{uuid.uuid4().hex[:8]}",
        detection_time=datetime(2026, 3, 12, 8, 0, 0),
        score=0.9,
        display_name="Hidden Bird",
        scientific_name="Parus major",
        common_name="Great Tit",
        is_hidden=True,
    )

    response = await client.get("/api/ebird/export")

    assert response.status_code == 200, response.text
    assert _read_csv_rows(response.text) == []


@pytest.mark.asyncio
async def test_ebird_export_filters_to_inclusive_requested_date_range(client: httpx.AsyncClient):
    settings.ebird.enabled = False
    settings.ebird.api_key = None

    await _insert_detection(
        frigate_event=f"evt-{uuid.uuid4().hex[:8]}",
        detection_time=datetime(2026, 3, 11, 18, 0, 0),
        score=0.91,
        display_name="Bird One",
        scientific_name="Parus major",
        common_name="Great Tit",
    )
    await _insert_detection(
        frigate_event=f"evt-{uuid.uuid4().hex[:8]}",
        detection_time=datetime(2026, 3, 12, 7, 30, 0),
        score=0.88,
        display_name="Bird Two",
        scientific_name="Turdus merula",
        common_name="Common Blackbird",
    )
    await _insert_detection(
        frigate_event=f"evt-{uuid.uuid4().hex[:8]}",
        detection_time=datetime(2026, 3, 13, 8, 15, 0),
        score=0.8,
        display_name="Bird Three",
        scientific_name="Cyanistes caeruleus",
        common_name="Blue Tit",
    )

    response = await client.get("/api/ebird/export", params={"from": "2026-03-12", "to": "2026-03-13"})

    assert response.status_code == 200, response.text
    rows = _read_csv_rows(response.text)
    assert len(rows) == 2
    assert {(row[0], row[8]) for row in rows} == {
        ("Common Blackbird", "03/12/2026"),
        ("Blue Tit", "03/13/2026"),
    }


@pytest.mark.asyncio
async def test_ebird_export_supports_open_ended_date_range_filters(client: httpx.AsyncClient):
    settings.ebird.enabled = False
    settings.ebird.api_key = None

    await _insert_detection(
        frigate_event=f"evt-{uuid.uuid4().hex[:8]}",
        detection_time=datetime(2026, 3, 10, 7, 0, 0),
        score=0.76,
        display_name="Bird One",
        scientific_name="Parus major",
        common_name="Great Tit",
    )
    await _insert_detection(
        frigate_event=f"evt-{uuid.uuid4().hex[:8]}",
        detection_time=datetime(2026, 3, 12, 7, 30, 0),
        score=0.88,
        display_name="Bird Two",
        scientific_name="Turdus merula",
        common_name="Common Blackbird",
    )
    await _insert_detection(
        frigate_event=f"evt-{uuid.uuid4().hex[:8]}",
        detection_time=datetime(2026, 3, 14, 8, 15, 0),
        score=0.8,
        display_name="Bird Three",
        scientific_name="Cyanistes caeruleus",
        common_name="Blue Tit",
    )

    from_response = await client.get("/api/ebird/export", params={"from": "2026-03-12"})
    to_response = await client.get("/api/ebird/export", params={"to": "2026-03-12"})

    assert from_response.status_code == 200, from_response.text
    assert to_response.status_code == 200, to_response.text

    from_rows = _read_csv_rows(from_response.text)
    to_rows = _read_csv_rows(to_response.text)

    assert {(row[0], row[8]) for row in from_rows} == {
        ("Common Blackbird", "03/12/2026"),
        ("Blue Tit", "03/14/2026"),
    }
    assert {(row[0], row[8]) for row in to_rows} == {
        ("Great Tit", "03/10/2026"),
        ("Common Blackbird", "03/12/2026"),
    }


@pytest.mark.asyncio
async def test_ebird_export_prefers_english_taxonomy_common_name_over_localized_detection_name(
    client: httpx.AsyncClient,
):
    settings.ebird.enabled = True
    settings.ebird.api_key = "test-token"
    settings.ebird.locale = "ru"

    taxa_id = 424242
    await _insert_taxonomy_cache(
        scientific_name="Turdus merula",
        common_name="Common Blackbird",
        taxa_id=taxa_id,
    )
    await _insert_detection(
        frigate_event=f"evt-{uuid.uuid4().hex[:8]}",
        detection_time=datetime(2026, 3, 12, 9, 0, 0),
        score=0.77,
        display_name="Merel UI",
        scientific_name="Turdus merula",
        common_name="Amsel Localized",
        taxa_id=taxa_id,
    )

    response = await client.get("/api/ebird/export")

    assert response.status_code == 200, response.text
    rows = _read_csv_rows(response.text)
    assert len(rows) == 1
    assert rows[0][0] == "Common Blackbird"


@pytest.mark.asyncio
async def test_ebird_export_does_not_duplicate_rows_when_multiple_taxonomy_cache_entries_share_taxa_id(
    client: httpx.AsyncClient,
):
    settings.ebird.enabled = False
    settings.ebird.api_key = None

    taxa_id = 515151
    await _insert_taxonomy_cache(
        scientific_name="Turdus merula",
        common_name="Common Blackbird",
        taxa_id=taxa_id,
    )
    await _insert_taxonomy_cache(
        scientific_name="Merula merula",
        common_name="Blackbird Alias",
        taxa_id=taxa_id,
    )
    await _insert_detection(
        frigate_event=f"evt-{uuid.uuid4().hex[:8]}",
        detection_time=datetime(2026, 3, 12, 10, 0, 0),
        score=0.81,
        display_name="Blackbird UI",
        scientific_name="Turdus merula",
        common_name="Localized Blackbird",
        taxa_id=taxa_id,
    )

    response = await client.get("/api/ebird/export")

    assert response.status_code == 200, response.text
    rows = _read_csv_rows(response.text)
    assert len(rows) == 1
    assert rows[0][0] == "Common Blackbird"


@pytest.mark.asyncio
async def test_ebird_export_rejects_invalid_date_query(client: httpx.AsyncClient):
    settings.ebird.enabled = False
    settings.ebird.api_key = None

    response = await client.get("/api/ebird/export", params={"from": "2026-13-40"})

    assert response.status_code == 400
    assert "Invalid date" in response.text


@pytest.mark.asyncio
async def test_ebird_export_rejects_inverted_date_range_query(client: httpx.AsyncClient):
    settings.ebird.enabled = False
    settings.ebird.api_key = None

    response = await client.get("/api/ebird/export", params={"from": "2026-03-13", "to": "2026-03-12"})

    assert response.status_code == 400
    assert "Invalid date range" in response.text


@pytest.mark.asyncio
async def test_ebird_export_tolerates_non_finite_score_metadata(client: httpx.AsyncClient):
    settings.ebird.enabled = False
    settings.ebird.api_key = None

    event_id = f"evt-{uuid.uuid4().hex[:8]}"
    await _insert_detection(
        frigate_event=event_id,
        detection_time=datetime(2026, 3, 12, 11, 0, 0),
        score=0.91,
        display_name="Bad Score Bird",
        scientific_name="Parus major",
        common_name="Great Tit",
    )
    async with get_db() as db:
        await db.execute(
            "UPDATE detections SET score = ? WHERE frigate_event = ?",
            ("bad-score", event_id),
        )
        await db.commit()

    response = await client.get("/api/ebird/export")

    assert response.status_code == 200, response.text
    rows = _read_csv_rows(response.text)
    assert len(rows) == 1
    assert rows[0][0] == "Great Tit"
    assert rows[0][18] == "Exported from YA-WAMF"


@pytest.mark.asyncio
async def test_ebird_export_uses_daily_duration_window_per_date(client: httpx.AsyncClient):
    settings.ebird.enabled = False
    settings.ebird.api_key = None

    await _insert_detection(
        frigate_event=f"evt-{uuid.uuid4().hex[:8]}",
        detection_time=datetime(2026, 3, 12, 7, 5, 0),
        score=0.71,
        display_name="Bird One",
        scientific_name="Parus major",
        common_name="Great Tit",
    )
    await _insert_detection(
        frigate_event=f"evt-{uuid.uuid4().hex[:8]}",
        detection_time=datetime(2026, 3, 12, 7, 47, 0),
        score=0.74,
        display_name="Bird Two",
        scientific_name="Parus major",
        common_name="Great Tit",
    )

    response = await client.get("/api/ebird/export", params={"from": "2026-03-12", "to": "2026-03-12"})

    assert response.status_code == 200, response.text
    rows = _read_csv_rows(response.text)
    assert len(rows) == 2
    assert rows[0][14] == "42"
    assert rows[1][14] == "42"


@pytest.mark.asyncio
async def test_ebird_export_computes_duration_per_exported_date_bucket(client: httpx.AsyncClient):
    settings.ebird.enabled = False
    settings.ebird.api_key = None

    await _insert_detection(
        frigate_event=f"evt-{uuid.uuid4().hex[:8]}",
        detection_time=datetime(2026, 3, 11, 6, 0, 0),
        score=0.55,
        display_name="Older Bird",
        scientific_name="Parus major",
        common_name="Great Tit",
    )
    await _insert_detection(
        frigate_event=f"evt-{uuid.uuid4().hex[:8]}",
        detection_time=datetime(2026, 3, 11, 6, 10, 0),
        score=0.65,
        display_name="Older Bird Two",
        scientific_name="Parus major",
        common_name="Great Tit",
    )
    await _insert_detection(
        frigate_event=f"evt-{uuid.uuid4().hex[:8]}",
        detection_time=datetime(2026, 3, 12, 7, 0, 0),
        score=0.75,
        display_name="Newer Bird",
        scientific_name="Turdus merula",
        common_name="Common Blackbird",
    )
    await _insert_detection(
        frigate_event=f"evt-{uuid.uuid4().hex[:8]}",
        detection_time=datetime(2026, 3, 12, 7, 45, 0),
        score=0.85,
        display_name="Newer Bird Two",
        scientific_name="Turdus merula",
        common_name="Common Blackbird",
    )

    response = await client.get("/api/ebird/export")

    assert response.status_code == 200, response.text
    rows = _read_csv_rows(response.text)
    assert len(rows) == 4
    durations_by_timestamp = {(row[8], row[9]): row[14] for row in rows}
    assert durations_by_timestamp[("03/12/2026", "07:45")] == "45"
    assert durations_by_timestamp[("03/12/2026", "07:00")] == "45"
    assert durations_by_timestamp[("03/11/2026", "06:10")] == "10"
    assert durations_by_timestamp[("03/11/2026", "06:00")] == "10"


@pytest.mark.asyncio
async def test_ebird_export_includes_available_runtime_metadata_in_submission_comments(client: httpx.AsyncClient):
    settings.ebird.enabled = False
    settings.ebird.api_key = None

    await _insert_detection(
        frigate_event=f"evt-{uuid.uuid4().hex[:8]}",
        detection_time=datetime(2026, 3, 12, 12, 0, 0),
        score=0.953,
        display_name="Metadata Bird",
        scientific_name="Turdus merula",
        common_name="Common Blackbird",
        video_classification_provider="intel_gpu",
        video_classification_backend="openvino",
    )

    response = await client.get("/api/ebird/export")

    assert response.status_code == 200, response.text
    rows = _read_csv_rows(response.text)
    assert len(rows) == 1
    assert rows[0][18] == "Exported from YA-WAMF; provider intel_gpu; backend openvino; confidence 0.95"


@pytest.mark.asyncio
async def test_ebird_export_uses_configured_state_and_country_when_present(client: httpx.AsyncClient):
    settings.ebird.enabled = False
    settings.ebird.api_key = None
    settings.location.state = "California"
    settings.location.country = "United States"

    await _insert_detection(
        frigate_event=f"evt-{uuid.uuid4().hex[:8]}",
        detection_time=datetime(2026, 3, 12, 12, 30, 0),
        score=0.88,
        display_name="Region Bird",
        scientific_name="Turdus merula",
        common_name="Common Blackbird",
    )

    response = await client.get("/api/ebird/export")

    assert response.status_code == 200, response.text
    rows = _read_csv_rows(response.text)
    assert len(rows) == 1
    assert rows[0][10] == "California"
    assert rows[0][11] == "United States"


@pytest.mark.asyncio
async def test_ebird_export_excludes_unknown_bird_rows(client: httpx.AsyncClient):
    settings.ebird.enabled = False
    settings.ebird.api_key = None

    await _insert_detection(
        frigate_event=f"evt-{uuid.uuid4().hex[:8]}",
        detection_time=datetime(2026, 3, 12, 12, 30, 0),
        score=0.51,
        display_name="Unknown Bird",
        scientific_name="Unknown Bird",
        common_name="Unknown Bird",
    )

    response = await client.get("/api/ebird/export")

    assert response.status_code == 200, response.text
    assert _read_csv_rows(response.text) == []


@pytest.mark.asyncio
async def test_ebird_export_falls_back_to_scientific_name_when_common_name_missing(client: httpx.AsyncClient):
    settings.ebird.enabled = False
    settings.ebird.api_key = None

    await _insert_detection(
        frigate_event=f"evt-{uuid.uuid4().hex[:8]}",
        detection_time=datetime(2026, 3, 12, 13, 0, 0),
        score=0.96,
        display_name="Большая синица",
        scientific_name="Parus major",
        common_name="Большая синица",
    )

    response = await client.get("/api/ebird/export")

    assert response.status_code == 200, response.text
    rows = _read_csv_rows(response.text)
    assert len(rows) == 1
    # Should fallback to scientific name in the common name column (index 0)
    assert rows[0][0] == "Parus major"


@pytest.mark.asyncio
async def test_ebird_export_range_filter_still_applies_after_strict_row_suppression(client: httpx.AsyncClient):
    settings.ebird.enabled = False
    settings.ebird.api_key = None

    taxa_id = 737373
    await _insert_taxonomy_cache(
        scientific_name="Parus major",
        common_name="Great Tit",
        taxa_id=taxa_id,
    )
    await _insert_detection(
        frigate_event=f"evt-{uuid.uuid4().hex[:8]}",
        detection_time=datetime(2026, 3, 11, 7, 0, 0),
        score=0.9,
        display_name="Большая синица",
        scientific_name="Parus major",
        common_name="Большая синица",
        taxa_id=taxa_id,
    )
    await _insert_detection(
        frigate_event=f"evt-{uuid.uuid4().hex[:8]}",
        detection_time=datetime(2026, 3, 12, 7, 0, 0),
        score=0.55,
        display_name="Unknown Bird",
        scientific_name="Unknown Bird",
        common_name="Unknown Bird",
    )
    await _insert_detection(
        frigate_event=f"evt-{uuid.uuid4().hex[:8]}",
        detection_time=datetime(2026, 3, 13, 7, 0, 0),
        score=0.9,
        display_name="Большая синица",
        scientific_name="Parus major",
        common_name="Большая синица",
        taxa_id=taxa_id,
    )

    response = await client.get("/api/ebird/export", params={"from": "2026-03-12", "to": "2026-03-13"})

    assert response.status_code == 200, response.text
    rows = _read_csv_rows(response.text)
    assert len(rows) == 1
    assert rows[0][0] == "Great Tit"
    assert rows[0][8] == "03/13/2026"
