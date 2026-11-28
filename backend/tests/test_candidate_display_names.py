"""Tests for resolving localized common names on snapshot candidates and counted birds."""

from unittest.mock import AsyncMock, patch

import aiosqlite
import httpx
import pytest
import pytest_asyncio

from app.main import app
from app.repositories.bird_observation_repository import (
    BirdObservationRepository,
    resolve_display_names_for_labels,
)
from app.services.species_names import SpeciesIdentityNames


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


@pytest.mark.asyncio
async def test_resolve_display_names_uses_catalogue_synonyms_when_taxonomy_cache_misses(tmp_path):
    db_path = tmp_path / "species.db"
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """CREATE TABLE taxonomy_cache (
                scientific_name TEXT,
                common_name TEXT,
                taxa_id INTEGER,
                manual_common_name TEXT,
                is_not_found INTEGER DEFAULT 0
            )"""
        )
        await db.execute(
            """CREATE TABLE taxonomy_translations (
                taxa_id INTEGER,
                language_code TEXT,
                common_name TEXT
            )"""
        )
        await db.commit()

        with (
            patch(
                "app.repositories.bird_observation_repository.species_catalog_resolver.resolve_scientific_name",
                return_value=(42, "resolved"),
            ),
            patch(
                "app.repositories.bird_observation_repository.species_name_lookup.resolve",
                return_value={42: SpeciesIdentityNames(display="Western Jackdaw", scientific="Coloeus monedula")},
            ),
        ):
            resolved = await resolve_display_names_for_labels(db, ["Corvus monedula", "Unknown Bird", "Robin"], "en")

    assert resolved == {"Corvus monedula": ("Coloeus monedula", "Western Jackdaw")}


@pytest.mark.asyncio
async def test_resolve_display_names_falls_back_to_bundled_species_reference(tmp_path):
    db_path = tmp_path / "species.db"
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """CREATE TABLE taxonomy_cache (
                scientific_name TEXT,
                common_name TEXT,
                taxa_id INTEGER,
                manual_common_name TEXT,
                is_not_found INTEGER DEFAULT 0
            )"""
        )
        await db.execute(
            """CREATE TABLE taxonomy_translations (
                taxa_id INTEGER,
                language_code TEXT,
                common_name TEXT
            )"""
        )
        await db.commit()

        with patch(
            "app.repositories.bird_observation_repository.species_catalog_resolver.resolve_scientific_name",
            return_value=(None, "unavailable"),
        ):
            resolved = await resolve_display_names_for_labels(db, ["Coloeus monedula"], "en")

    assert resolved == {"Coloeus monedula": ("Coloeus monedula", "Western Jackdaw")}


@pytest.mark.asyncio
async def test_named_for_event_populates_common_name_for_scientific_bird_and_unknown_best_guess(tmp_path):
    db_path = tmp_path / "birds.db"
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(
            """
            CREATE TABLE detections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                frigate_event TEXT UNIQUE,
                category_name TEXT,
                scientific_name TEXT,
                common_name TEXT,
                display_name TEXT,
                score REAL,
                manual_tagged INTEGER DEFAULT 0,
                classification_input_json TEXT
            );
            CREATE TABLE detection_initial_classifications (
                detection_id INTEGER,
                classification_input_json TEXT
            );
            CREATE TABLE bird_observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                frigate_event TEXT,
                bird_index INTEGER,
                candidate_id TEXT,
                clip_variant TEXT,
                frame_index INTEGER,
                crop_box_json TEXT,
                detector_confidence REAL,
                species TEXT,
                classifier_label TEXT,
                classifier_score REAL,
                manual_species INTEGER DEFAULT 0,
                is_hidden INTEGER DEFAULT 0
            );
            CREATE TABLE snapshot_candidates (
                frigate_event TEXT,
                clip_variant TEXT,
                frame_index INTEGER,
                crop_box_json TEXT,
                source_mode TEXT,
                content_sha256 TEXT
            );
            CREATE TABLE taxonomy_cache (
                scientific_name TEXT,
                common_name TEXT,
                taxa_id INTEGER,
                manual_common_name TEXT,
                is_not_found INTEGER DEFAULT 0
            );
            CREATE TABLE taxonomy_translations (
                taxa_id INTEGER,
                language_code TEXT,
                common_name TEXT
            );
            INSERT INTO detections (frigate_event, category_name, scientific_name, common_name, display_name, score)
            VALUES ('evt-1', 'Columba livia', 'Columba livia', 'Rock Pigeon', 'Rock Pigeon', 0.65);
            INSERT INTO bird_observations
                (frigate_event, bird_index, candidate_id, clip_variant, frame_index, crop_box_json,
                 detector_confidence, species, classifier_label, classifier_score)
            VALUES
                ('evt-1', 0, 'obs-0', 'recording', 192, '[10, 10, 50, 50]', 0.88, 'Unknown Bird', 'Chroicocephalus ridibundus', 0.31),
                ('evt-1', 1, 'obs-1', 'recording', 192, '[100, 100, 180, 180]', 0.94, 'Corvus monedula', 'Corvus monedula', 0.81);
            """
        )
        await db.commit()

        with (
            patch(
                "app.repositories.bird_observation_repository.species_catalog_resolver.resolve_scientific_name",
                side_effect=lambda name: (42, "resolved") if name == "Corvus monedula" else (None, "unknown"),
            ),
            patch(
                "app.repositories.bird_observation_repository.species_name_lookup.resolve",
                return_value={42: SpeciesIdentityNames(display="Western Jackdaw", scientific="Coloeus monedula")},
            ),
        ):
            birds = await BirdObservationRepository(db).named_for_event("evt-1", "en")

    unknown_bird = next(bird for bird in birds if bird["species"] == "Unknown Bird")
    jackdaw = next(bird for bird in birds if bird["species"] == "Corvus monedula")
    assert unknown_bird.get("common_name") is None
    assert unknown_bird["classifier_common_name"] == "Black-headed Gull"
    assert jackdaw["scientific_name"] == "Coloeus monedula"
    assert jackdaw["common_name"] == "Western Jackdaw"


@pytest.mark.asyncio
async def test_snapshot_candidates_endpoint_includes_resolved_classifier_common_name(client: httpx.AsyncClient):
    with (
        patch("app.routers.proxy.get_db") as mock_get_db,
        patch("app.routers.proxy.DetectionRepository") as mock_repo_cls,
        patch("app.routers.proxy.BirdObservationRepository") as mock_bird_repo_cls,
        patch(
            "app.routers.proxy.resolve_display_names_for_labels",
            new=AsyncMock(return_value={"Corvus monedula": ("Coloeus monedula", "Western Jackdaw")}),
        ),
        patch("app.services.media_cache.media_cache.get_snapshot", new_callable=AsyncMock, return_value=b"snap"),
        patch(
            "app.services.media_cache.media_cache.get_snapshot_metadata",
            new_callable=AsyncMock,
            return_value={"source": "hq_candidate_full_frame"},
        ),
        patch(
            "app.services.media_cache.media_cache.get_cached_image_version",
            new_callable=AsyncMock,
            return_value="v1",
        ),
    ):
        mock_get_db.return_value.__aenter__.return_value = AsyncMock()
        mock_bird_repo_cls.return_value.named_for_event = AsyncMock(return_value=[])
        mock_repo_cls.return_value.is_as_recorded_dismissed = AsyncMock(return_value=False)
        mock_repo_cls.return_value.list_snapshot_candidates = AsyncMock(
            return_value=[
                {
                    "candidate_id": "cand-jackdaw",
                    "frame_index": 5,
                    "frame_offset_seconds": 2.0,
                    "source_mode": "model_crop",
                    "clip_variant": "recording",
                    "crop_box": [10, 10, 80, 80],
                    "crop_confidence": 0.92,
                    "classifier_label": "Corvus monedula",
                    "classifier_score": 0.90,
                    "ranking_score": 0.90,
                    "selected": False,
                    "thumbnail_ref": "t1",
                    "image_ref": "i1",
                    "snapshot_source": "hq_candidate_model_crop",
                }
            ]
        )

        response = await client.get("/api/frigate/evt-1/snapshot/candidates")

    assert response.status_code == 200
    candidate = response.json()["candidates"][0]
    assert candidate["classifier_label"] == "Corvus monedula"
    assert candidate["classifier_common_name"] == "Western Jackdaw"
    assert candidate["classifier_scientific_name"] == "Coloeus monedula"
