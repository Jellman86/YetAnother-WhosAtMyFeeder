"""Giving audio detections the same identity visual ones carry.

Audio correlation was the last read path keyed on name text. BirdNET-Go reports
a scientific name and a scientific name moves. Measured on a live install of
56,027 audio detections: 84 of 85 species resolve to a catalogue identity, and
the one that does not is `Corvus monedula`, which IOC 14.2 calls
`Coloeus monedula` after the jackdaw genus split. Those 28 detections cannot
currently join to a visual detection of the same bird.

The rule is the one the detection backfill already follows: a name resolving to
exactly one identity gains it, anything ambiguous or unknown keeps nothing.
"""

import aiosqlite
import pytest
import pytest_asyncio

from app.repositories.detection_repository import DetectionRepository
from app.services.audio_identity import resolve_audio_identity


class _Resolver:
    """Stands in for the catalogue with a fixed, explicit opinion."""

    def __init__(self, answers: dict[str, tuple[int | None, str]]):
        self._answers = answers

    def resolve_scientific_name(self, name):
        return self._answers.get(str(name or "").strip(), (None, "unknown"))


def test_a_name_the_catalogue_holds_once_gains_that_identity():
    resolver = _Resolver({"Prunella modularis": (10081, "resolved")})
    assert resolve_audio_identity("Prunella modularis", resolver=resolver) == 10081


def test_an_ambiguous_name_gains_nothing_rather_than_picking_one():
    resolver = _Resolver({"Shared name": (None, "ambiguous")})
    assert resolve_audio_identity("Shared name", resolver=resolver) is None


def test_a_name_no_source_holds_gains_nothing():
    """`Corvus monedula` is the real example until an alias records the split."""
    resolver = _Resolver({})
    assert resolve_audio_identity("Corvus monedula", resolver=resolver) is None


def test_no_catalogue_is_not_an_error():
    resolver = _Resolver({"Prunella modularis": (None, "unavailable")})
    assert resolve_audio_identity("Prunella modularis", resolver=resolver) is None


@pytest.mark.parametrize("blank", [None, "", "   "])
def test_a_blank_name_is_never_looked_up(blank):
    class Exploding:
        def resolve_scientific_name(self, name):
            raise AssertionError("should not be consulted")

    assert resolve_audio_identity(blank, resolver=Exploding()) is None


def test_a_resolver_that_fails_never_breaks_ingest():
    """Audio ingest must not stop because the catalogue had a bad moment."""

    class Broken:
        def resolve_scientific_name(self, name):
            raise RuntimeError("catalogue on fire")

    assert resolve_audio_identity("Prunella modularis", resolver=Broken()) is None


async def _audio_table(db: aiosqlite.Connection) -> None:
    await db.execute(
        """
        CREATE TABLE audio_detections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP NOT NULL,
            species VARCHAR NOT NULL,
            confidence FLOAT NOT NULL,
            sensor_id VARCHAR,
            raw_data TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            scientific_name VARCHAR,
            source_event_id VARCHAR(512),
            species_id INTEGER
        )
        """
    )
    await db.commit()


@pytest_asyncio.fixture
async def audio_repo():
    async with aiosqlite.connect(":memory:") as db:
        await _audio_table(db)
        yield DetectionRepository(db), db


@pytest.mark.asyncio
async def test_the_backfill_only_touches_rows_without_an_identity(audio_repo):
    repo, db = audio_repo
    await db.execute(
        "INSERT INTO audio_detections (timestamp, species, confidence, scientific_name, species_id)"
        " VALUES ('2026-08-23 08:00:00','Dunnock',0.9,'Prunella modularis',NULL)"
    )
    await db.execute(
        "INSERT INTO audio_detections (timestamp, species, confidence, scientific_name, species_id)"
        " VALUES ('2026-08-23 08:01:00','Robin',0.9,'Erithacus rubecula',4242)"
    )
    await db.commit()

    resolver = _Resolver({"Prunella modularis": (10081, "resolved"), "Erithacus rubecula": (9293, "resolved")})
    summary = await repo.backfill_audio_species_ids(resolver=resolver)

    assert summary["identified"] == 1
    rows = await (await db.execute("SELECT scientific_name, species_id FROM audio_detections ORDER BY id")).fetchall()
    assert rows[0][1] == 10081
    assert rows[1][1] == 4242, "an identity already recorded is never rewritten"


@pytest.mark.asyncio
async def test_the_backfill_counts_what_it_could_not_identify(audio_repo):
    repo, db = audio_repo
    await db.execute(
        "INSERT INTO audio_detections (timestamp, species, confidence, scientific_name)"
        " VALUES ('2026-08-23 08:00:00','Jackdaw',0.9,'Corvus monedula')"
    )
    await db.commit()

    summary = await repo.backfill_audio_species_ids(resolver=_Resolver({}))
    assert summary["identified"] == 0
    assert summary["unresolved"] == 1


@pytest.mark.asyncio
async def test_running_the_backfill_again_changes_nothing(audio_repo):
    repo, db = audio_repo
    await db.execute(
        "INSERT INTO audio_detections (timestamp, species, confidence, scientific_name)"
        " VALUES ('2026-08-23 08:00:00','Dunnock',0.9,'Prunella modularis')"
    )
    await db.commit()
    resolver = _Resolver({"Prunella modularis": (10081, "resolved")})

    first = await repo.backfill_audio_species_ids(resolver=resolver)
    second = await repo.backfill_audio_species_ids(resolver=resolver)

    assert first["identified"] == 1
    assert second["identified"] == 0, "a second run has nothing left to do"


@pytest.mark.asyncio
async def test_two_names_for_one_bird_are_counted_once(audio_repo):
    """The whole point: a renamed taxon must not appear twice in the counts."""
    from datetime import datetime, timedelta

    repo, db = audio_repo
    now = datetime(2026, 8, 23, 8, 0, 0)
    for offset, (species, sci) in enumerate([("Jackdaw", "Corvus monedula"), ("Western Jackdaw", "Coloeus monedula")]):
        await db.execute(
            "INSERT INTO audio_detections (timestamp, species, confidence, scientific_name, species_id)"
            " VALUES (?,?,?,?,7056)",
            ((now + timedelta(minutes=offset)).isoformat(sep=" "), species, 0.9, sci),
        )
    await db.commit()

    rows = await repo.get_audio_species_counts(
        now - timedelta(hours=1), now + timedelta(hours=1), now - timedelta(hours=2), now - timedelta(hours=1)
    )
    assert len(rows) == 1, f"one bird under two names must count once: {rows}"
    assert rows[0]["window_count"] == 2


@pytest.mark.asyncio
async def test_audio_without_identity_groups_by_name_as_before(audio_repo):
    from datetime import datetime, timedelta

    repo, db = audio_repo
    now = datetime(2026, 8, 23, 8, 0, 0)
    for offset, sci in enumerate(["Prunella modularis", "Prunella modularis", "Erithacus rubecula"]):
        await db.execute(
            "INSERT INTO audio_detections (timestamp, species, confidence, scientific_name) VALUES (?,?,?,?)",
            ((now + timedelta(minutes=offset)).isoformat(sep=" "), "x", 0.9, sci),
        )
    await db.commit()

    rows = await repo.get_audio_species_counts(
        now - timedelta(hours=1), now + timedelta(hours=1), now - timedelta(hours=2), now - timedelta(hours=1)
    )
    assert sorted(r["window_count"] for r in rows) == [1, 2]
