"""The Explorer's owner-only Owner confirmed filter, in visits and in captures."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio

from app.database import close_db, get_db, init_db
from app.repositories.visit_repository import VisitRepository
from app.utils.owner_confirmation import is_owner_confirmed


START = datetime(2034, 4, 9, 9, 15, 0)
WINDOW_END = START + timedelta(hours=1)
DAY = "start_date=2034-04-09&end_date=2034-04-09"


@pytest_asyncio.fixture
async def repo():
    await init_db()
    async with get_db() as db:
        await db.execute("DELETE FROM detections WHERE frigate_event LIKE 'confirmed-test-%'")
        await db.commit()
        yield VisitRepository(db)
        await db.execute("DELETE FROM detections WHERE frigate_event LIKE 'confirmed-test-%'")
        await db.commit()
    await close_db()


async def capture(
    repo,
    number,
    seconds,
    *,
    species="Turdus merula",
    category=None,
    manual=False,
    hidden=0,
    favorite=False,
    camera="birdcam",
):
    event = f"confirmed-test-{number}"
    cursor = await repo.db.execute(
        """INSERT INTO detections (detection_time, detection_index, score, display_name,
        category_name, frigate_event, camera_name, scientific_name, is_hidden, manual_tagged)
        VALUES (?, 0, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            (START + timedelta(seconds=seconds)).isoformat(sep=" "),
            0.7 + number / 1000,
            species,
            species if category is None else category,
            event,
            camera,
            species,
            hidden,
            int(manual),
        ),
    )
    if favorite:
        await repo.db.execute("INSERT INTO detection_favorites (detection_id) VALUES (?)", (cursor.lastrowid,))
    await repo.db.commit()
    return event


def window(**kwargs):
    return {"start": START, "end": WINDOW_END, **kwargs}


def capture_window(**kwargs):
    return {"start_date": START, "end_date": WINDOW_END, **kwargs}


@pytest.mark.asyncio
async def test_sql_rule_matches_the_badge_rule_for_every_label(repo):
    labels = [
        ("Turdus merula", None),
        ("Unknown Bird", None),
        ("unknown bird ", None),
        ("Background", None),
        ("Turdus merula", "background"),
        ("Thrushes and allies", None),
        ("Life", None),
        ("", "Turdus merula"),
    ]
    # Each label on its own camera, so no two captures share a visit.
    for number, (species, category) in enumerate(labels):
        await capture(
            repo, number, number * 600, species=species, category=category, manual=True, camera=f"cam{number}"
        )
    await capture(repo, 50, 30, manual=False, camera="cam-model")
    expected = {
        f"confirmed-test-{number}"
        for number, (species, category) in enumerate(labels)
        if is_owner_confirmed(True, species, species if category is None else category)
    }
    assert expected == {"confirmed-test-0"}
    end = START + timedelta(hours=2)
    listed = await repo.get_all(start_date=START, end_date=end, owner_confirmed_only=True)
    assert {row.frigate_event for row in listed} == expected
    assert await repo.get_count(start_date=START, end_date=end, owner_confirmed_only=True) == len(expected)
    headers, total = await repo.list_visits(start=START, end=end, owner_confirmed_only=True)
    assert total == len(expected)
    assert {header["visit_id"] for header in headers} == expected


# Labels the presenter shows as Unknown Bird only after collapsing whitespace and casefolding.
SPACED_UNKNOWN_LABELS = [
    ("Unknown  Bird", None),
    ("Turdus merula", "Unknown\tBird"),
    ("Thrushes and\tallies", None),
    ("Turdus merula", "Thrushes and\tallies"),
    ("UNKNOWN\u00a0BIRD", None),
]


@pytest.mark.asyncio
async def test_unknown_labels_with_odd_spacing_confirm_nothing_in_any_read(repo):
    for number, (species, category) in enumerate(SPACED_UNKNOWN_LABELS):
        await capture(
            repo, number, number * 600, species=species, category=category, manual=True, camera=f"cam{number}"
        )
    named = await capture(repo, 40, 30, manual=True, camera="cam-named")
    end = START + timedelta(hours=2)
    assert [
        row.frigate_event for row in await repo.get_all(start_date=START, end_date=end, owner_confirmed_only=True)
    ] == [named]
    assert await repo.get_count(start_date=START, end_date=end, owner_confirmed_only=True) == 1
    headers, total = await repo.list_visits(start=START, end=end, owner_confirmed_only=True)
    assert total == 1
    assert [header["visit_id"] for header in headers] == [named]
    unfiltered, _ = await repo.list_visits(start=START, end=end)
    assert {header["visit_id"] for header in unfiltered if header["owner_confirmed"]} == {named}


@pytest.mark.asyncio
async def test_odd_spacing_unknown_labels_are_left_out_of_each_api_read(repo, monkeypatch):
    from app.main import app

    headers = await birds_present(monkeypatch, owner=True)
    for number, (species, category) in enumerate(SPACED_UNKNOWN_LABELS):
        await capture(
            repo, number, number * 600, species=species, category=category, manual=True, camera=f"cam{number}"
        )
    named = await capture(repo, 40, 30, manual=True, camera="cam-named")
    window_query = "start_date=2034-04-09&end_date=2034-04-09&owner_confirmed_only=true"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test", headers=headers
    ) as client:
        listed = await client.get(f"/api/events?{window_query}")
        assert [row["frigate_event"] for row in listed.json()] == [named]
        counted = await client.get(f"/api/events/count?{window_query}")
        assert counted.json()["count"] == 1
        visits = await client.get(f"/api/visits?{window_query}")
        assert [visit["visit_id"] for visit in visits.json()["visits"]] == [named]
        everything = await client.get("/api/visits?start_date=2034-04-09&end_date=2034-04-09")
        badges = {visit["visit_id"] for visit in everything.json()["visits"] if visit["owner_confirmed"]}
        assert badges == {named}


@pytest.mark.asyncio
async def test_a_visit_matches_on_one_confirmed_capture_and_expands_to_all_of_them(repo):
    first = await capture(repo, 0, 0)
    await capture(repo, 1, 20, manual=True)
    await capture(repo, 2, 40)
    await capture(repo, 3, 600, species="Erithacus rubecula")
    headers, total = await repo.list_visits(**window(owner_confirmed_only=True))
    assert total == 1
    assert headers[0]["visit_id"] == first
    assert headers[0]["capture_count"] == 3
    assert headers[0]["owner_confirmed"] == 1
    captures, count = await repo.visit_captures(first, start=START, end=WINDOW_END)
    assert count == 3
    assert [row.frigate_event for row in captures] == [first, "confirmed-test-1", "confirmed-test-2"]


@pytest.mark.asyncio
@pytest.mark.parametrize("where", ["hidden", "before_window"])
async def test_a_confirmation_outside_the_view_does_not_make_a_visit_match(repo, where):
    seconds = -120 if where == "before_window" else 10
    await capture(repo, 0, seconds, manual=True, hidden=int(where == "hidden"))
    await capture(repo, 1, 20)
    headers, total = await repo.list_visits(**window(owner_confirmed_only=True))
    assert (headers, total) == ([], 0)
    unfiltered, _ = await repo.list_visits(**window())
    assert all(not header["owner_confirmed"] for header in unfiltered)


@pytest.mark.asyncio
async def test_tagging_a_capture_unknown_confirms_nothing(repo):
    await capture(repo, 0, 0, species="Unknown Bird", manual=True)
    assert (await repo.list_visits(**window(owner_confirmed_only=True)))[1] == 0
    assert await repo.get_count(**capture_window(owner_confirmed_only=True)) == 0
    assert await repo.get_all(**capture_window(owner_confirmed_only=True)) == []


@pytest.mark.asyncio
async def test_favourites_and_owner_confirmed_match_a_visit_that_wears_both_badges(repo):
    both = await capture(repo, 0, 0, favorite=True)
    await capture(repo, 1, 20, manual=True)
    await capture(repo, 2, 600, species="Erithacus rubecula", favorite=True)
    await capture(repo, 3, 1200, species="Parus major", manual=True)
    headers, total = await repo.list_visits(**window(favorites=True, owner_confirmed_only=True))
    assert total == 1
    assert headers[0]["visit_id"] == both
    assert headers[0]["capture_count"] == 2
    # Captures are judged one at a time: no single capture is both.
    assert await repo.get_count(**capture_window(favorite_only=True, owner_confirmed_only=True)) == 0
    assert await repo.get_all(**capture_window(favorite_only=True, owner_confirmed_only=True)) == []
    assert (await repo.list_visits(**window(favorites=True)))[1] == 2
    assert (await repo.list_visits(**window(owner_confirmed_only=True)))[1] == 2


@pytest.mark.asyncio
async def test_filtered_visit_pages_and_their_total_hold_beyond_the_last_page(repo):
    for number in range(3):
        await capture(repo, number, number * 600, manual=True)
    await capture(repo, 9, 2400)
    page, total = await repo.list_visits(**window(owner_confirmed_only=True, limit=2))
    assert (len(page), total) == (2, 3)
    page, total = await repo.list_visits(**window(owner_confirmed_only=True, limit=2, offset=10))
    assert (page, total) == ([], 3)


@pytest.mark.asyncio
@pytest.mark.parametrize("sort", ["newest", "oldest"])
async def test_species_reads_apply_the_filter_and_count_what_they_list(repo, sort):
    await capture(repo, 0, 0, manual=True)
    await capture(repo, 1, 600)
    await capture(repo, 2, 1200, manual=True)
    await capture(repo, 3, 1800, species="Unknown Bird", manual=True)
    # A bare species read takes the seek-per-branch fast path unless the filter keeps it out.
    listed = await repo.get_all(species="Turdus merula", sort=sort, owner_confirmed_only=True)
    events = [row.frigate_event for row in listed if row.frigate_event.startswith("confirmed-test-")]
    assert sorted(events) == ["confirmed-test-0", "confirmed-test-2"]
    count = await repo.get_count(species="Turdus merula", owner_confirmed_only=True, start_date=START)
    assert count == 2
    paged = await repo.get_all(**capture_window(owner_confirmed_only=True, limit=1, offset=1, sort=sort))
    assert len(paged) == 1


async def birds_present(monkeypatch, *, owner: bool):
    from app.auth import create_access_token
    from app.config import settings
    from app.routers import events
    from app.utils import public_access

    monkeypatch.setattr(events, "batch_check_clips", AsyncMock(return_value={}))
    if owner:
        monkeypatch.setattr(settings.auth, "enabled", False)
        monkeypatch.setattr(settings.public_access, "enabled", False)
        return {}
    monkeypatch.setattr(settings.auth, "enabled", True)
    monkeypatch.setattr(settings.auth, "session_secret", "confirmed-filter-secret-with-enough-characters")
    monkeypatch.setattr(settings, "api_key", None)
    monkeypatch.setattr(settings.public_access, "enabled", True)
    monkeypatch.setattr(settings.public_access, "show_historical_days", 0)
    monkeypatch.setattr(settings.public_access, "historical_days_mode", "fixed")
    monkeypatch.setattr(public_access, "public_utc_day", lambda now=None: START.date())
    return {"Authorization": "Bearer " + create_access_token("confirmed-guest", "guest")}


@pytest.mark.asyncio
async def test_owner_filters_visits_captures_and_counts_by_owner_confirmation(repo, monkeypatch):
    from app.main import app

    headers = await birds_present(monkeypatch, owner=True)
    confirmed = await capture(repo, 0, 0)
    await capture(repo, 1, 20, manual=True)
    await capture(repo, 2, 600, species="Erithacus rubecula")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test", headers=headers
    ) as client:
        visits = await client.get(f"/api/visits?{DAY}&owner_confirmed_only=true")
        assert visits.status_code == 200, visits.text
        body = visits.json()
        assert body["total"] == 1
        assert body["visits"][0]["visit_id"] == confirmed
        assert body["visits"][0]["owner_confirmed"] is True
        assert body["visits"][0]["capture_count"] == 2
        listed = await client.get(f"/api/events?{DAY}&owner_confirmed_only=true")
        assert [row["frigate_event"] for row in listed.json()] == ["confirmed-test-1"]
        counted = await client.get(f"/api/events/count?{DAY}&owner_confirmed_only=true")
        assert counted.json() == {"count": 1, "filtered": True}
        unfiltered = await client.get(f"/api/visits?{DAY}")
        badges = {visit["visit_id"]: visit["owner_confirmed"] for visit in unfiltered.json()["visits"]}
        assert badges == {confirmed: True, "confirmed-test-2": False}


@pytest.mark.asyncio
async def test_a_guest_link_asking_for_owner_confirmed_gets_the_ordinary_guest_view(repo, monkeypatch):
    from app.main import app

    headers = await birds_present(monkeypatch, owner=False)
    await capture(repo, 0, 0)
    await capture(repo, 1, 20, manual=True)
    await capture(repo, 2, 600, species="Erithacus rubecula")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test", headers=headers
    ) as client:
        for route in ("/api/visits", "/api/events", "/api/events/count"):
            regular = await client.get(f"{route}?{DAY}")
            flagged = await client.get(f"{route}?{DAY}&owner_confirmed_only=true")
            assert regular.status_code == flagged.status_code == 200, flagged.text
            assert flagged.json() == regular.json()
        assert (await client.get(f"/api/visits?{DAY}&owner_confirmed_only=true")).json()["total"] == 2
