"""Localized bird names that survive without a network.

The bundled reference ships English names only, and `taxonomy_translations` is
keyed on an iNaturalist taxon id the reference does not have. This store is
keyed on scientific name so a reference-resolved species can still be named in
the owner's language, and it is populated in bulk from eBird while online so it
is there when nothing is reachable.

It holds reproducible data. Losing it costs one refresh, so it lives beside the
application database rather than inside it, and needs no migration.
"""

import pytest

from app.services.localized_names import LocalizedNameStore


@pytest.fixture
def store(tmp_path):
    return LocalizedNameStore(tmp_path / "names.db")


def test_stores_and_reads_a_localized_name(store):
    written = store.upsert_many("de", [("Cyanistes caeruleus", "Blaumeise")])

    assert written == 1
    assert store.lookup("Cyanistes caeruleus", "de") == "Blaumeise"


def test_lookup_ignores_case_and_surrounding_space(store):
    store.upsert_many("de", [("Cyanistes caeruleus", "Blaumeise")])

    assert store.lookup("  cyanistes CAERULEUS ", "de") == "Blaumeise"


def test_locales_do_not_leak_into_one_another(store):
    store.upsert_many("de", [("Cyanistes caeruleus", "Blaumeise")])
    store.upsert_many("fr", [("Cyanistes caeruleus", "Mésange bleue")])

    assert store.lookup("Cyanistes caeruleus", "fr") == "Mésange bleue"
    assert store.lookup("Cyanistes caeruleus", "es") is None


def test_a_refresh_replaces_a_renamed_species_rather_than_duplicating_it(store):
    store.upsert_many("de", [("Cyanistes caeruleus", "Blaumeise")])
    store.upsert_many("de", [("Cyanistes caeruleus", "Blaumeise (neu)")])

    assert store.lookup("Cyanistes caeruleus", "de") == "Blaumeise (neu)"
    assert store.status()["locales"]["de"] == 1


@pytest.mark.parametrize(
    "entries",
    [
        [("", "Blaumeise")],
        [("Cyanistes caeruleus", "")],
        [("Cyanistes caeruleus", None)],
        [(None, "Blaumeise")],
    ],
)
def test_unusable_rows_are_skipped_rather_than_stored(store, entries):
    assert store.upsert_many("de", entries) == 0
    assert store.lookup("Cyanistes caeruleus", "de") is None


def test_a_name_identical_to_the_english_one_is_not_stored(store):
    """eBird returns English for an untranslated species; storing it would claim a translation."""
    written = store.upsert_many(
        "it", [("Cyanistes caeruleus", "Eurasian Blue Tit")], english={"cyanistes caeruleus": "Eurasian Blue Tit"}
    )

    assert written == 0
    assert store.lookup("Cyanistes caeruleus", "it") is None


def test_status_reports_what_is_held(store):
    store.upsert_many("de", [("A b", "x"), ("C d", "y")])

    status = store.status()

    assert status["available"] is True
    assert status["locales"] == {"de": 2}
    assert status["refreshed_at"]["de"]


def test_a_missing_lookup_is_silent(store):
    assert store.lookup("Nothing here", "de") is None
    assert store.lookup(None, "de") is None
    assert store.lookup("Cyanistes caeruleus", "") is None


def test_an_unwritable_location_disables_the_store_rather_than_raising(tmp_path):
    unwritable = LocalizedNameStore(tmp_path / "no-such-dir" / "deeper" / "names.db")
    unwritable._parent_is_writable = lambda: False  # type: ignore[method-assign]

    assert unwritable.upsert_many("de", [("A b", "x")]) == 0
    assert unwritable.lookup("A b", "de") is None
    assert unwritable.status()["available"] is False


def test_a_damaged_file_disables_the_store_rather_than_raising(tmp_path):
    path = tmp_path / "damaged.db"
    path.write_bytes(b"not a database at all")
    damaged = LocalizedNameStore(path)

    assert damaged.lookup("A b", "de") is None
    assert damaged.status()["available"] is False


# ── Refreshing from eBird ────────────────────────────────────────────────────

from datetime import datetime, timedelta, timezone  # noqa: E402

from app.services import localized_names as module  # noqa: E402

TAXONOMY = {
    "en": [
        {"sciName": "Cyanistes caeruleus", "comName": "Eurasian Blue Tit"},
        {"sciName": "Erithacus rubecula", "comName": "European Robin"},
    ],
    "de": [
        {"sciName": "Cyanistes caeruleus", "comName": "Blaumeise"},
        # eBird returns the English name when it has no translation.
        {"sciName": "Erithacus rubecula", "comName": "European Robin"},
    ],
}


@pytest.fixture
def ebird_taxonomy(monkeypatch):
    from app.services import ebird_service as ebird_module

    async def get_taxonomy(locale=None):
        return TAXONOMY.get(str(locale or "en"), [])

    monkeypatch.setattr(ebird_module.ebird_service, "get_taxonomy", get_taxonomy)


@pytest.mark.asyncio
async def test_a_refresh_stores_only_the_genuinely_translated_names(store, ebird_taxonomy):
    stored = await module.refresh_locale_from_ebird("de", store=store)

    assert stored == 1
    assert store.lookup("Cyanistes caeruleus", "de") == "Blaumeise"
    # Untranslated: storing the English name would claim a translation.
    assert store.lookup("Erithacus rubecula", "de") is None


@pytest.mark.asyncio
async def test_english_is_never_refreshed_because_it_is_the_baseline(store, ebird_taxonomy):
    assert await module.refresh_localized_names(["en"], store=store) == {}


@pytest.mark.asyncio
async def test_a_recent_locale_is_left_alone(store, ebird_taxonomy):
    await module.refresh_localized_names(["de"], store=store)

    assert await module.refresh_localized_names(["de"], store=store) == {}
    assert await module.refresh_localized_names(["de"], store=store, force=True) == {"de": 1}


@pytest.mark.asyncio
async def test_a_broken_ebird_costs_nothing(store, monkeypatch):
    from app.services import ebird_service as ebird_module

    async def explode(locale=None):
        raise RuntimeError("ebird is down")

    monkeypatch.setattr(ebird_module.ebird_service, "get_taxonomy", explode)

    assert await module.refresh_locale_from_ebird("de", store=store) == 0
    assert store.lookup("Cyanistes caeruleus", "de") is None


@pytest.mark.parametrize(
    ("recorded", "due"),
    [
        (None, True),
        ("not a date", True),
        ((datetime.now(timezone.utc) - timedelta(days=1)).isoformat(), False),
        ((datetime.now(timezone.utc) - timedelta(days=60)).isoformat(), True),
    ],
)
def test_refresh_is_due_only_after_the_interval(recorded, due):
    assert module._needs_refresh(recorded) is due
