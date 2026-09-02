"""A manual correction must carry the corrected species' identity, never the old bird's.

Reported as leaderboard duplicates (#386): a Dunnock retagged by hand kept the
`species_id` of the Tree Sparrow or Jungle Babbler it had been called before, so
the leaderboard grouped it as a separate species with the same name.
"""

import pytest
import pytest_asyncio

from app.database import close_db, get_db, init_db
from app.repositories.detection_repository import DetectionRepository


@pytest_asyncio.fixture(autouse=True)
async def db():
    await init_db()
    try:
        async with get_db() as conn:
            await conn.execute("DELETE FROM detections")
            await conn.execute(
                """INSERT INTO detections (frigate_event, camera_name, detection_time, detection_index, score,
                   display_name, category_name, scientific_name, common_name, taxa_id, species_id, is_hidden)
                   VALUES ('evt1','cam','2026-08-31 08:32:25',1,0.63,
                   'Eurasian Tree Sparrow','Passer montanus','Passer montanus','Eurasian Tree Sparrow',555,9774,0)"""
            )
            await conn.commit()
        yield
    finally:
        await close_db()


@pytest.mark.asyncio
async def test_retagging_to_another_species_replaces_the_identity():
    async with get_db() as conn:
        repo = DetectionRepository(conn)
        await repo.apply_manual_species_tag(
            frigate_event="evt1",
            display_name="Dunnock",
            category_name="Prunella modularis",
            scientific_name="Prunella modularis",
            common_name="Dunnock",
            taxa_id=13988,
            audio_confirmed=False,
            audio_species=None,
            audio_score=None,
            species_id=10081,
        )
        await conn.commit()
        async with conn.execute("SELECT display_name, species_id FROM detections WHERE frigate_event='evt1'") as cur:
            row = await cur.fetchone()
    assert row == ("Dunnock", 10081)


@pytest.mark.asyncio
async def test_retagging_without_a_resolved_identity_does_not_keep_the_old_birds():
    """If the corrected name cannot be resolved, no identity is honest. The old
    bird's identity is not."""
    async with get_db() as conn:
        repo = DetectionRepository(conn)
        await repo.apply_manual_species_tag(
            frigate_event="evt1",
            display_name="Dunnock",
            category_name="Prunella modularis",
            scientific_name="Prunella modularis",
            common_name="Dunnock",
            taxa_id=13988,
            audio_confirmed=False,
            audio_species=None,
            audio_score=None,
            species_id=None,
        )
        await conn.commit()
        async with conn.execute("SELECT species_id FROM detections WHERE frigate_event='evt1'") as cur:
            (species_id,) = await cur.fetchone()
    assert species_id is None
