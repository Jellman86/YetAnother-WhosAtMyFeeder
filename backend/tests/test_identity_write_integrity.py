"""A canonical identity must not be lost or left stale by a later write (#360).

Catalogue identity is what decides whether two detections are the same bird.
Two writes were careless with it: the higher-score upsert replaced species_id
unconditionally, so a result carrying none nulled an identity the backfill had
already resolved; and a manual correction rewrote every name but left the old
species_id in place, quietly filing the corrected bird under the species it
used to be.
"""

import pytest
import pytest_asyncio

from app.database import close_db, get_db, init_db
from app.repositories.detection_repository import Detection
from app.repositories.detection_repository import DetectionRepository

SPECIES_ID = 10081


@pytest_asyncio.fixture(autouse=True)
async def clean_db():
    await init_db()
    try:
        async with get_db() as db:
            await db.execute("DELETE FROM detections")
            await db.commit()
        yield
    finally:
        await close_db()


async def _stored(db, event: str) -> dict:
    async with db.execute(
        "SELECT species_id, taxa_id, display_name, scientific_name FROM detections WHERE frigate_event = ?",
        (event,),
    ) as cursor:
        row = await cursor.fetchone()
    return {"species_id": row[0], "taxa_id": row[1], "display_name": row[2], "scientific_name": row[3]}


def _detection(**overrides) -> Detection:
    base = dict(
        frigate_event="evt",
        camera_name="cam1",
        detection_time="2026-08-31 09:00:00",
        detection_index=1,
        score=0.5,
        display_name="Dunnock",
        category_name="Dunnock",
        scientific_name="Prunella modularis",
    )
    base.update(overrides)
    return Detection(**base)


@pytest.mark.asyncio
async def test_a_later_result_without_an_identity_keeps_the_one_already_resolved():
    """The backfill resolves an identity; a higher-score result for the same
    species that carries none must not take it away."""
    async with get_db() as db:
        repo = DetectionRepository(db)
        await repo.insert_if_not_exists(_detection())
        await repo.assign_species_id_by_scientific_name("Prunella modularis", SPECIES_ID)
        assert (await _stored(db, "evt"))["species_id"] == SPECIES_ID

        await repo.upsert_if_higher_score(_detection(score=0.9, species_id=None))

        assert (await _stored(db, "evt"))["species_id"] == SPECIES_ID


@pytest.mark.asyncio
async def test_a_result_for_a_different_species_replaces_the_identity():
    """Keeping an identity must not mean keeping the wrong one: when the
    species itself changes, the new result's identity wins, even when absent."""
    async with get_db() as db:
        repo = DetectionRepository(db)
        await repo.insert_if_not_exists(_detection())
        await repo.assign_species_id_by_scientific_name("Prunella modularis", SPECIES_ID)

        await repo.upsert_if_higher_score(
            _detection(
                score=0.95,
                display_name="Robin",
                category_name="Robin",
                scientific_name="Erithacus rubecula",
            )
        )

        stored = await _stored(db, "evt")
        assert stored["display_name"] == "Robin"
        assert stored["species_id"] is None


@pytest.mark.asyncio
async def test_a_manual_correction_does_not_leave_the_old_identity_behind():
    """A corrected bird filed under the species it used to be is worse than
    one with no identity at all: the wrong one groups it with the wrong bird."""
    async with get_db() as db:
        repo = DetectionRepository(db)
        await repo.insert_if_not_exists(_detection())
        await repo.assign_species_id_by_scientific_name("Prunella modularis", SPECIES_ID)

        await repo.apply_manual_species_tag(
            frigate_event="evt",
            display_name="Robin",
            category_name="Robin",
            scientific_name="Erithacus rubecula",
            common_name="Robin",
            taxa_id=None,
            audio_confirmed=False,
            audio_species=None,
            audio_score=None,
        )
        await db.commit()

        stored = await _stored(db, "evt")
        assert stored["display_name"] == "Robin"
        assert stored["species_id"] != SPECIES_ID


@pytest.mark.asyncio
async def test_confirming_the_same_species_keeps_its_identity():
    """Confirming what is already there is not a correction and must not
    disturb the identity."""
    async with get_db() as db:
        repo = DetectionRepository(db)
        await repo.insert_if_not_exists(_detection())
        await repo.assign_species_id_by_scientific_name("Prunella modularis", SPECIES_ID)

        await repo.apply_manual_species_tag(
            frigate_event="evt",
            display_name="Dunnock",
            category_name="Dunnock",
            scientific_name="Prunella modularis",
            common_name="Dunnock",
            taxa_id=None,
            audio_confirmed=False,
            audio_species=None,
            audio_score=None,
        )
        await db.commit()

        assert (await _stored(db, "evt"))["species_id"] == SPECIES_ID
