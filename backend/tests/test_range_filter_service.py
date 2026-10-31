"""The regional list's fetch, cache and validation, with eBird mocked at its HTTP boundary (#696)."""

import json
from datetime import datetime, timedelta

import httpx
import pytest
import pytest_asyncio
from structlog.testing import capture_logs

from app.config import settings
from app.database import close_db, get_db, init_db
from app.repositories.range_filter_repository import (
    RangeDecisionRecord,
    RangeFilterRepository,
    StoredRangeList,
    StoredTaxon,
)
from app.services.ebird_service import EbirdResponseTooLarge, EbirdService
from app.services.range_filter_service import (
    RangeFilterService,
    country_code,
    regional_species_codes,
    species_code_index,
)
from app.services.species_catalog_resolver import ModelSpeciesCoverage

API_KEY = "test-ebird-key-never-logged"
NOW = datetime(2026, 10, 31, 12, 0)

# A tiny eBird world: three species recorded around a Sonoma feeder, one European
# species eBird knows but the county has never recorded, and one subspecies group.
TAXONOMY = [
    {"speciesCode": "amerob", "sciName": "Turdus migratorius", "comName": "American Robin", "category": "species"},
    {"speciesCode": "houfin", "sciName": "Haemorhous mexicanus", "comName": "House Finch", "category": "species"},
    {
        "speciesCode": "yerwar",
        "sciName": "Setophaga coronata",
        "comName": "Yellow-rumped Warbler",
        "category": "species",
    },
    {"speciesCode": "eurbla", "sciName": "Turdus merula", "comName": "Eurasian Blackbird", "category": "species"},
    {
        "speciesCode": "myrwar",
        "sciName": "Setophaga coronata coronata",
        "comName": "Yellow-rumped Warbler (Myrtle)",
        "category": "issf",
    },
    {"speciesCode": "duck1", "sciName": "Anatidae sp.", "comName": "duck sp.", "category": "spuh"},
]
CATALOGUE = {
    "turdus migratorius": 1,
    "haemorhous mexicanus": 2,
    "setophaga coronata": 3,
    "turdus merula": 4,
}
COUNTY_LIST = ["amerob", "houfin", "myrwar", "duck1"]
STATE_LIST = ["amerob", "houfin", "yerwar"]
HOTSPOTS = [
    {
        "locId": "L1",
        "countryCode": "US",
        "subnational1Code": "US-CA",
        "subnational2Code": "US-CA-097",
        "lat": 38.31,
        "lng": -122.70,
    },
    {"locId": "bad", "countryCode": "??", "lat": 38.3, "lng": -122.7},
]


class FakeResolver:
    def __init__(self, coverage: ModelSpeciesCoverage | None = None) -> None:
        self.coverage = coverage

    def resolve_scientific_name(self, name):
        species_id = CATALOGUE.get(str(name or "").casefold())
        return (species_id, "resolved") if species_id else (None, "unknown")

    def cached_output_species_id(self, model_sha256, output_index, label):
        return None

    def cached_species_id_for_name(self, name):
        return CATALOGUE.get(str(name or "").casefold())

    def model_species_coverage(self, model_sha256):
        return self.coverage


def ebird_world(*, requests: list[httpx.Request], county=COUNTY_LIST, status: int = 200):
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if status != 200:
            return httpx.Response(status, text="denied")
        path = request.url.path
        if path.endswith("/ref/hotspot/geo"):
            return httpx.Response(200, json=HOTSPOTS)
        if path.endswith("/ref/taxa-locales/ebird"):
            return httpx.Response(200, json=[{"code": "en"}])
        if path.endswith("/ref/taxonomy/ebird"):
            return httpx.Response(200, json=TAXONOMY)
        if path.endswith("/product/spplist/US-CA-097"):
            return httpx.Response(200, json=county)
        if path.endswith("/product/spplist/US-CA"):
            return httpx.Response(200, json=STATE_LIST)
        if path.startswith("/v2/ref/region/info/"):
            return httpx.Response(200, json={"result": "Sonoma County, California, US"})
        return httpx.Response(404, json={})

    return httpx.MockTransport(handler)


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(settings.ebird, "enabled", True)
    monkeypatch.setattr(settings.ebird, "api_key", API_KEY)
    monkeypatch.setattr(settings.location, "latitude", 38.31211)
    monkeypatch.setattr(settings.location, "longitude", -122.70442)
    monkeypatch.setattr(settings.location, "country", "United States")
    monkeypatch.setattr(settings.classification, "range_filter_enabled", True)
    monkeypatch.setattr(settings.classification, "range_filter_region_level", "county")


@pytest_asyncio.fixture
async def database():
    await init_db()
    async with get_db() as db:
        for table in ("range_list_taxa", "range_lists", "range_filter_decisions"):
            await db.execute(f"DELETE FROM {table}")
        await db.commit()
    yield
    await close_db()


def service_with(transport: httpx.MockTransport, *, coverage=None, clock=lambda: NOW) -> RangeFilterService:
    return RangeFilterService(ebird=EbirdService(transport=transport), resolver=FakeResolver(coverage), clock=clock)


# ── eBird client ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_api_key_travels_only_in_the_header_and_never_reaches_a_log(configured):
    requests: list[httpx.Request] = []
    client = EbirdService(transport=ebird_world(requests=requests, status=403))

    with capture_logs() as logs, pytest.raises(httpx.HTTPStatusError):
        await client.get_region_species_codes("US-CA-097")

    assert requests[0].headers["X-eBirdApiToken"] == API_KEY
    assert API_KEY not in str(requests[0].url)
    assert requests[0].url.host == "api.ebird.org"
    assert API_KEY not in json.dumps(logs, default=str)


@pytest.mark.asyncio
async def test_nearby_hotspots_name_their_regions_nearest_first_and_drop_malformed_rows(configured):
    requests: list[httpx.Request] = []
    client = EbirdService(transport=ebird_world(requests=requests))

    regions = await client.get_nearby_hotspot_regions(
        query_lat=38.3, query_lng=-122.7, feeder_lat=38.31211, feeder_lng=-122.70442
    )

    assert [(region.country, region.state, region.county) for region in regions] == [("US", "US-CA", "US-CA-097")]
    assert regions[0].distance_km < 1
    # eBird is sent the approximate point, never the feeder's exact coordinates.
    assert requests[0].url.params["lat"] == "38.3"
    assert requests[0].url.params["fmt"] == "json"


@pytest.mark.asyncio
async def test_a_region_list_keeps_only_well_formed_codes(configured):
    client = EbirdService(transport=ebird_world(requests=[], county=["amerob", "BAD CODE", 7, "houfin"]))

    assert await client.get_region_species_codes("US-CA-097") == ["amerob", "houfin"]
    with pytest.raises(ValueError):
        await client.get_region_species_codes("../etc/passwd")


@pytest.mark.asyncio
async def test_an_oversized_response_is_refused_before_it_is_parsed(configured):
    def huge(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"[" + b'"amerob",' * 100_000 + b'"x"]')

    client = EbirdService(transport=httpx.MockTransport(huge))

    with pytest.raises(EbirdResponseTooLarge):
        await client.get_region_species_codes("US-CA")


def test_subspecies_groups_report_as_their_species_and_spuhs_are_dropped():
    species, reports_as = species_code_index(TAXONOMY)

    assert set(species) == {"amerob", "houfin", "yerwar", "eurbla"}
    assert reports_as == {"myrwar": "yerwar"}
    assert regional_species_codes(COUNTY_LIST, species, reports_as) == {"amerob", "houfin", "yerwar"}


def test_country_names_resolve_to_ebird_country_codes():
    assert country_code("United States") == "US"
    assert country_code("UK") == "GB"
    assert country_code("gb") == "GB"
    assert country_code("Atlantis") is None
    assert country_code(None) is None


# ── Refresh, cache and validation ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_refresh_caches_the_county_list_and_filters_with_it(configured, database, monkeypatch):
    monkeypatch.setattr("app.services.range_filter_service.county_list_too_short", lambda count: False)
    service = service_with(ebird_world(requests=[]))

    await service.refresh()

    assert service.last_error is None
    active = service.active_list()
    assert active is not None
    assert active.region_code == "US-CA-097"
    assert active.region_name == "Sonoma County, California, US"
    assert active.in_range == frozenset({1, 2, 3})
    assert active.known == frozenset({1, 2, 3, 4})
    assert active.region_species_total == 3

    reloaded = service_with(ebird_world(requests=[]))
    await reloaded.load()
    assert reloaded.active_list() == active


@pytest.mark.asyncio
async def test_an_under_birded_county_steps_up_to_its_state(configured, database):
    service = service_with(ebird_world(requests=[]))

    await service.refresh()

    active = service.active_list()
    assert active is not None
    assert (active.region_code, active.region_level, active.note) == ("US-CA", "state", "county_list_too_short")


@pytest.mark.asyncio
async def test_a_failed_refresh_keeps_the_filter_open_and_says_why(configured, database):
    service = service_with(ebird_world(requests=[], status=403))

    await service.refresh()

    assert service.active_list() is None
    state = service.state()
    assert (state.filtering, state.reason, state.problem) == (False, "lookup_failed", "ebird_key_rejected")


@pytest.mark.asyncio
async def test_an_unreachable_ebird_is_named_as_such(configured, database):
    def offline(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    service = service_with(httpx.MockTransport(offline))

    await service.refresh()

    assert service.state().problem == "ebird_unreachable"


@pytest.mark.asyncio
async def test_a_stale_cached_list_stops_filtering(configured, database, monkeypatch):
    monkeypatch.setattr("app.services.range_filter_service.county_list_too_short", lambda count: False)
    service = service_with(ebird_world(requests=[]))
    await service.refresh()

    later = service_with(ebird_world(requests=[]), clock=lambda: NOW + timedelta(days=31))
    await later.load()

    assert later.active_list() is None
    assert later.state().reason == "list_stale"


@pytest.mark.asyncio
async def test_a_tampered_cached_list_is_refused(configured, database):
    async with get_db() as db:
        await RangeFilterRepository(db).replace_list(
            StoredRangeList(
                source="ebird",
                region_code="US-CA; DROP",
                region_codes=("US-CA; DROP",),
                region_name=None,
                region_level="state",
                location_key="geo:38.31,-122.70|county",
                fetched_at=NOW,
                region_species_total=1,
                note=None,
            ),
            [StoredTaxon("amerob", "Turdus migratorius", "American Robin", True)],
        )
    service = service_with(ebird_world(requests=[]))
    await service.load()

    assert service.active_list() is None
    assert (service.state().reason, service.state().problem) == ("list_unusable", "invalid_region")


@pytest.mark.asyncio
async def test_moving_the_feeder_retires_the_old_list(configured, database, monkeypatch):
    monkeypatch.setattr("app.services.range_filter_service.county_list_too_short", lambda count: False)
    service = service_with(ebird_world(requests=[]))
    await service.refresh()

    monkeypatch.setattr(settings.location, "latitude", 51.2787)
    monkeypatch.setattr(settings.location, "longitude", 0.5217)

    assert service.active_list() is None
    assert service.state().reason == "location_changed"


@pytest.mark.asyncio
async def test_no_key_and_no_location_are_named_and_nothing_is_fetched(configured, database, monkeypatch):
    requests: list[httpx.Request] = []
    service = service_with(ebird_world(requests=requests))

    monkeypatch.setattr(settings.ebird, "api_key", None)
    await service.refresh()
    assert service.state().reason == "needs_ebird_key"

    monkeypatch.setattr(settings.ebird, "api_key", API_KEY)
    monkeypatch.setattr(settings.location, "latitude", None)
    monkeypatch.setattr(settings.location, "longitude", None)
    monkeypatch.setattr(settings.location, "country", None)
    await service.refresh()
    assert service.state().reason == "needs_location"
    assert requests == []


@pytest.mark.asyncio
async def test_a_country_only_location_fetches_the_country_list(configured, database, monkeypatch):
    requests: list[httpx.Request] = []
    monkeypatch.setattr(settings.location, "latitude", None)
    monkeypatch.setattr(settings.location, "longitude", None)

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/product/spplist/US"):
            return httpx.Response(200, json=STATE_LIST)
        return ebird_world(requests=[]).handle_request(request)

    service = service_with(httpx.MockTransport(handler))
    await service.refresh()

    active = service.active_list()
    assert active is not None
    assert (active.region_code, active.region_level) == ("US", "country")
    assert not any(request.url.path.endswith("/ref/hotspot/geo") for request in requests)


@pytest.mark.asyncio
async def test_birdnet_go_calls_add_presence_but_never_remove_it(configured, database, monkeypatch):
    monkeypatch.setattr("app.services.range_filter_service.county_list_too_short", lambda count: False)
    async with get_db() as db:
        await db.execute("DELETE FROM audio_detections")
        await db.execute(
            "INSERT INTO audio_detections (timestamp, species, confidence, scientific_name, source_event_id)"
            " VALUES (?, 'Eurasian Blackbird', 0.9, 'Turdus merula', 'heard-1')",
            (NOW - timedelta(days=3),),
        )
        await db.commit()
    service = service_with(ebird_world(requests=[]))
    await service.refresh()
    await service.reload_heard()

    active = service.active_list()
    assert active is not None
    assert 4 in active.heard
    status = await service.status()
    assert status["heard_species"] == 1
    assert status["heard_only_species"] == 1
    async with get_db() as db:
        await db.execute("DELETE FROM audio_detections")
        await db.commit()


@pytest.mark.asyncio
async def test_status_and_preview_report_the_model_effect_before_the_filter_is_on(configured, database, monkeypatch):
    monkeypatch.setattr("app.services.range_filter_service.county_list_too_short", lambda count: False)
    monkeypatch.setattr(settings.classification, "range_filter_enabled", False)
    coverage = ModelSpeciesCoverage(birds=frozenset({1, 2, 4, 77}), ungrouped=frozenset(), unresolved_outputs=2)
    service = service_with(ebird_world(requests=[]), coverage=coverage)
    monkeypatch.setattr(service, "_active_model_coverage", lambda: coverage)
    await service.refresh()
    async with get_db() as db:
        await db.execute("DELETE FROM detections")
        await db.execute(
            """INSERT INTO detections (detection_time, detection_index, score, display_name, category_name,
                   frigate_event, camera_name, species_id) VALUES (?, 1, 0.9, 'Eurasian Blackbird',
                   'Turdus merula', 'seen-1', 'cam', 4)""",
            (NOW - timedelta(days=1),),
        )
        await db.commit()

    status = await service.status()
    preview = await service.preview()

    assert (status["filtering"], status["reason"]) == (False, "ready")
    assert status["model"] == {"bird_species": 4, "out_of_range": 1, "unmatched": 3}
    assert preview["available"] is True
    assert [item["scientific_name"] for item in preview["recently_seen"]] == ["Turdus merula"]
    assert preview["recently_seen"][0]["detections"] == 1
    assert preview["model_out_of_range_total"] == 1
    assert preview["examples"] == []
    async with get_db() as db:
        await db.execute("DELETE FROM detections")
        await db.commit()


@pytest.mark.asyncio
async def test_decisions_are_recorded_listed_and_pruned(database):
    async with get_db() as db:
        repo = RangeFilterRepository(db)
        for index, outcome in enumerate(["skipped", "fallback", "skipped"]):
            await repo.record_decision(
                RangeDecisionRecord(
                    frigate_event=f"evt-{index}",
                    outcome=outcome,
                    camera="cam",
                    detected_at=NOW,
                    decided_at=NOW - timedelta(days=index * 200),
                    original_label="Turdus merula",
                    original_score=0.9,
                    original_species_id=4,
                    chosen_label="Turdus migratorius" if outcome == "fallback" else None,
                    chosen_score=0.8 if outcome == "fallback" else None,
                    region_code="US-CA-097",
                    source="ebird",
                )
            )
        skips = await repo.recent_skips(limit=10)
        assert [record.frigate_event for record in skips] == ["evt-0", "evt-2"]
        assert (await repo.get_decision("evt-1")).chosen_label == "Turdus migratorius"
        assert await repo.count_decisions_since(NOW - timedelta(days=30)) == {"fallback": 0, "skipped": 1}
        assert await repo.prune_decisions(NOW - timedelta(days=365)) == 1
        assert await repo.get_decision("evt-2") is None
