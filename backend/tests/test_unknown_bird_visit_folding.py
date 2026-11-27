"""Naming an Unknown bird can join it to a visit, so Visits can fall while no capture is lost (#1096).

An Unknown bird capture is its own visit, because nothing says which bird it was. Once it is named,
by "Analyse all unknowns" or by the owner, it follows the visit rule like any other capture: within
the visit gap of a visit of the same species on the same camera, it joins that visit.

The day summary's ``unknown_visit_count`` says how many of its visits are Unknown birds, judged by
each visit's first capture with the rule that shows a bird as "Unknown bird". It is read from the
same visit openings as ``visit_count``, so it can never exceed it, and the ``top_species`` row named
"Unknown Bird" is built from the same openings, so the Dashboard never shows two Unknown totals.
"""

from datetime import datetime, timedelta

import httpx
import pytest
import pytest_asyncio

from app.auth import create_access_token
from app.config import settings
from app.database import close_db, get_db, init_db
from app.main import app
from app.repositories.detection_repository import DetectionRepository
from app.routers import stats as stats_router
from app.utils.api_datetime import serialize_storage_datetime

NOW = datetime(2035, 6, 14, 18, 0, 0)
START = NOW - timedelta(hours=1)
ROBIN = "Erithacus rubecula"
UNKNOWN = "Unknown Bird"


@pytest_asyncio.fixture(autouse=True)
async def isolated_db(monkeypatch):
    monkeypatch.setattr(stats_router, "utc_naive_now", lambda: NOW)
    monkeypatch.setattr(settings.classification, "threshold", 0.6)
    monkeypatch.setattr(settings.visits, "gap_seconds", 60)
    monkeypatch.setattr(settings.auth, "enabled", True)
    monkeypatch.setattr(settings.auth, "initial_setup_complete", True)
    monkeypatch.setattr(settings.auth, "username", "owner")
    monkeypatch.setattr(settings.public_access, "enabled", False)
    monkeypatch.setenv("TZ", "UTC")
    await init_db()
    try:
        async with get_db() as db:
            await db.execute("DELETE FROM detections")
            await db.commit()
        yield
    finally:
        await close_db()


async def _seed_rows(*rows: tuple[str, datetime, str, str | None, int]) -> None:
    """Each row is (event, capture time, display name, scientific name, hidden)."""
    async with get_db() as db:
        await db.executemany(
            """INSERT INTO detections (
                   frigate_event, camera_name, detection_time, detection_index, score,
                   display_name, category_name, scientific_name, common_name, is_hidden, manual_tagged
               ) VALUES (?, 'birdcam', ?, 1, 0.9, ?, ?, ?, ?, ?, 0)""",
            [
                (event, serialize_storage_datetime(at), name, name, scientific, scientific, hidden)
                for event, at, name, scientific, hidden in rows
            ],
        )
        await db.commit()


async def _seed_capture(
    event: str,
    at: datetime,
    display: str,
    *,
    category: str | None = None,
    scientific: str | None = None,
    common: str | None = None,
    no_common: bool = False,
    species_id: int | None = None,
    taxa_id: int | None = None,
    camera: str = "birdcam",
    stored_time: str | None = None,
) -> None:
    """One visible capture with every identity field set as given, for legacy and mixed shapes.

    ``stored_time`` writes the time text exactly as given, for rows stored in an older format.
    """
    async with get_db() as db:
        await db.execute(
            """INSERT INTO detections (
                   frigate_event, camera_name, detection_time, detection_index, score, display_name,
                   category_name, scientific_name, common_name, species_id, taxa_id, is_hidden, manual_tagged
               ) VALUES (?, ?, ?, 1, 0.9, ?, ?, ?, ?, ?, ?, 0, 0)""",
            (
                event,
                camera,
                stored_time or serialize_storage_datetime(at),
                display,
                display if category is None else category,
                scientific,
                None if no_common else scientific if common is None else common,
                species_id,
                taxa_id,
            ),
        )
        await db.commit()


async def _seed(*captures: tuple[str, int, str | None]) -> None:
    """Each capture is (event, seconds after START, scientific name or None for an Unknown bird)."""
    await _seed_rows(
        *((event, START + timedelta(seconds=seconds), name or UNKNOWN, name, 0) for event, seconds, name in captures)
    )


async def _visits() -> int:
    async with get_db() as db:
        return len((await DetectionRepository(db).get_window_visits(START, NOW)).visits)


async def _visible_captures() -> int:
    async with get_db() as db:
        async with db.execute("SELECT COUNT(*) FROM detections WHERE COALESCE(is_hidden, 0) = 0") as cursor:
            return int((await cursor.fetchone())[0])


async def _name_by_analysis(event: str, scientific_name: str) -> None:
    """The write "Analyse all unknowns" makes when a clip names an Unknown bird."""
    async with get_db() as db:
        assert await DetectionRepository(db).update_primary_classification(
            frigate_event=event,
            display_name=scientific_name,
            category_name=scientific_name,
            score=0.8,
            detection_index=1,
            scientific_name=scientific_name,
            common_name=scientific_name,
            taxa_id=None,
            audio_confirmed=False,
            audio_species=None,
            audio_score=None,
            manual_override=False,
        )


async def _name_by_owner(event: str, scientific_name: str) -> None:
    """The write a manual correction makes when the owner names an Unknown bird."""
    async with get_db() as db:
        assert await DetectionRepository(db).apply_manual_species_tag(
            frigate_event=event,
            display_name=scientific_name,
            category_name=scientific_name,
            scientific_name=scientific_name,
            common_name=scientific_name,
            taxa_id=None,
            audio_confirmed=False,
            audio_species=None,
            audio_score=None,
        )
        # The router commits a manual correction once its other writes are done.
        await db.commit()


async def _summary(query: str = "", headers: dict[str, str] | None = None) -> dict:
    owner = {"Authorization": f"Bearer {create_access_token('owner')}"}
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/stats/daily-summary{query}", headers=owner if headers is None else headers)
    assert response.status_code == 200, response.text
    return response.json()


def _unknown_row(body: dict) -> dict | None:
    return next((row for row in body["top_species"] if row["species"] == "Unknown Bird"), None)


def _counts(body: dict) -> tuple[int, int]:
    """Visits and Unknown visits, after checking the response agrees with itself.

    The Unknown row of the species list carries the Unknown subtotal, and the species rows together
    hold every visit exactly once: none counted twice, none left out.
    """
    row = _unknown_row(body)
    assert (row["visit_count"] if row else 0) == body["unknown_visit_count"], body["top_species"]
    assert sum(item["visit_count"] for item in body["top_species"]) == body["visit_count"], body["top_species"]
    return body["visit_count"], body["unknown_visit_count"]


def _rows(body: dict) -> dict[str, tuple[int, int, str]]:
    """Each species row as (visits, captures, latest capture)."""
    return {item["species"]: (item["visit_count"], item["count"], item["latest_event"]) for item in body["top_species"]}


# The fold itself -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_naming_an_unknown_bird_beside_a_visit_of_that_species_joins_it():
    await _seed(("robin-1", 0, ROBIN), ("robin-2", 20, ROBIN), ("unknown-1", 50, None))
    assert await _visits() == 2

    await _name_by_analysis("unknown-1", ROBIN)

    assert await _visits() == 1
    assert await _visible_captures() == 3


@pytest.mark.asyncio
async def test_naming_an_unknown_bird_by_hand_joins_it_the_same_way():
    await _seed(("robin-1", 0, ROBIN), ("unknown-1", 30, None))
    assert await _visits() == 2

    await _name_by_owner("unknown-1", ROBIN)

    assert await _visits() == 1
    assert await _visible_captures() == 2


@pytest.mark.asyncio
async def test_an_unknown_bird_named_between_two_visits_joins_both():
    # 100 seconds apart, the two robin captures are two visits; the Unknown bird is within the gap of each.
    await _seed(("robin-1", 0, ROBIN), ("unknown-1", 50, None), ("robin-2", 100, ROBIN))
    assert await _visits() == 3

    await _name_by_analysis("unknown-1", ROBIN)

    assert await _visits() == 1
    assert await _visible_captures() == 3


@pytest.mark.asyncio
async def test_an_unknown_bird_named_with_no_visit_of_that_species_nearby_stays_its_own_visit():
    await _seed(("robin-1", 0, ROBIN), ("unknown-1", 30, None), ("dunnock-1", 600, "Prunella modularis"))
    assert await _visits() == 3

    # A different species, and the robin's visit is not the dunnock's.
    await _name_by_analysis("unknown-1", "Prunella modularis")

    assert await _visits() == 3
    assert await _visible_captures() == 3


# The day summary's Unknown subtotal ----------------------------------------------------------


@pytest.mark.asyncio
async def test_day_summary_says_how_many_visits_are_unknown_birds_and_counts_the_fold():
    await _seed(("robin-1", 0, ROBIN), ("robin-2", 20, ROBIN), ("unknown-1", 50, None), ("unknown-2", 900, None))

    before = await _summary()
    await _name_by_analysis("unknown-1", ROBIN)
    after = await _summary()

    assert (*_counts(before), before["unresolved_count"]) == (3, 2, 2)
    # The named capture joined the robin's visit; every capture is still counted.
    assert (*_counts(after), after["unresolved_count"]) == (2, 1, 1)
    assert before["total_count"] == after["total_count"] == 4


@pytest.mark.asyncio
async def test_the_unknown_subtotal_and_visits_are_read_together_while_a_batch_names_birds(monkeypatch):
    # One robin visit with two Unknown birds beside it. The batch names one before the visits are
    # read and the other after, while the summary is still being assembled.
    await _seed(("robin-1", 0, ROBIN), ("unknown-1", 20, None), ("unknown-2", 40, None))
    hourly = DetectionRepository.get_timebucket_counts_hourly
    latest = DetectionRepository.get_all

    async def batch_names_the_first(self, *args, **kwargs):
        await _name_by_analysis("unknown-1", ROBIN)
        return await hourly(self, *args, **kwargs)

    async def batch_names_the_second(self, *args, **kwargs):
        await _name_by_analysis("unknown-2", ROBIN)
        return await latest(self, *args, **kwargs)

    monkeypatch.setattr(DetectionRepository, "get_timebucket_counts_hourly", batch_names_the_first)
    monkeypatch.setattr(DetectionRepository, "get_all", batch_names_the_second)

    body = await _summary()

    # Visits, the Unknown birds and every species row describe one moment: after the first naming,
    # before the second. One robin visit holding two captures, and one Unknown bird.
    assert _counts(body) == (2, 1)
    assert _rows(body) == {"Erithacus rubecula": (1, 2, "unknown-1"), "Unknown Bird": (1, 1, "unknown-2")}


@pytest.mark.asyncio
async def test_each_visit_is_judged_unknown_by_its_own_capture_not_by_its_species_latest_label():
    # An Unknown capture that kept a robin's scientific name, and a named robin later: two visits,
    # and the earlier one is an Unknown bird whatever the robin's latest label says.
    await _seed_rows(
        ("unknown-kept-name", START, UNKNOWN, ROBIN, 0),
        ("robin-later", START + timedelta(minutes=5), "European Robin", ROBIN, 0),
    )

    body = await _summary()
    assert _counts(body) == (2, 1)
    # The robin keeps its own visit and the Unknown bird is listed once, apart from it.
    assert _rows(body) == {"European Robin": (1, 1, "robin-later"), "Unknown Bird": (1, 1, "unknown-kept-name")}


@pytest.mark.asyncio
@pytest.mark.parametrize("unknown_first", [True, False], ids=["unknown-earlier", "unknown-later"])
async def test_an_unknown_bird_that_kept_a_species_catalogue_id_never_shares_that_species_row(unknown_first):
    # A legacy Unknown capture that still carries a robin's catalogue id and scientific name, beside
    # three robin visits. In either order every visit is counted once: the robin keeps its three
    # visits and stays in the list (so the Species figure does not change), and the Unknown bird is
    # one visit of its own.
    robin_offsets = [5, 10, 15] if unknown_first else [0, 5, 10]
    unknown_offset = 0 if unknown_first else 15
    for index, minutes in enumerate(robin_offsets):
        await _seed_capture(
            f"robin-{index}", START + timedelta(minutes=minutes), "European Robin", scientific=ROBIN, species_id=42
        )
    await _seed_capture(
        "unknown-kept-id", START + timedelta(minutes=unknown_offset), UNKNOWN, scientific=ROBIN, species_id=42
    )

    body = await _summary()

    assert _counts(body) == (4, 1)
    assert _rows(body) == {"European Robin": (3, 3, "robin-2"), "Unknown Bird": (1, 1, "unknown-kept-id")}
    assert len(body["top_species"]) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("display", "category"),
    [("European Robin", UNKNOWN), ("", UNKNOWN), ("", "")],
    ids=["unknown-category", "blank-display", "blank-labels"],
)
async def test_a_capture_the_dashboard_shows_as_unknown_bird_is_an_unknown_visit(display, category):
    # Older rows can keep a species name beside an Unknown category, or no display name at all. The
    # Dashboard shows each as Unknown bird, so it is counted as one, and not under the robin.
    await _seed_capture("robin-1", START, "European Robin", scientific=ROBIN, species_id=42)
    await _seed_capture(
        "legacy-unknown", START + timedelta(minutes=5), display, category=category, scientific=ROBIN, species_id=42
    )

    body = await _summary()

    assert _counts(body) == (2, 1)
    assert _rows(body) == {"European Robin": (1, 1, "robin-1"), "Unknown Bird": (1, 1, "legacy-unknown")}
    assert body["latest_detection"]["display_name"] == "Unknown Bird"


@pytest.mark.asyncio
async def test_a_legacy_group_label_is_one_unknown_visit_everywhere_on_the_dashboard():
    # Older models named some birds by group. The Dashboard shows them as Unknown bird, and the visit
    # rule groups them like a species: two captures within the gap are one visit, Unknown in every total.
    group = "Great tit and allies"
    await _seed_rows(
        ("group-1", START, group, group, 0),
        ("group-2", START + timedelta(seconds=30), group, group, 0),
    )

    body = await _summary()

    assert _counts(body) == (1, 1)
    assert _unknown_row(body)["count"] == 2


@pytest.mark.asyncio
async def test_group_labels_and_ordinary_unknown_birds_give_one_unknown_total():
    # Two group-label captures in one visit and one ordinary Unknown bird: two Unknown visits, three
    # captures, under Visits and in Top visitors alike.
    group = "Great tit and allies"
    await _seed_rows(
        ("group-1", START, group, group, 0),
        ("group-2", START + timedelta(seconds=30), group, group, 0),
        ("unknown-1", START + timedelta(minutes=10), UNKNOWN, None, 0),
    )

    body = await _summary()

    assert _counts(body) == (2, 2)
    row = _unknown_row(body)
    assert row["count"] == 3
    assert row["latest_event"] == "unknown-1"


@pytest.mark.asyncio
async def test_an_unknown_bird_added_by_hand_is_an_unknown_visit_too():
    await _seed_rows(("manual_unknown", START, UNKNOWN, None, 0))

    assert _counts(await _summary()) == (1, 1)


@pytest.mark.asyncio
async def test_the_unknown_subtotal_counts_only_visible_unknown_birds_inside_the_window():
    await _seed_rows(
        ("robin-today", NOW - timedelta(hours=2), "European Robin", ROBIN, 0),
        ("unknown-today", NOW - timedelta(hours=1), UNKNOWN, None, 0),
        ("unknown-hidden", NOW - timedelta(minutes=30), UNKNOWN, None, 1),
        # Yesterday evening: inside the last 24 hours, before today's midnight.
        ("unknown-yesterday", NOW - timedelta(hours=20), UNKNOWN, None, 0),
        # Older than the last 24 hours.
        ("unknown-older", NOW - timedelta(hours=30), UNKNOWN, None, 0),
    )

    assert _counts(await _summary()) == (3, 2)
    assert _counts(await _summary("?window=today", None)) == (2, 1)


@pytest.mark.asyncio
async def test_a_guest_unknown_subtotal_respects_the_shared_history(monkeypatch):
    # Only today (UTC) is shared, so yesterday evening's Unknown bird is outside a guest's window.
    monkeypatch.setattr(settings.public_access, "enabled", True)
    monkeypatch.setattr(settings.public_access, "historical_days_mode", "custom")
    monkeypatch.setattr(settings.public_access, "show_historical_days", 0)
    await _seed_rows(
        ("robin-today", NOW - timedelta(hours=2), "European Robin", ROBIN, 0),
        ("unknown-today", NOW - timedelta(hours=1), UNKNOWN, None, 0),
        ("unknown-yesterday", NOW - timedelta(hours=20), UNKNOWN, None, 0),
    )

    owner = await _summary()
    guest = await _summary(headers={})

    assert _counts(owner) == (3, 2)
    assert _counts(guest) == (2, 1)


# Round 4: the species list stays what it was before the single read ---------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("window", ["", "?window=today"], ids=["last-24-hours", "today"])
async def test_captures_stored_in_mixed_time_formats_are_read_as_one_clock(window):
    # An older row keeps an explicit UTC offset; a newer one is naive UTC. Twenty seconds apart on one
    # camera they are one robin visit, and the later one is the newest.
    await _seed_capture(
        "robin-offset",
        START,
        "European Robin",
        scientific=ROBIN,
        species_id=42,
        stored_time="2035-06-14 17:00:00+00:00",
    )
    await _seed_capture(
        "robin-naive", START, "European Robin", scientific=ROBIN, species_id=42, stored_time="2035-06-14 17:00:20"
    )
    # And as separate visits on two cameras, opened in either format.
    await _seed_capture(
        "dunnock-offset",
        START,
        "Dunnock",
        scientific="Prunella modularis",
        species_id=7,
        camera="patiocam",
        stored_time="2035-06-14 17:10:00+00:00",
    )
    await _seed_capture(
        "dunnock-naive",
        START,
        "Dunnock",
        scientific="Prunella modularis",
        species_id=7,
        camera="feedercam",
        stored_time="2035-06-14 17:05:00",
    )

    body = await _summary(window)

    assert _counts(body) == (3, 0)
    assert _rows(body) == {"European Robin": (1, 2, "robin-naive"), "Dunnock": (2, 2, "dunnock-offset")}


@pytest.mark.asyncio
async def test_a_bird_stored_under_two_keys_keeps_the_name_of_its_fuller_record():
    # One older robin capture has only a taxon; two later ones carry the catalogue id too. They are one
    # bird in the list, named as its catalogue records name it.
    await _seed_capture("robin-taxon", START, "Robin", scientific=ROBIN, common="Robin", taxa_id=424242)
    for index, minutes in enumerate((5, 10)):
        await _seed_capture(
            f"robin-{index}",
            START + timedelta(minutes=minutes),
            "European Robin",
            scientific=ROBIN,
            common="European Robin",
            species_id=42,
            taxa_id=424242,
        )

    body = await _summary()

    assert _counts(body) == (3, 0)
    [row] = body["top_species"]
    assert (row["species"], row["common_name"], row["taxa_id"]) == ("European Robin", "European Robin", 424242)
    assert (row["visit_count"], row["count"], row["latest_event"]) == (3, 3, "robin-1")


@pytest.mark.asyncio
async def test_species_with_equal_counts_keep_a_fixed_order():
    # Four species ahead, then a blackbird and a robin tied on visits and captures: the tie is broken
    # by catalogue key, so the same bird is fifth on every read.
    ahead = [
        ("Dunnock", "Prunella modularis", 11),
        ("Wren", "Troglodytes troglodytes", 12),
        ("Great Tit", "Parus major", 13),
        ("Blue Tit", "Cyanistes caeruleus", 14),
    ]
    for index, (name, scientific, species_id) in enumerate(ahead):
        for visit in range(3):
            await _seed_capture(
                f"{species_id}-{visit}",
                START + timedelta(minutes=index * 10 + visit * 2),
                name,
                scientific=scientific,
                species_id=species_id,
            )
    for visit in range(2):
        await _seed_capture(
            f"robin-{visit}",
            START + timedelta(minutes=45 + visit * 2),
            "European Robin",
            scientific=ROBIN,
            species_id=21,
        )
        await _seed_capture(
            f"blackbird-{visit}",
            START + timedelta(minutes=50 + visit * 2),
            "Eurasian Blackbird",
            scientific="Turdus merula",
            species_id=19,
        )

    body = await _summary()

    # The robin is seen first, but the blackbird's catalogue key sorts first, as it always has.
    assert [row["species"] for row in body["top_species"]][4:] == ["Eurasian Blackbird", "European Robin"]


@pytest.mark.asyncio
@pytest.mark.parametrize("named_first", [True, False], ids=["named-first", "group-label-first"])
async def test_a_group_label_inside_a_visit_never_renames_the_species_row(named_first):
    # A great tit and a legacy "Great tit and allies" capture that kept its catalogue id, 15 seconds
    # apart on one camera: one visit. Opened by the great tit, it is a Great Tit visit whose newest
    # capture is the group-label one; opened by the group label, it is an Unknown bird visit.
    first, second = (("tit", "Great Tit"), ("group", "Great tit and allies"))
    if not named_first:
        first, second = second, first
    await _seed_capture(first[0], START, first[1], scientific="Parus major", species_id=13)
    await _seed_capture(second[0], START + timedelta(seconds=15), second[1], scientific="Parus major", species_id=13)
    await _seed_capture("unknown-1", START + timedelta(minutes=10), UNKNOWN)

    body = await _summary()

    if named_first:
        assert _counts(body) == (2, 1)
        assert _rows(body) == {"Great Tit": (1, 2, "group"), "Unknown Bird": (1, 1, "unknown-1")}
    else:
        assert _counts(body) == (2, 2)
        assert _rows(body) == {"Unknown Bird": (2, 3, "unknown-1")}


# Species rows as dev builds them ---------------------------------------------------------------
# Named rows keep dev's raw catalogue-key buckets, order and alias merge exactly; only the captures
# of Unknown visits leave them. Every test in this section also passes against dev.


@pytest.mark.asyncio
@pytest.mark.parametrize("hand_added", [True, False], ids=["with-hand-added-alias", "camera-only"])
async def test_a_newer_capture_with_incomplete_taxonomy_never_splits_or_strips_the_bird(hand_added):
    # Two robin visits with every id, an optional hand-added "Robin" with only the taxon, then the
    # newest robin with only its scientific name: one row, the taxon kept, the newest event shown.
    for index, minutes in enumerate((0, 5)):
        await _seed_capture(
            f"robin-full-{index}",
            START + timedelta(minutes=minutes),
            "European Robin",
            scientific=ROBIN,
            common="European Robin",
            species_id=42,
            taxa_id=424242,
        )
    if hand_added:
        await _seed_capture(
            "manual_robin", START + timedelta(minutes=10), "Robin", scientific=ROBIN, common="Robin", taxa_id=424242
        )
    await _seed_capture(
        "robin-newest", START + timedelta(minutes=15), "European Robin", scientific=ROBIN, no_common=True
    )

    body = await _summary()

    visits = 4 if hand_added else 3
    assert _counts(body) == (visits, 0)
    [row] = body["top_species"]
    assert (row["species"], row["taxa_id"]) == ("European Robin", 424242)
    assert (row["visit_count"], row["count"], row["latest_event"]) == (visits, visits, "robin-newest")


@pytest.mark.asyncio
@pytest.mark.parametrize("hand_added", [True, False], ids=["hand-added", "camera"])
async def test_an_alias_seen_last_keeps_the_fuller_records_name(hand_added):
    # Two robin visits with every id, then a later "Robin" with only the taxon: the row keeps the
    # fuller records' name, and its newest event is the later capture.
    for index, minutes in enumerate((0, 5)):
        await _seed_capture(
            f"robin-full-{index}",
            START + timedelta(minutes=minutes),
            "European Robin",
            scientific=ROBIN,
            common="European Robin",
            species_id=42,
            taxa_id=424242,
        )
    later = "manual_robin" if hand_added else "robin-taxon"
    await _seed_capture(later, START + timedelta(minutes=10), "Robin", scientific=ROBIN, common="Robin", taxa_id=424242)

    body = await _summary()

    assert _counts(body) == (3, 0)
    [row] = body["top_species"]
    assert (row["species"], row["common_name"], row["taxa_id"]) == ("European Robin", "European Robin", 424242)
    assert (row["visit_count"], row["count"], row["latest_event"]) == (3, 3, later)


@pytest.mark.asyncio
async def test_a_tie_with_a_partly_identified_bird_keeps_the_fifth_place_dev_gives():
    # Four species ahead; two robin visits with catalogue id 21; two blackbird visits, one with id 19
    # and one with only its names. The robin is fifth, as it always was.
    ahead = [
        ("Dunnock", "Prunella modularis", 11),
        ("Wren", "Troglodytes troglodytes", 12),
        ("Great Tit", "Parus major", 13),
        ("Blue Tit", "Cyanistes caeruleus", 14),
    ]
    for index, (name, scientific, species_id) in enumerate(ahead):
        for visit in range(3):
            await _seed_capture(
                f"{species_id}-{visit}",
                START + timedelta(minutes=index * 10 + visit * 2),
                name,
                scientific=scientific,
                species_id=species_id,
            )
    for visit in range(2):
        await _seed_capture(
            f"robin-{visit}",
            START + timedelta(minutes=45 + visit * 2),
            "European Robin",
            scientific=ROBIN,
            species_id=21,
        )
    await _seed_capture(
        "blackbird-id", START + timedelta(minutes=50), "Eurasian Blackbird", scientific="Turdus merula", species_id=19
    )
    await _seed_capture(
        "blackbird-names", START + timedelta(minutes=52), "Eurasian Blackbird", scientific="Turdus merula"
    )

    body = await _summary()

    assert [row["species"] for row in body["top_species"]][4:] == ["European Robin", "Eurasian Blackbird"]


# Round 6: a capture shown as Unknown bird inside a named visit -----------------------------------

WINDOWS = pytest.mark.parametrize("window", ["", "?window=today"], ids=["last-24-hours", "today"])


@pytest.mark.asyncio
@WINDOWS
async def test_a_group_label_continuing_a_named_visit_under_its_own_key_adds_no_species(window):
    # A great tit with its catalogue id, then a "Great tit and allies" capture a second later with only
    # the scientific name: one Great Tit visit. The group label joins the great tit's row and photo; it
    # never becomes a row of its own or an extra species.
    await _seed_capture("tit", START, "Great Tit", scientific="Parus major", species_id=13)
    await _seed_capture("group", START + timedelta(seconds=1), "Great tit and allies", scientific="Parus major")
    await _seed_capture("unknown-1", START + timedelta(minutes=10), UNKNOWN)

    body = await _summary(window)

    assert _counts(body) == (2, 1)
    assert _rows(body) == {"Great Tit": (1, 2, "group"), "Unknown Bird": (1, 1, "unknown-1")}


@pytest.mark.asyncio
@WINDOWS
async def test_a_group_label_opening_the_pair_keeps_the_whole_visit_under_unknown_bird(window):
    await _seed_capture("group", START, "Great tit and allies", scientific="Parus major")
    await _seed_capture("tit", START + timedelta(seconds=1), "Great Tit", scientific="Parus major", species_id=13)
    await _seed_capture("unknown-1", START + timedelta(minutes=10), UNKNOWN)

    body = await _summary(window)

    assert _counts(body) == (2, 2)
    assert _rows(body) == {"Unknown Bird": (2, 3, "unknown-1")}


@pytest.mark.asyncio
@WINDOWS
async def test_an_unknown_capture_never_lends_its_taxon_to_the_named_row(window):
    # A named robin without a taxon, then a capture 15 seconds later in its visit that is shown as
    # Unknown bird (an Unknown category) and carries taxon 313131 under its own key. The robin's row
    # takes the later photo but never that taxon, so its link never opens taxon 313131.
    await _seed_capture("robin", START, "European Robin", scientific=ROBIN, species_id=42)
    await _seed_capture(
        "robin-unknown-category",
        START + timedelta(seconds=15),
        "European Robin",
        category=UNKNOWN,
        scientific=ROBIN,
        taxa_id=313131,
    )

    body = await _summary(window)

    assert _counts(body) == (1, 0)
    [row] = body["top_species"]
    assert (row["species"], row["taxa_id"]) == ("European Robin", None)
    assert (row["visit_count"], row["count"], row["latest_event"]) == (1, 2, "robin-unknown-category")
