"""Replay the reported Dunnock evidence without a model or a production database."""

from copy import deepcopy
from contextlib import asynccontextmanager, closing
import json
import os
import sqlite3

import aiosqlite
import httpx
import pytest

from app.services.counted_bird_identity import resolve_bird_identities


@pytest.fixture
def evidence():
    return {
        "birds": [
            {
                "id": 694,
                "species": "Unknown Bird",
                "classifier_label": "Prunella modularis",
                "classifier_score": 0.4518895447254181,
                "manual_species": False,
                "is_hidden": False,
                "clip_variant": "frigate_snapshot",
                "frame_index": 0,
                "crop_box": [873, 341, 1112, 480],
            }
        ],
        "candidates": [
            {
                "source_mode": "frigate_hint_crop",
                "clip_variant": "frigate_snapshot",
                "frame_index": 0,
                "crop_box": [785, 303, 1209, 499],
            }
        ],
        "detection": {
            "category_name": "Prunella modularis",
            "scientific_name": "Prunella modularis",
            "common_name": "Dunnock",
            "display_name": "Dunnock",
            "score": 0.9395976066589355,
            "manual_tagged": False,
        },
        "threshold": 0.6,
    }


def test_reported_dunnock_uses_accepted_identity_without_inventing_crop_confidence(evidence):
    original = deepcopy(evidence)
    bird = resolve_bird_identities(**evidence)[0]
    assert bird["species"] == "Prunella modularis"
    assert bird["common_name"] == "Dunnock"
    assert bird["identity_source"] == "visit"
    assert bird["identity_score"] == pytest.approx(0.9395976066589355)
    assert bird["classifier_score"] == pytest.approx(0.4518895447254181)
    assert evidence == original


@pytest.mark.parametrize(
    "change",
    [
        "other_species",
        "other_frame",
        "other_variant",
        "missing_hint",
        "far_box",
        "ambiguous",
        "bad_score",
        "weak_parent",
        "unknown_parent",
    ],
)
def test_uncertain_or_unrelated_primary_evidence_does_not_name_a_bird(evidence, change):
    bird = evidence["birds"][0]
    if change == "other_species":
        bird["classifier_label"] = "Cardinalis cardinalis"
    if change == "other_frame":
        evidence["candidates"][0]["frame_index"] = 1
    if change == "other_variant":
        evidence["candidates"][0]["clip_variant"] = "event"
    if change == "missing_hint":
        evidence["candidates"] = []
    if change == "far_box":
        bird["crop_box"] = [10, 10, 50, 50]
    if change == "ambiguous":
        evidence["birds"].append({**bird, "id": 695, "crop_box": [890, 350, 920, 400]})
    if change == "bad_score":
        evidence["detection"]["score"] = float("nan")
    if change == "weak_parent":
        evidence["detection"]["score"] = 0.4
    if change == "unknown_parent":
        evidence["detection"] = {"category_name": "Unknown Bird", "score": 0.99}
    assert resolve_bird_identities(**evidence)[0]["species"] == "Unknown Bird"


@pytest.mark.parametrize("override", [{"manual_species": True, "species": "European Robin"}, {"is_hidden": True}])
def test_owner_choices_survive_identity_resolution(evidence, override):
    evidence["birds"][0].update(override)
    assert resolve_bird_identities(**evidence)[0]["species"] == evidence["birds"][0]["species"]


def test_primary_name_does_not_spread_to_another_bird(evidence):
    evidence["birds"].append({**evidence["birds"][0], "id": 695, "crop_box": [10, 10, 50, 50]})
    assert [b["species"] for b in resolve_bird_identities(**evidence)] == ["Prunella modularis", "Unknown Bird"]


@pytest.mark.parametrize("cached_identity", ["Turdus migratorius", None])
def test_visit_identity_cannot_override_a_conflicting_or_ambiguous_cached_crop_alias(evidence, cached_identity):
    evidence["birds"][0]["classifier_label"] = "Robin"
    evidence["detection"].update(
        category_name="Erithacus rubecula",
        scientific_name="Erithacus rubecula",
        common_name="Robin",
        display_name="Robin",
    )
    bird = resolve_bird_identities(**evidence, species_aliases={"robin": cached_identity})[0]
    assert bird["species"] == "Unknown Bird"
    assert bird["identity_source"] == "crop"
    assert bird["classifier_label"] == "Robin"
    assert bird["classifier_score"] == evidence["birds"][0]["classifier_score"]


@pytest.mark.parametrize("species_aliases", [{}, {"dunnock": "Prunella modularis"}])
def test_matching_crop_common_name_can_borrow_its_accepted_visit_identity(evidence, species_aliases):
    evidence["birds"][0]["classifier_label"] = "Dunnock"
    bird = resolve_bird_identities(**evidence, species_aliases=species_aliases)[0]
    assert bird["species"] == "Prunella modularis"
    assert bird["identity_source"] == "visit"
    assert bird["identity_score"] == evidence["detection"]["score"]


def test_crop_naming_uses_configured_threshold(evidence):
    evidence["candidates"] = []
    evidence["birds"][0]["classifier_score"] = 0.62
    bird = resolve_bird_identities(**evidence)[0]
    assert bird["species"] == "Prunella modularis"
    assert bird["identity_source"] == "crop"


def test_owner_named_visit_does_not_reuse_an_old_model_score(evidence):
    evidence["detection"].update(manual_tagged=True, score=0.14)
    bird = resolve_bird_identities(**evidence)[0]
    assert bird["species"] == "Prunella modularis"
    assert bird["identity_source"] == "visit"
    assert bird["identity_score"] is None
    assert bird["classifier_score"] == evidence["birds"][0]["classifier_score"]


@pytest.fixture
def history(evidence, tmp_path, monkeypatch):
    from app.config import settings
    from app.routers import proxy

    path = tmp_path / "history.db"
    with closing(sqlite3.connect(os.environ["DB_PATH"])) as source, closing(sqlite3.connect(path)) as db:
        source.backup(db)
        db.execute("DELETE FROM detections")
        db.execute(
            "INSERT INTO detections (frigate_event, camera_name, detection_time, detection_index, score, display_name, category_name, scientific_name, common_name) VALUES ('reported-dunnock','birdcam','2026-10-02 16:09:21',0,.9395976,'Dunnock','Prunella modularis','Prunella modularis','Dunnock')"
        )
        b = evidence["birds"][0]
        db.execute(
            "INSERT INTO bird_observations (id, frigate_event, bird_index, candidate_id, clip_variant, frame_index, crop_box_json, detector_confidence, species, classifier_label, classifier_score) VALUES (694,'reported-dunnock',0,'crop','frigate_snapshot',0,?,.509,'Unknown Bird','Prunella modularis',.4518895)",
            (json.dumps(b["crop_box"]),),
        )
        db.execute(
            "INSERT INTO snapshot_candidates (frigate_event,candidate_id,frame_index,source_mode,clip_variant,crop_box_json,ranking_score) VALUES ('reported-dunnock','hint',0,'frigate_hint_crop','frigate_snapshot',?,.59)",
            (json.dumps(evidence["candidates"][0]["crop_box"]),),
        )
        db.commit()

    @asynccontextmanager
    async def get_db():
        async with aiosqlite.connect(path) as db:
            yield db

    monkeypatch.setattr(proxy, "get_db", get_db)
    monkeypatch.setattr(settings.classification, "threshold", 0.6)
    return path


@pytest.mark.asyncio
async def test_existing_dunnock_resolves_consistently_without_rewriting_original_evidence(history):
    from app.repositories.bird_observation_repository import BirdObservationRepository

    async with aiosqlite.connect(history) as db:
        repo = BirdObservationRepository(db)
        resolved = (await repo.resolved_for_events(["reported-dunnock"]))["reported-dunnock"]
        assert resolved[0]["species"] == "Prunella modularis"
        assert resolved[0]["identity_source"] == "visit"
        summary = (await repo.summaries_for_events(["reported-dunnock"]))["reported-dunnock"]
        assert summary["unknown"] == 0
        assert summary["species"] == [{"species": "Prunella modularis", "count": 1}]
        assert (await repo.list_for_event("reported-dunnock"))[0]["species"] == "Unknown Bird"


@pytest.mark.asyncio
@pytest.mark.parametrize("name,status", [("Dun", 400), ("Dunnock", 200), ("Prunella modularis", 200)])
async def test_counted_species_save_requires_complete_known_identity(history, name, status):
    from app.main import app
    from app.auth import create_access_token

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch(
            "/api/frigate/reported-dunnock/birds/694",
            json={"species": name},
            headers={"Authorization": f"Bearer {create_access_token('owner')}"},
        )
    assert response.status_code == status
    if status == 200:
        assert response.json()["species"] == "Prunella modularis"
        assert response.json()["common_name"] == "Dunnock"
    else:
        with closing(sqlite3.connect(history)) as db:
            assert db.execute("SELECT species,manual_species FROM bird_observations WHERE id=694").fetchone() == (
                "Unknown Bird",
                0,
            )


def test_common_and_scientific_parent_aliases_share_effective_identity_without_rewriting_evidence(evidence):
    evidence["birds"][0].update(species="Dunnock", classifier_label="Dunnock", classifier_score=0.9)
    evidence["birds"].append(
        {**evidence["birds"][0], "id": 695, "species": "Prunella modularis", "manual_species": True}
    )
    before = deepcopy(evidence)
    birds = resolve_bird_identities(**evidence)
    assert [bird["species"] for bird in birds] == ["Prunella modularis", "Prunella modularis"]
    assert [bird["classifier_label"] for bird in birds] == ["Dunnock", "Dunnock"]
    assert evidence == before


@pytest.mark.asyncio
async def test_cached_aliases_group_summaries_and_api_birds_without_rewriting_evidence(history):
    from app.repositories.bird_observation_repository import BirdObservationRepository

    with closing(sqlite3.connect(history)) as db:
        db.execute(
            "INSERT INTO taxonomy_cache (scientific_name, common_name) VALUES ('Erithacus rubecula', 'European Robin')"
        )
        db.execute(
            "UPDATE bird_observations SET species = 'European Robin', classifier_label = 'European Robin', classifier_score = .9"
        )
        db.execute(
            "INSERT INTO bird_observations (frigate_event, bird_index, candidate_id, clip_variant, frame_index, crop_box_json, detector_confidence, species, classifier_label, classifier_score, manual_species) VALUES ('reported-dunnock',1,'second','frigate_snapshot',0,'[10,10,50,50]',.9,'Erithacus rubecula','European Robin',.9,1)"
        )
        db.commit()
    async with aiosqlite.connect(history) as db:
        repo = BirdObservationRepository(db)
        birds = await repo.named_for_event("reported-dunnock")
        assert [bird["species"] for bird in birds] == ["Erithacus rubecula", "Erithacus rubecula"]
        summary = (await repo.summaries_for_events(["reported-dunnock"]))["reported-dunnock"]
        assert summary["species"] == [{"species": "Erithacus rubecula", "count": 2}]
        raw = await repo.list_for_event("reported-dunnock")
        assert [bird["species"] for bird in raw] == ["European Robin", "Erithacus rubecula"]


@pytest.mark.asyncio
async def test_ambiguous_cached_common_alias_does_not_merge_distinct_species(history):
    from app.repositories.bird_observation_repository import BirdObservationRepository

    with closing(sqlite3.connect(history)) as db:
        db.execute("INSERT INTO taxonomy_cache (scientific_name, common_name) VALUES ('Erithacus rubecula', 'Robin')")
        db.execute("INSERT INTO taxonomy_cache (scientific_name, common_name) VALUES ('Turdus migratorius', 'Robin')")
        db.execute("UPDATE bird_observations SET species = 'Robin', classifier_label = 'Robin', classifier_score = .9")
        db.commit()
    async with aiosqlite.connect(history) as db:
        repo = BirdObservationRepository(db)
        bird = (await repo.resolved_for_events(["reported-dunnock"]))["reported-dunnock"][0]
        assert bird["species"] == "Robin"
        assert not bird.get("scientific_name")
        named = (await repo.named_for_event("reported-dunnock"))[0]
        assert named["species"] == "Robin"
        assert not named.get("scientific_name")


@pytest.mark.asyncio
async def test_summary_taxonomy_lookup_is_shared_by_a_page_of_events(history):
    from app.repositories.bird_observation_repository import BirdObservationRepository

    with closing(sqlite3.connect(history)) as db:
        db.execute(
            "INSERT INTO taxonomy_cache (scientific_name, common_name) VALUES ('Haemorhous mexicanus', 'House Finch')"
        )
        for index in range(100):
            event_id = f"batch-alias-{index}"
            db.execute(
                "INSERT INTO detections (frigate_event, camera_name, detection_time, detection_index, score, display_name, category_name) VALUES (?,'test','2026-10-03 08:00:00',1,.9,'House Finch','House Finch')",
                (event_id,),
            )
            db.execute(
                "INSERT INTO bird_observations (frigate_event, bird_index, candidate_id, clip_variant, frame_index, crop_box_json, detector_confidence, species, classifier_label, classifier_score) VALUES (?,0,'bird','event',0,'[10,10,50,50]',.9,'House Finch','House Finch',.9)",
                (event_id,),
            )
        db.commit()
    statements = []
    async with aiosqlite.connect(history) as db:
        await db.set_trace_callback(statements.append)
        summaries = await BirdObservationRepository(db).summaries_for_events(
            [f"batch-alias-{index}" for index in range(100)]
        )
    assert len(summaries) == 100
    assert all(
        summary["species"] == [{"species": "Haemorhous mexicanus", "count": 1}] for summary in summaries.values()
    )
    assert len([query for query in statements if "FROM taxonomy_cache" in query]) == 1


def _resolve(evidence):
    return resolve_bird_identities(
        evidence["birds"], evidence["candidates"], evidence["detection"], threshold=evidence["threshold"]
    )


def test_the_tracked_bird_is_pointed_out_even_when_the_name_is_too_uncertain_to_lend(evidence):
    # Needs your call holds exactly the visits whose name is below the threshold. The reviewer
    # still needs to see which bird that name is about, without the name being copied onto it (#481).
    evidence["detection"]["score"] = 0.52
    evidence["birds"].append({**deepcopy(evidence["birds"][0]), "id": 695, "crop_box": [100, 100, 200, 200]})

    tracked, other = _resolve(evidence)

    assert tracked["tracked"] is True
    assert tracked["identity_source"] == "crop" and tracked["species"] == "Unknown Bird"
    assert other["tracked"] is False


def test_no_bird_is_pointed_out_when_frigates_box_covers_two(evidence):
    evidence["birds"].append({**deepcopy(evidence["birds"][0]), "id": 695, "crop_box": [880, 350, 1100, 470]})

    assert [bird["tracked"] for bird in _resolve(evidence)] == [False, False]


def test_no_bird_is_pointed_out_without_frigates_box(evidence):
    evidence["candidates"] = []

    assert [bird["tracked"] for bird in _resolve(evidence)] == [False]
