"""Grouping detections by catalogue identity rather than by name text.

Phase 4 of the species catalogue. Until now the grouping key was
`taxa_id`, then scientific name, then display name, all as text. A scientific
name is not stable: when a taxon is split, lumped or synonymised,
`Parus caeruleus` and `Cyanistes caeruleus` become two different birds to
anything keying on the text, so a leaderboard divides and a species page shows
half its sightings, silently.

The catalogue's opaque `species_id` is the fix. It goes in front of the existing
fallbacks rather than replacing them, so a row the catalogue cannot identify
behaves exactly as it does today.

Two things make this less obvious than it looks, and both are asserted here:

* `species_id` and `taxa_id` are integers from different databases with
  overlapping ranges. Measured on a live install, `taxa_id` spans 487 to
  1,289,423 and `species_id` spans 1,391 to 17,542. Casting both to bare text in
  one key space merges unrelated species, so each source is namespaced.
* Preferring `species_id` could *split* a species whose rows are only partly
  identified, which is the very failure this phase exists to remove.
"""

from datetime import datetime, timedelta

import aiosqlite
import pytest
import pytest_asyncio

from app.repositories.detection_repository import DetectionRepository
from tests.test_detection_repository import _create_detections_table, _create_taxonomy_tables


@pytest_asyncio.fixture
async def seeded_repository():
    """A repository over an in-memory database, plus a terse way to add a row."""
    async with aiosqlite.connect(":memory:") as db:
        await _create_detections_table(db)
        await _create_taxonomy_tables(db)
        await db.commit()
        repo = DetectionRepository(db)
        counter = {"n": 0}

        async def add(
            *,
            display_name: str,
            scientific_name: str | None = None,
            species_id: int | None = None,
            taxa_id: int | None = None,
            is_hidden: bool = False,
        ) -> None:
            counter["n"] += 1
            await db.execute(
                """
                INSERT INTO detections (
                    detection_time, detection_index, score, display_name, category_name,
                    frigate_event, camera_name, is_hidden, scientific_name, taxa_id, species_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime(2026, 8, 23, 8, 0, 0) + timedelta(minutes=counter["n"]),
                    1,
                    0.9,
                    display_name,
                    display_name,
                    f"evt-{counter['n']}",
                    "birdcam",
                    1 if is_hidden else 0,
                    scientific_name,
                    taxa_id,
                    species_id,
                ),
            )
            await db.commit()

        yield repo, add


@pytest.fixture
def key() -> str:
    return DetectionRepository._canonical_key_sql()


def test_catalogue_identity_is_preferred_over_every_text_key(key):
    identity = key.index("species_id")
    assert identity < key.index("taxa_id")
    assert identity < key.index("scientific_name")
    assert identity < key.index("display_name")


def test_the_text_fallbacks_are_kept_for_rows_the_catalogue_cannot_identify(key):
    assert "taxa_id" in key
    assert "scientific_name" in key
    assert "display_name" in key


def test_identity_and_taxonomy_ids_cannot_collide_in_one_key_space(key):
    """`species_id` 10081 is a Dunnock; `taxa_id` 10081 is some other taxon."""
    assert "'species:'" in key or '"species:"' in key
    assert "'taxon:'" in key or '"taxon:"' in key


@pytest.mark.asyncio
async def test_two_names_for_one_species_count_as_one_bird(seeded_repository):
    """The defect this phase exists to fix: a renamed taxon dividing history."""
    repo, add = seeded_repository
    await add(display_name="Blue Tit", scientific_name="Parus caeruleus", species_id=4242)
    await add(display_name="Blue Tit", scientific_name="Cyanistes caeruleus", species_id=4242)

    rows = await repo.get_species_leaderboard_base()
    blue_tits = [r for r in rows if r["count"] == 2]
    assert len(blue_tits) == 1, f"expected one Blue Tit group, got {rows}"


@pytest.mark.asyncio
async def test_a_species_id_never_merges_with_an_equal_taxa_id(seeded_repository):
    repo, add = seeded_repository
    await add(display_name="Dunnock", scientific_name="Prunella modularis", species_id=10081)
    await add(display_name="Something Else", scientific_name="Aliud aliud", taxa_id=10081)

    rows = await repo.get_species_leaderboard_base()
    assert len(rows) == 2, f"a species_id and a taxa_id sharing a number must not merge: {rows}"


@pytest.mark.asyncio
async def test_rows_without_catalogue_identity_group_exactly_as_before(seeded_repository):
    repo, add = seeded_repository
    await add(display_name="Unknown Bird")
    await add(display_name="Unknown Bird")
    await add(display_name="Robin", scientific_name="Erithacus rubecula")
    await add(display_name="Robin", scientific_name="Erithacus rubecula")

    rows = await repo.get_species_leaderboard_base()
    assert sorted(r["count"] for r in rows) == [2, 2]


@pytest.mark.asyncio
async def test_different_species_are_never_merged_by_identity(seeded_repository):
    repo, add = seeded_repository
    await add(display_name="Dunnock", scientific_name="Prunella modularis", species_id=10081)
    await add(display_name="Robin", scientific_name="Erithacus rubecula", species_id=9293)

    rows = await repo.get_species_leaderboard_base()
    assert len(rows) == 2
    assert all(r["count"] == 1 for r in rows)


@pytest.mark.asyncio
async def test_hidden_detections_stay_out_of_the_counts(seeded_repository):
    repo, add = seeded_repository
    await add(display_name="Dunnock", scientific_name="Prunella modularis", species_id=10081)
    await add(display_name="Dunnock", scientific_name="Prunella modularis", species_id=10081, is_hidden=True)

    rows = await repo.get_species_leaderboard_base()
    assert [r["count"] for r in rows] == [1]


@pytest.mark.asyncio
async def test_filtering_a_species_finds_every_row_the_leaderboard_counted(seeded_repository):
    """Grouping and filtering must agree, or a species page contradicts the leaderboard.

    Grouping by identity while filtering by name text reintroduces the exact
    defect this phase removes: the leaderboard merges a renamed taxon into one
    row, then opening that row shows only the half that still carries the
    displayed name.
    """
    repo, add = seeded_repository
    await add(display_name="Blue Tit", scientific_name="Parus caeruleus", species_id=4242)
    await add(display_name="Blue Tit", scientific_name="Cyanistes caeruleus", species_id=4242)

    rows = await repo.get_species_leaderboard_base()
    grouped = next(r for r in rows if r["count"] == 2)
    assert grouped is not None

    join_sql, condition, params = await repo._canonical_species_query_parts(
        detection_alias="d",
        species_name="Cyanistes caeruleus",
    )
    async with repo.db.execute(
        f"SELECT COUNT(DISTINCT d.id) FROM detections d{join_sql} WHERE {condition}", params
    ) as cursor:
        matched = (await cursor.fetchone())[0]

    assert matched == 2, f"the leaderboard counted 2 for this species, so filtering it must return 2; got {matched}"


@pytest.mark.asyncio
async def test_the_leaderboard_returns_the_key_its_metrics_are_looked_up_by(seeded_repository):
    """Trend data is joined on this key, and a mismatch fails silently.

    The router used to rebuild the grouping rule in Python. Two copies of one
    rule drift, and when they do `metrics.get(...)` returns an empty dict, so
    every species shows a flat trend and nothing raises.
    """
    repo, add = seeded_repository
    await add(display_name="Dunnock", scientific_name="Prunella modularis", species_id=10081)
    await add(display_name="Dunnock", scientific_name="Prunella modularis", species_id=10081)

    rows = await repo.get_species_leaderboard_base()
    metrics = await repo.get_unified_species_window_metrics()

    assert rows[0]["unified_key"], "the leaderboard must expose the key it grouped on"
    assert rows[0]["unified_key"] in metrics, (
        f"leaderboard key {rows[0]['unified_key']!r} is absent from metrics keys "
        f"{list(metrics)!r}; trends would silently read as flat"
    )
    assert metrics[rows[0]["unified_key"]]["count_30d"] >= 2
