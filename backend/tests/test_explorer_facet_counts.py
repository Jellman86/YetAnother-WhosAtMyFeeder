"""The Explorer's facet counts count what choosing the facet would show (#1097).

A tester chose Today and saw every species counted over all time, and switching to Visits changed
nothing. A count beside a filter is a claim about the results that filter gives, so it follows the
period, the Visits or Captures choice, and the other filters in the rail.
"""

from datetime import datetime, timedelta

import httpx
import pytest
import pytest_asyncio

from app.auth import AuthContext, get_auth_context_with_legacy
from app.config import settings
from app.database import close_db, get_db, init_db
from app.main import app
from app.routers.events import UNKNOWN_BIRD_FILTER_ALIAS, _event_filters_cache
from app.utils import public_access

TODAY = datetime(2033, 10, 3)
YESTERDAY = TODAY - timedelta(days=1)
TODAY_WINDOW = {"start_time": "2033-10-03T00:00:00Z", "end_time": "2033-10-03T23:59:59.999Z"}
BLACKBIRD = "taxa:12716"
ROBIN = "taxa:13094"


@pytest.fixture(autouse=True)
def offline_taxonomy(monkeypatch):
    from app.services.taxonomy import taxonomy_service as ts_module

    async def unavailable(self, name):
        raise ts_module.TaxonomyLookupUnavailable(name)

    monkeypatch.setattr(ts_module.TaxonomyService, "_lookup_inaturalist", unavailable)


@pytest_asyncio.fixture(autouse=True)
async def history(migrated_history_db, monkeypatch):
    # A private database: these counts cover the whole history, and nothing here reaches later tests.
    monkeypatch.setenv("DB_PATH", str(migrated_history_db))
    monkeypatch.setattr(settings.auth, "enabled", False)
    monkeypatch.setattr(settings.public_access, "enabled", False)
    monkeypatch.setattr(settings.visits, "gap_seconds", 120)
    await init_db()
    _event_filters_cache.clear()
    try:
        # Blackbird: one visit of three captures and a later one today, one visit yesterday.
        await _capture("bb-1", TODAY.replace(hour=10))
        await _capture("bb-2", TODAY.replace(hour=10, second=30))
        await _capture("bb-3", TODAY.replace(hour=10, minute=1))
        await _capture("bb-4", TODAY.replace(hour=12), camera="patio")
        await _capture("bb-old", YESTERDAY.replace(hour=10), favourite=True)
        # Robin: one visit of two captures yesterday, nothing today.
        await _capture("rb-1", YESTERDAY.replace(hour=9), robin=True, audio=True)
        await _capture("rb-2", YESTERDAY.replace(hour=9, second=20), robin=True)
        await _capture("rb-hidden", TODAY.replace(hour=11), robin=True, hidden=True)
        yield
    finally:
        _event_filters_cache.clear()
        app.dependency_overrides.pop(get_auth_context_with_legacy, None)
        await close_db()


async def _capture(event, at, *, camera="birdcam", robin=False, hidden=False, favourite=False, audio=False):
    name, sci, taxa = (
        ("European Robin", "Erithacus rubecula", 13094) if robin else ("Blackbird", "Turdus merula", 12716)
    )
    await _record(event, at, name, sci=sci, common=name, taxa=taxa, camera=camera, hidden=hidden, audio=audio)
    if favourite:
        async with get_db() as db:
            await db.execute(
                "INSERT INTO detection_favorites (detection_id) SELECT id FROM detections WHERE frigate_event = ?",
                (event,),
            )
            await db.commit()


async def _record(
    event, at, display, *, sci=None, common=None, taxa=None, category=None, camera="birdcam", hidden=False, audio=False
):
    async with get_db() as db:
        await db.execute(
            """INSERT INTO detections (detection_time, detection_index, score, display_name, category_name,
                frigate_event, camera_name, is_hidden, manual_tagged, audio_confirmed,
                scientific_name, common_name, taxa_id)
            VALUES (?, 0, 0.9, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)""",
            (
                at.isoformat(sep=" "),
                display,
                category or display,
                event,
                camera,
                int(hidden),
                int(audio),
                sci,
                common,
                taxa,
            ),
        )
        await db.commit()


async def _cache_taxon(sci, common, taxa):
    async with get_db() as db:
        await db.execute(
            "INSERT OR REPLACE INTO taxonomy_cache (scientific_name, common_name, taxa_id) VALUES (?, ?, ?)",
            (sci, common, taxa),
        )
        await db.commit()


async def _shown(client, unit, params):
    """What choosing the filters in ``params`` shows, in ``unit``."""
    if unit == "visits":
        response = await client.get("/api/visits", params={**params, "limit": 1})
        assert response.status_code == 200, response.text
        return response.json()["total"]
    response = await client.get("/api/events/count", params=params)
    assert response.status_code == 200, response.text
    return response.json()["count"]


async def _assert_every_species_count_is_shown(unit, **params):
    body = await _filters(**params, unit=unit)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        for option in body["species"]:
            shown = await _shown(client, unit, {**params, "species": option["value"]})
            assert option["count"] == shown, (unit, params, option)
    return body


async def _filters(**params):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/events/filters", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def _species_counts(body):
    return {option["value"]: option["count"] for option in body["species"]}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "window,unit,blackbird,robin",
    [
        ({}, "captures", 5, 2),
        ({}, "visits", 3, 1),
        (TODAY_WINDOW, "captures", 4, 0),
        (TODAY_WINDOW, "visits", 2, 0),
        ({"start_date": "2033-10-02", "end_date": "2033-10-02"}, "visits", 1, 1),
    ],
)
async def test_species_counts_follow_the_period_and_visits_or_captures(window, unit, blackbird, robin):
    body = await _filters(**window, unit=unit)

    assert body["unit"] == unit
    assert _species_counts(body) == {BLACKBIRD: blackbird, ROBIN: robin}


@pytest.mark.asyncio
async def test_visit_counts_report_the_gap_they_were_grouped_with():
    assert (await _filters(unit="visits"))["gap_seconds"] == 120
    assert (await _filters(unit="captures"))["gap_seconds"] is None


@pytest.mark.asyncio
async def test_without_a_unit_the_counts_stay_all_visible_captures():
    body = await _filters()

    assert body["unit"] == "captures"
    assert _species_counts(body) == {BLACKBIRD: 5, ROBIN: 2}
    assert body["camera_counts"] == {"birdcam": 6, "patio": 1}


@pytest.mark.asyncio
@pytest.mark.parametrize("unit", ["visits", "captures"])
@pytest.mark.parametrize("window", [{}, TODAY_WINDOW, {"camera": "patio"}, {"favorites": "true"}])
async def test_each_species_count_is_what_choosing_that_species_shows(unit, window):
    body = await _filters(**window, unit=unit)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        for option in body["species"]:
            params = {**window, "species": option["value"]}
            if unit == "visits":
                shown = (await client.get("/api/visits", params={**params, "limit": 1})).json()["total"]
            else:
                shown = (await client.get("/api/events/count", params=params)).json()["count"]
            assert option["count"] == shown, option


@pytest.mark.asyncio
async def test_species_counts_ignore_the_chosen_species_and_follow_the_camera():
    body = await _filters(**TODAY_WINDOW, unit="visits", species=BLACKBIRD, camera="patio")

    # Every species stays offered, counted as choosing it instead would show.
    assert _species_counts(body) == {BLACKBIRD: 1, ROBIN: 0}
    # The camera list follows the chosen species but not the chosen camera.
    assert body["camera_counts"] == {"birdcam": 1, "patio": 1}


@pytest.mark.asyncio
async def test_camera_counts_follow_the_period_and_unit():
    body = await _filters(**TODAY_WINDOW, unit="visits")

    assert body["camera_counts"] == {"birdcam": 1, "patio": 1}


@pytest.mark.asyncio
async def test_only_counts_follow_the_period_and_unit():
    all_time = await _filters(unit="visits")
    today = await _filters(**TODAY_WINDOW, unit="visits")

    assert all_time["totals"]["favorites"] == 1
    assert all_time["totals"]["audio_matched"] == 1
    assert all_time["totals"]["total"] == 4
    assert today["totals"] == {"total": 2, "favorites": 0, "audio_matched": 0, "video_analysed": 0, "hidden": 1}


@pytest.mark.asyncio
async def test_hidden_choice_counts_the_hidden_records_and_offers_their_species():
    body = await _filters(**TODAY_WINDOW, unit="captures", only_hidden="true")

    # Only the Robin was hidden, so the hidden view offers it alone.
    assert _species_counts(body) == {ROBIN: 1}


@pytest.mark.asyncio
async def test_guest_counts_keep_the_guest_history_window_and_never_count_hidden(monkeypatch):
    monkeypatch.setattr(settings.public_access, "enabled", True)
    monkeypatch.setattr(settings.public_access, "show_historical_days", 0)
    monkeypatch.setattr(settings.public_access, "historical_days_mode", "fixed")
    monkeypatch.setattr(public_access, "public_utc_day", lambda now=None: TODAY.date())
    app.dependency_overrides[get_auth_context_with_legacy] = lambda: AuthContext("guest")

    # Asking for all time, or for hidden records, reads only what a guest may see.
    for params in ({"unit": "captures"}, {"unit": "captures", "only_hidden": "true"}):
        body = await _filters(**params)
        assert _species_counts(body).get(BLACKBIRD) == 4, params
        assert _species_counts(body).get(ROBIN, 0) == 0, params
    today = await _filters(**TODAY_WINDOW, unit="visits")
    assert today["species"][0]["count"] == 2
    assert today["totals"]["hidden"] == 0


# The reviewers' reproductions: a count is the result of the option's own filter, whatever its records hold.


@pytest.mark.asyncio
@pytest.mark.parametrize("unit", ["visits", "captures"])
async def test_a_legacy_record_with_only_a_cached_taxon_counts_as_its_filter_finds_it(unit):
    await _cache_taxon("Turdus merula", "Blackbird", 12716)
    # A record from before taxon ids were stored, a visit of its own.
    await _record("bb-legacy", TODAY.replace(hour=15), "Blackbird", sci="Turdus merula")

    body = await _assert_every_species_count_is_shown(unit, **TODAY_WINDOW)
    # Visits match a stored taxon id only, so three visits; the capture count reads the cache too.
    assert _species_counts(body)[BLACKBIRD] == (2 if unit == "visits" else 5)
    if unit == "visits":
        all_time = await _assert_every_species_count_is_shown(unit)
        assert _species_counts(all_time)[BLACKBIRD] == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("unit", ["visits", "captures"])
async def test_unknown_bird_counts_every_record_its_filter_finds(unit):
    await _record("unknown-1", TODAY.replace(hour=16), "Unknown Bird")
    # Named as a species, but filed under Unknown Bird: the Unknown bird filter finds it too.
    await _record("named-unknown", TODAY.replace(hour=17), "Dunnock", sci="Prunella modularis", category="Unknown Bird")

    body = await _assert_every_species_count_is_shown(unit, **TODAY_WINDOW)
    assert _species_counts(body)[UNKNOWN_BIRD_FILTER_ALIAS] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("unit", ["visits", "captures"])
async def test_a_taxon_resolved_after_the_options_loaded_does_not_change_the_count(unit):
    await _record("tit-1", TODAY.replace(hour=18), "Blue Tit Label", sci="Cyanistes caeruleus")
    first = await _assert_every_species_count_is_shown(unit)
    assert _species_counts(first)["Blue Tit Label"] == 1

    # The options stay cached while the taxonomy learns the species' id; a new window counts again.
    await _cache_taxon("Cyanistes caeruleus", "Eurasian Blue Tit", 13270)
    again = await _assert_every_species_count_is_shown(unit, **TODAY_WINDOW)
    assert _species_counts(again)["Blue Tit Label"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("unit", ["visits", "captures"])
@pytest.mark.parametrize(
    "label,display,sci,common,taxa,cache",
    [
        ("parenthetical", "Eurasian Blue Tit (Cyanistes caeruleus)", None, None, None, None),
        (
            "sci-stored-cache-known",
            "Blue Tit Label",
            "Cyanistes caeruleus",
            None,
            None,
            ("Cyanistes caeruleus", "Eurasian Blue Tit", 13270),
        ),
        ("taxa-cache-conflict", "Conflict Bird", "Parus major", None, 999, ("Parus major", "Great Tit", 111)),
        ("accented", "Grünfink", None, None, None, None),
        ("display-is-common-name", "Great Tit", None, None, None, ("Parus major", "Great Tit", 111)),
    ],
)
async def test_counts_match_the_filter_for_awkward_labels(unit, label, display, sci, common, taxa, cache):
    if cache:
        await _cache_taxon(*cache)
    await _record(f"{label}-1", TODAY.replace(hour=19), display, sci=sci, common=common, taxa=taxa)
    await _record(
        f"{label}-2", TODAY.replace(hour=19, minute=30), display, sci=sci, common=common, taxa=taxa, camera="patio"
    )

    for params in ({}, TODAY_WINDOW, {"camera": "patio"}, {**TODAY_WINDOW, "favorites": "true"}):
        await _assert_every_species_count_is_shown(unit, **params)


@pytest.mark.asyncio
async def test_the_hidden_view_offers_the_species_and_cameras_only_hidden_records_hold():
    await _record(
        "gone-1",
        TODAY.replace(hour=20),
        "Hawfinch",
        sci="Coccothraustes coccothraustes",
        taxa=9083,
        camera="shed",
        hidden=True,
    )

    hidden = await _filters(unit="captures", only_hidden="true")
    assert _species_counts(hidden)["taxa:9083"] == 1
    assert "shed" in hidden["cameras"]
    assert hidden["camera_counts"]["shed"] == 1

    # The ordinary view does not offer what only hidden records hold.
    visible = await _filters(unit="captures")
    assert "taxa:9083" not in _species_counts(visible)
    assert "shed" not in visible["cameras"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "params",
    [
        {"unit": "frames"},
        {"start_date": "2033-02-30"},
        {"start_time": "2033-10-03T00:00:00"},
        {"start_time": "2033-10-04T00:00:00Z", "end_time": "2033-10-03T00:00:00Z"},
        {"taxon": "0"},
    ],
)
async def test_a_malformed_request_is_refused(params):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/events/filters", params=params)
    assert response.status_code in (400, 422), response.text


@pytest.mark.asyncio
async def test_a_guest_cannot_narrow_counts_by_what_is_not_shared_with_them(monkeypatch):
    monkeypatch.setattr(settings.public_access, "enabled", True)
    monkeypatch.setattr(settings.public_access, "show_historical_days", 7)
    monkeypatch.setattr(settings.public_access, "historical_days_mode", "fixed")
    monkeypatch.setattr(settings.public_access, "show_camera_names", False)
    monkeypatch.setattr(settings.public_access, "show_audio", False)
    monkeypatch.setattr(public_access, "public_utc_day", lambda now=None: TODAY.date())
    app.dependency_overrides[get_auth_context_with_legacy] = lambda: AuthContext("guest")

    plain = await _filters(unit="captures")
    narrowed = await _filters(
        unit="captures",
        camera="patio",
        audio_confirmed_only="true",
        owner_confirmed_only="true",
        multiple_species_only="true",
        only_hidden="true",
    )

    assert _species_counts(narrowed) == _species_counts(plain) == {BLACKBIRD: 5, ROBIN: 2}
    assert narrowed["cameras"] == [] and narrowed["camera_counts"] == {}
    assert narrowed["totals"]["audio_matched"] == 0 and narrowed["totals"]["hidden"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("unit", ["visits", "captures"])
async def test_one_request_reads_the_shared_history_work_once_per_window(unit, monkeypatch):
    from app.repositories.bird_observation_repository import BirdObservationRepository
    from app.repositories.visit_repository import VisitRepository

    evidence_reads: list[tuple] = []
    groupings: set[tuple] = set()
    read_evidence = BirdObservationRepository.multiple_species_events
    group = VisitRepository.grouping_cte

    async def counted_evidence(self, **kwargs):
        evidence_reads.append(tuple(sorted(kwargs.items())))
        return await read_evidence(self, **kwargs)

    async def counted_grouping(self, **kwargs):
        groupings.add((kwargs.get("camera"), kwargs.get("hidden_only")))
        return await group(self, **kwargs)

    monkeypatch.setattr(BirdObservationRepository, "multiple_species_events", counted_evidence)
    monkeypatch.setattr(VisitRepository, "grouping_cte", counted_grouping)

    await _filters(unit=unit, camera="patio", multiple_species_only="true")

    # Once for the visible records and once for the hidden ones, however many facets read them.
    assert len(evidence_reads) == 2
    if unit == "visits":
        # A chosen camera narrows each facet, not the grouping the camera list shares.
        assert groupings == {(None, False), (None, True)}


# Counts under a window or a filter are read with the results, from the history as it is.


async def _visits_shown(**params):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        return await _shown(client, "visits", params)


@pytest.mark.asyncio
async def test_hiding_a_record_today_updates_the_all_time_counts_kept_earlier():
    # Reproduction: All time, Today, hide, Today again, back to All time.
    assert _species_counts(await _filters(unit="visits"))[BLACKBIRD] == 3
    assert _species_counts(await _filters(unit="visits", **TODAY_WINDOW))[BLACKBIRD] == 2
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/events/bb-4/hide")
        assert response.status_code == 200, response.text
    assert _species_counts(await _filters(unit="visits", force_refresh="true", **TODAY_WINDOW))[BLACKBIRD] == 1

    all_time = await _filters(unit="visits")
    assert _species_counts(all_time)[BLACKBIRD] == 2 == await _visits_shown(species=BLACKBIRD)


@pytest.mark.asyncio
@pytest.mark.parametrize("unit", ["visits", "captures"])
async def test_a_capture_arriving_between_reads_is_counted_when_an_earlier_view_is_read_again(unit):
    # Reproduction: a window read, a new capture in it, the same window read again.
    before = _species_counts(await _filters(unit=unit, **TODAY_WINDOW))[BLACKBIRD]
    await _filters(unit=unit, camera="patio", **TODAY_WINDOW)
    await _capture("bb-late", TODAY.replace(hour=22))

    again = await _assert_every_species_count_is_shown(unit, **TODAY_WINDOW)
    assert _species_counts(again)[BLACKBIRD] == before + 1


@pytest.mark.asyncio
@pytest.mark.parametrize("unit", ["visits", "captures"])
async def test_a_write_committed_by_another_connection_is_in_the_next_read(unit):
    import sqlite3

    from app.database import _get_db_path

    before = _species_counts(await _filters(unit=unit, **TODAY_WINDOW))[BLACKBIRD]
    # Committed outside the application's pool: nothing in the application is told of it.
    with sqlite3.connect(_get_db_path()) as db:
        db.execute("UPDATE detections SET is_hidden = 1 WHERE frigate_event = 'bb-4'")

    after = await _assert_every_species_count_is_shown(unit, **TODAY_WINDOW)
    assert _species_counts(after)[BLACKBIRD] == before - 1


@pytest.mark.asyncio
async def test_a_scoped_answer_is_counted_afresh_every_time(monkeypatch):
    from app.repositories.explorer_facet_repository import ExplorerFacetRepository

    calls = 0
    count = ExplorerFacetRepository.facet_counts

    async def counted(self, *args, **kwargs):
        nonlocal calls
        calls += 1
        return await count(self, *args, **kwargs)

    monkeypatch.setattr(ExplorerFacetRepository, "facet_counts", counted)
    for params in ({"unit": "visits", **TODAY_WINDOW}, {"unit": "captures"}):
        await _filters(**params)
        await _filters(**params)
    assert calls == 4
    # Only the request with no unit, window or filter is kept for a minute, as it always was.
    await _filters()
    await _filters()
    assert calls == 5


@pytest.mark.asyncio
async def test_a_read_started_before_a_refresh_never_restores_what_the_refresh_replaced(monkeypatch):
    import asyncio
    import sqlite3

    from app.database import _get_db_path
    from app.repositories.explorer_facet_repository import ExplorerFacetRepository

    counted_old = asyncio.Event()
    release_old = asyncio.Event()
    count = ExplorerFacetRepository.facet_counts
    held = True

    async def held_after_counting(self, *args, **kwargs):
        nonlocal held
        result = await count(self, *args, **kwargs)
        if held:
            held = False
            counted_old.set()
            await release_old.wait()
        return result

    monkeypatch.setattr(ExplorerFacetRepository, "facet_counts", held_after_counting)
    # The request with no window or filter is the one kept; this one counts, then waits.
    old = asyncio.create_task(_filters())
    await counted_old.wait()
    with sqlite3.connect(_get_db_path()) as db:
        db.execute("UPDATE detections SET is_hidden = 1 WHERE frigate_event = 'bb-1'")
    refreshed = await _filters(force_refresh="true")
    release_old.set()
    stale = await old

    assert _species_counts(stale)[BLACKBIRD] == _species_counts(refreshed)[BLACKBIRD] + 1
    assert await _filters() == refreshed


@pytest.mark.asyncio
@pytest.mark.parametrize("unit", ["visits", "captures"])
@pytest.mark.parametrize("stored", ["Épervier d'Europe", "épervier d'europe"])
@pytest.mark.parametrize("first", ["upper", "lower"])
async def test_an_accented_name_counts_what_its_filter_finds_in_either_query_order(unit, stored, first):
    from app.repositories.detection_repository import clear_species_alias_cache

    await _record("accent-1", TODAY.replace(hour=21), stored)
    clear_species_alias_cache()
    spellings = {"upper": "Épervier d'Europe", "lower": "épervier d'europe"}
    queries = [spellings[first], spellings["lower" if first == "upper" else "upper"]]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        for query in queries:
            # A query in either spelling, then the option itself: each count is what its filter finds.
            await _shown(client, unit, {**TODAY_WINDOW, "species": query})
            body = await _filters(unit=unit, **TODAY_WINDOW)
            assert _species_counts(body)[stored] == await _shown(client, unit, {**TODAY_WINDOW, "species": stored})


@pytest.mark.asyncio
async def test_an_uppercase_query_finds_a_lowercase_accented_name_as_before():
    from app.repositories.detection_repository import clear_species_alias_cache

    # The case rule is unchanged: a query is lowered by Python, the stored name by SQLite.
    await _record("accent-lower", TODAY.replace(hour=21), "épervier d'europe")
    clear_species_alias_cache()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert await _shown(client, "captures", {"species": "Épervier d'Europe"}) == 1


@pytest.mark.asyncio
async def test_a_kept_answer_expires_no_later_than_the_option_list_it_was_built_from(monkeypatch):
    import sqlite3

    from app.database import _get_db_path
    from app.routers import events

    clock = [1000.0]
    monkeypatch.setattr(events, "_monotonic", lambda: clock[0])
    # The option list is read and kept by a scoped request.
    await _filters(unit="visits")
    # Near the end of the list's minute, the request with no filters is answered from that list.
    clock[0] += 50
    await _filters()
    with sqlite3.connect(_get_db_path()) as db:
        db.execute(
            """INSERT INTO detections (detection_time, detection_index, score, display_name, category_name,
                frigate_event, camera_name, scientific_name, common_name, taxa_id)
            VALUES ('2033-10-03 22:00:00', 0, 0.9, 'Dunnock', 'Dunnock', 'dn-1', 'birdcam',
                'Prunella modularis', 'Dunnock', 13858)"""
        )

    # Once the list's minute is over, the answer built from it is over too.
    clock[0] += 15
    assert "taxa:13858" in _species_counts(await _filters())


@pytest.mark.asyncio
@pytest.mark.parametrize("unit", ["visits", "captures"])
async def test_a_camera_the_counts_find_is_offered_even_before_the_option_list_knows_it(unit):
    import sqlite3

    from app.database import _get_db_path

    first = await _filters(unit=unit)
    assert "shed" not in first["cameras"]
    with sqlite3.connect(_get_db_path()) as db:
        db.execute(
            """INSERT INTO detections (detection_time, detection_index, score, display_name, category_name,
                frigate_event, camera_name, scientific_name, common_name, taxa_id)
            VALUES ('2033-10-03 22:00:00', 0, 0.9, 'Blackbird', 'Blackbird', 'shed-1', 'shed',
                'Turdus merula', 'Blackbird', 12716)"""
        )

    today = await _filters(unit=unit, **TODAY_WINDOW)
    assert today["camera_counts"]["shed"] == 1
    assert "shed" in today["cameras"]
    # A camera with nothing in the period stays offered, as the kept list has it.
    assert "patio" in today["cameras"] and "birdcam" in today["cameras"]
