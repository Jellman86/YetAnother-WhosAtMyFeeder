from datetime import datetime

import pytest

from app.database import get_db
from app.repositories.detection_repository import Detection, DetectionRepository


def detection(event: str, label: str, score: float = 0.8) -> Detection:
    return Detection(
        detection_time=datetime(2026, 10, 2),
        detection_index=1,
        score=score,
        display_name=label,
        category_name=label,
        scientific_name=label,
        frigate_event=event,
        camera_name="birdcam",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("insert_method", ["create", "upsert_if_higher_score", "insert_if_not_exists"])
async def test_initial_identity_survives_reingest_and_automatic_overturn(insert_method):
    event = f"original-identity-{insert_method}"
    async with get_db() as db:
        repo = DetectionRepository(db)
        await getattr(repo, insert_method)(detection(event, "Dryobates pubescens"))
        await repo.upsert_if_higher_score(detection(event, "Baeolophus bicolor", 0.97))
        current = await repo.get_by_frigate_event(event)
        assert current.category_name == "Baeolophus bicolor"
        assert await repo.get_initial_classification_labels(event) == ["Dryobates pubescens"]
        await repo.upsert_if_higher_score(detection(event, "Cardinalis cardinalis", 0.99))
        assert await repo.get_initial_classification_labels(event) == ["Dryobates pubescens"]


@pytest.mark.asyncio
async def test_legacy_identity_is_not_inferred_from_a_later_label():
    async with get_db() as db:
        repo = DetectionRepository(db)
        event = "legacy-unknown-initial-identity"
        await repo.create(detection(event, "Baeolophus bicolor"))
        # A migrated historical row has no first-classification evidence.
        await db.execute(
            "DELETE FROM detection_initial_classifications WHERE detection_id = (SELECT id FROM detections WHERE frigate_event = ?)",
            (event,),
        )
        await db.commit()
        await repo.upsert_if_higher_score(detection(event, "Cardinalis cardinalis", 0.99))
        assert await repo.get_initial_classification_labels(event) is None


@pytest.mark.asyncio
async def test_delete_and_new_capture_do_not_inherit_deleted_initial_evidence():
    async with get_db() as db:
        repo = DetectionRepository(db)
        event = "deleted-initial-identity"
        await repo.create(detection(event, "Dryobates pubescens"))
        await repo.delete_by_frigate_event(event)
        await repo.create(detection(event, "Baeolophus bicolor"))
        assert await repo.get_initial_classification_labels(event) == ["Baeolophus bicolor"]


@pytest.mark.asyncio
@pytest.mark.parametrize("decision", ["confirm", "change"])
@pytest.mark.parametrize("model_agrees", [True, False])
async def test_explicit_owner_species_choice_survives_requested_model_reclassification(decision, model_agrees):
    async with get_db() as db:
        repo = DetectionRepository(db)
        event = f"owner-choice-{decision}-{model_agrees}"
        await repo.create(detection(event, "Dryobates pubescens"))
        if decision == "confirm":
            await repo.confirm_manual_species_tag(frigate_event=event)
            expected = "Dryobates pubescens"
        else:
            expected = "Baeolophus bicolor"
            await repo.apply_manual_species_tag(
                frigate_event=event,
                display_name=expected,
                category_name=expected,
                scientific_name=expected,
                common_name=None,
                taxa_id=None,
                audio_confirmed=False,
                audio_species=None,
                audio_score=None,
            )
        await db.commit()
        assert await repo.get_owner_species_choice_labels(event) == [expected]
        model_label = expected if model_agrees else "Cardinalis cardinalis"
        await repo.update_primary_classification(
            frigate_event=event,
            display_name=model_label,
            category_name=model_label,
            score=0.99,
            detection_index=2,
            scientific_name=model_label,
            common_name=None,
            taxa_id=None,
            audio_confirmed=False,
            audio_species=None,
            audio_score=None,
            manual_override=True,
        )
        assert await repo.get_owner_species_choice_labels(event) == [expected]
        assert (await repo.get_by_frigate_event(event)).manual_tagged
        assert await repo.get_initial_classification_labels(event) == ["Dryobates pubescens"]
