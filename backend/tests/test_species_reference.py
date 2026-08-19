"""The bundled species reference: names without a network round trip.

Coverage is partial by design. What matters is that a hit is correct and free,
a miss is silent so the caller falls through to eBird and iNaturalist, and a
missing or damaged file never takes the naming path down with it.
"""

import sqlite3
from pathlib import Path

import pytest

from app.services.species_reference import SpeciesReference, species_reference


@pytest.fixture
def reference(tmp_path):
    path = tmp_path / "ref.db"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE reference_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE taxon (
            id INTEGER PRIMARY KEY,
            scientific_name TEXT NOT NULL,
            common_name TEXT,
            source TEXT NOT NULL
        );
        CREATE UNIQUE INDEX idx_taxon_scientific ON taxon (scientific_name COLLATE NOCASE);
        CREATE INDEX idx_taxon_common ON taxon (common_name COLLATE NOCASE);
        """
    )
    connection.executemany(
        "INSERT INTO taxon (scientific_name, common_name, source) VALUES (?, ?, 'test')",
        [
            ("Haemorhous cassinii", "Cassin's Finch"),
            ("Cyanistes caeruleus", "Eurasian Blue Tit"),
            ("Corvus corone", None),
        ],
    )
    connection.executemany(
        "INSERT INTO reference_meta (key, value) VALUES (?, ?)",
        [("schema_version", "1"), ("taxon_count", "3"), ("source", "test")],
    )
    connection.commit()
    connection.close()
    return SpeciesReference(path)


def test_resolves_a_scientific_name(reference):
    result = reference.lookup("Haemorhous cassinii")

    assert result is not None
    assert result["scientific_name"] == "Haemorhous cassinii"
    assert result["common_name"] == "Cassin's Finch"
    assert result["taxa_id"] is None


def test_resolves_a_common_name(reference):
    result = reference.lookup("Eurasian Blue Tit")

    assert result["scientific_name"] == "Cyanistes caeruleus"
    assert result["common_name"] == "Eurasian Blue Tit"


@pytest.mark.parametrize(
    "query",
    ["haemorhous cassinii", "HAEMORHOUS CASSINII", "  Haemorhous cassinii  ", "cassin's finch"],
)
def test_matching_ignores_case_and_surrounding_space(reference, query):
    assert reference.lookup(query) is not None


def test_resolves_the_taxonomic_hierarchy_form(reference):
    """The 10,000-label models emit `04815_Animalia_..._Genus_species`."""
    result = reference.lookup("00123_Animalia_Chordata_Aves_Passeriformes_Fringillidae_Haemorhous_cassinii")

    assert result["scientific_name"] == "Haemorhous cassinii"


def test_resolves_the_paired_form_by_either_half(reference):
    assert reference.lookup("Haemorhous cassinii (Cassin's Finch)")["common_name"] == "Cassin's Finch"
    assert reference.lookup("Cyanistes caeruleus (Blue Tit)")["scientific_name"] == "Cyanistes caeruleus"


def test_a_taxon_with_no_common_name_still_resolves(reference):
    result = reference.lookup("Corvus corone")

    assert result["scientific_name"] == "Corvus corone"
    assert result["common_name"] is None


@pytest.mark.parametrize("query", ["", "   ", None, "Nothing matches this", "Unknown Bird"])
def test_a_miss_is_silent_so_the_caller_falls_through(reference, query):
    assert reference.lookup(query) is None


def test_a_missing_file_disables_the_layer_rather_than_raising(tmp_path):
    absent = SpeciesReference(tmp_path / "does-not-exist.db")

    assert absent.available is False
    assert absent.lookup("Haemorhous cassinii") is None
    assert absent.status()["available"] is False


def test_a_damaged_file_disables_the_layer_rather_than_raising(tmp_path):
    path = tmp_path / "damaged.db"
    path.write_bytes(b"this is not a database")
    damaged = SpeciesReference(path)

    assert damaged.lookup("Haemorhous cassinii") is None
    assert damaged.available is False


def test_status_reports_what_shipped(reference):
    status = reference.status()

    assert status["available"] is True
    assert status["taxon_count"] == 3
    assert status["schema_version"] == "1"


def test_the_shipped_database_is_committed_and_not_swallowed_by_gitignore():
    """`*.db` is ignored, so this asset needs an explicit exception to ship."""
    import subprocess

    root = Path(__file__).resolve().parents[2]
    asset = root / "backend" / "app" / "assets" / "species_reference.db"
    assert asset.is_file(), "the bundled reference is missing from the checkout"

    ignored = subprocess.run(["git", "check-ignore", "-q", str(asset)], cwd=root, capture_output=True)
    assert ignored.returncode != 0, "species_reference.db is git-ignored and would never ship"


def test_the_shipped_database_covers_the_measured_species():
    """The committed asset, not a fixture: a regression guard on the real file."""
    if not species_reference.available:
        pytest.skip("bundled reference not present in this checkout")

    status = species_reference.status()
    assert status["taxon_count"] >= 900

    result = species_reference.lookup("Haemorhous cassinii")
    assert result is not None
    assert result["common_name"] == "Cassin's Finch"


# ── The lookup chain ─────────────────────────────────────────────────────────
#
# The reference sits *after* iNaturalist, not before it. Resolving from it first
# looked attractive but cost the iNaturalist taxon id for every covered species,
# which enrichment needs. The network call is already bounded and cached after
# first sight, so the reference earns its place where the network cannot answer:
# offline installs, and installs riding out an outage.


@pytest.mark.asyncio
async def test_inaturalist_still_wins_when_it_can_answer(monkeypatch):
    """A covered species must keep its taxon id."""
    from app.services.taxonomy import taxonomy_service as module

    async def answers(name):
        return {"scientific_name": "Haemorhous cassinii", "common_name": "Cassin's Finch", "taxa_id": 456}

    async def empty_cache(_query, db=None):
        return None

    async def noop_save(*_args, **_kwargs):
        return None

    monkeypatch.setattr(module.taxonomy_service, "_lookup_inaturalist", answers)
    monkeypatch.setattr(module.taxonomy_service, "_get_from_cache", empty_cache)
    monkeypatch.setattr(module.taxonomy_service, "_save_to_cache", noop_save)

    result = await module.taxonomy_service.get_names("Haemorhous cassinii")

    assert result["taxa_id"] == 456


@pytest.mark.asyncio
async def test_the_reference_answers_when_the_lookup_is_unavailable(monkeypatch):
    """An outage no longer costs a covered species its name."""
    from app.services.taxonomy import taxonomy_service as module
    from app.services.taxonomy.taxonomy_service import TaxonomyLookupUnavailable

    saved: list[object] = []

    async def unavailable(_name):
        raise TaxonomyLookupUnavailable("provider down")

    async def empty_cache(_query, db=None):
        return None

    async def record_save(payload, *_args, **_kwargs):
        saved.append(payload)

    monkeypatch.setattr(module.taxonomy_service, "_lookup_inaturalist", unavailable)
    monkeypatch.setattr(module.taxonomy_service, "_get_from_cache", empty_cache)
    monkeypatch.setattr(module.taxonomy_service, "_save_to_cache", record_save)

    result = await module.taxonomy_service.get_names("Haemorhous cassinii")

    assert result["scientific_name"] == "Haemorhous cassinii"
    assert result["common_name"] == "Cassin's Finch"
    assert result["taxa_id"] is None
    # Nothing is written: a row with no taxon id must not block a later lookup.
    assert saved == []


@pytest.mark.asyncio
async def test_the_reference_answers_when_the_species_is_simply_not_found(monkeypatch):
    from app.services.taxonomy import taxonomy_service as module

    saved: list[object] = []

    async def not_found(_name):
        return None

    async def empty_cache(_query, db=None):
        return None

    async def record_save(payload, *_args, **_kwargs):
        saved.append(payload)

    monkeypatch.setattr(module.taxonomy_service, "_lookup_inaturalist", not_found)
    monkeypatch.setattr(module.taxonomy_service, "_get_from_cache", empty_cache)
    monkeypatch.setattr(module.taxonomy_service, "_save_to_cache", record_save)

    result = await module.taxonomy_service.get_names("Cyanistes caeruleus")

    assert result["common_name"] == "Eurasian Blue Tit"
    assert saved == []


@pytest.mark.asyncio
async def test_an_uncovered_species_still_records_the_negative(monkeypatch):
    """The reference must not swallow the not-found bookkeeping it cannot answer."""
    from app.services.taxonomy import taxonomy_service as module

    saved: list[dict] = []

    async def not_found(_name):
        return None

    async def empty_cache(_query, db=None):
        return None

    async def record_save(payload, *_args, **_kwargs):
        saved.append(payload)

    monkeypatch.setattr(module.taxonomy_service, "_lookup_inaturalist", not_found)
    monkeypatch.setattr(module.taxonomy_service, "_get_from_cache", empty_cache)
    monkeypatch.setattr(module.taxonomy_service, "_save_to_cache", record_save)

    result = await module.taxonomy_service.get_names("Nothing In Any Source")

    assert result["common_name"] is None
    assert len(saved) == 1
    assert saved[0]["is_not_found"] is True


@pytest.mark.asyncio
async def test_the_reference_answer_is_localized_when_the_store_has_the_name(monkeypatch, tmp_path):
    """An offline install still names the bird in the owner's language."""
    from app.config import settings
    from app.services.localized_names import LocalizedNameStore
    from app.services.taxonomy import taxonomy_service as module

    store = LocalizedNameStore(tmp_path / "names.db")
    store.upsert_many("de", [("Cyanistes caeruleus", "Blaumeise")])
    monkeypatch.setattr(module, "localized_names", store)
    monkeypatch.setattr(settings.ebird, "locale", "de")

    async def not_found(_name):
        return None

    async def empty_cache(_query, db=None):
        return None

    async def noop_save(*_args, **_kwargs):
        return None

    monkeypatch.setattr(module.taxonomy_service, "_lookup_inaturalist", not_found)
    monkeypatch.setattr(module.taxonomy_service, "_get_from_cache", empty_cache)
    monkeypatch.setattr(module.taxonomy_service, "_save_to_cache", noop_save)

    result = await module.taxonomy_service.get_names("Cyanistes caeruleus")

    assert result["scientific_name"] == "Cyanistes caeruleus"
    assert result["common_name"] == "Blaumeise"


@pytest.mark.asyncio
async def test_the_reference_answer_stays_english_when_no_translation_is_held(monkeypatch, tmp_path):
    from app.config import settings
    from app.services.localized_names import LocalizedNameStore
    from app.services.taxonomy import taxonomy_service as module

    monkeypatch.setattr(module, "localized_names", LocalizedNameStore(tmp_path / "empty.db"))
    monkeypatch.setattr(settings.ebird, "locale", "de")

    async def not_found(_name):
        return None

    async def empty_cache(_query, db=None):
        return None

    async def noop_save(*_args, **_kwargs):
        return None

    monkeypatch.setattr(module.taxonomy_service, "_lookup_inaturalist", not_found)
    monkeypatch.setattr(module.taxonomy_service, "_get_from_cache", empty_cache)
    monkeypatch.setattr(module.taxonomy_service, "_save_to_cache", noop_save)

    result = await module.taxonomy_service.get_names("Cyanistes caeruleus")

    assert result["common_name"] == "Eurasian Blue Tit"


def test_concurrent_lookups_share_one_connection_safely():
    """The reference is read from the event path; a shared connection needs serializing."""
    import threading

    if not species_reference.available:
        pytest.skip("bundled reference not present in this checkout")

    errors: list[BaseException] = []

    def read() -> None:
        try:
            for _ in range(200):
                species_reference.lookup("Haemorhous cassinii")
                species_reference.lookup("Nothing at all")
        except BaseException as error:  # noqa: BLE001
            errors.append(error)

    threads = [threading.Thread(target=read) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []


# ── Integrity ────────────────────────────────────────────────────────────────


def _reference_with_digest(tmp_path, digest: str | None):
    """A minimal reference plus an optional recorded digest beside it."""
    import sqlite3

    path = tmp_path / "ref.db"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE reference_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE taxon (
            id INTEGER PRIMARY KEY,
            scientific_name TEXT NOT NULL,
            common_name TEXT,
            source TEXT NOT NULL
        );
        CREATE UNIQUE INDEX idx_taxon_scientific ON taxon (scientific_name COLLATE NOCASE);
        """
    )
    connection.execute(
        "INSERT INTO taxon (scientific_name, common_name, source) VALUES ('Cyanistes caeruleus', 'Blue Tit', 't')"
    )
    connection.execute("INSERT INTO reference_meta (key, value) VALUES ('taxon_count', '1')")
    connection.commit()
    connection.close()
    if digest is not None:
        (tmp_path / "ref.db.sha256").write_text(digest, encoding="utf-8")
    return SpeciesReference(path)


def _digest_of(path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_a_reference_matching_its_recorded_digest_is_used(tmp_path):
    reference = _reference_with_digest(tmp_path, None)
    digest = _digest_of(tmp_path / "ref.db")
    (tmp_path / "ref.db.sha256").write_text(f"{digest}  species_reference.db\n", encoding="utf-8")

    assert reference.lookup("Cyanistes caeruleus")["common_name"] == "Blue Tit"


def test_a_reference_that_does_not_match_its_digest_is_refused(tmp_path):
    """Wrong names written into detection history are worse than no names."""
    reference = _reference_with_digest(tmp_path, "0" * 64)

    assert reference.available is False
    assert reference.lookup("Cyanistes caeruleus") is None


def test_a_reference_with_no_recorded_digest_is_still_usable(tmp_path):
    """A locally regenerated file has no sidecar; that is not a corruption signal."""
    reference = _reference_with_digest(tmp_path, None)

    assert reference.lookup("Cyanistes caeruleus") is not None


def test_the_shipped_reference_matches_its_recorded_digest():
    from app.services.species_reference import DEFAULT_REFERENCE_PATH

    sidecar = DEFAULT_REFERENCE_PATH.with_suffix(DEFAULT_REFERENCE_PATH.suffix + ".sha256")
    if not DEFAULT_REFERENCE_PATH.is_file() or not sidecar.is_file():
        pytest.skip("bundled reference not present in this checkout")

    recorded = sidecar.read_text(encoding="utf-8").split()[0]
    assert _digest_of(DEFAULT_REFERENCE_PATH) == recorded
    assert species_reference.available is True


def test_the_build_is_reproducible(tmp_path):
    """A recorded digest is only meaningful if regenerating produces the same file."""
    import hashlib
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from build_species_reference import build

    labels = tmp_path / "labels.txt"
    labels.write_text(
        "Haemorhous cassinii (Cassin's Finch)\nCyanistes caeruleus (Eurasian Blue Tit)\n",
        encoding="utf-8",
    )

    first_path = tmp_path / "one.db"
    second_path = tmp_path / "two.db"
    first_count, first_digest = build(labels, first_path)
    second_count, second_digest = build(labels, second_path)

    assert first_count == second_count == 2
    assert first_digest == second_digest
    assert hashlib.sha256(first_path.read_bytes()).hexdigest() == first_digest
    assert first_path.with_suffix(".db.sha256").read_text(encoding="utf-8").split()[0] == first_digest


def test_duplicate_and_unusable_labels_are_handled_deterministically(tmp_path):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from build_species_reference import parse_labels

    pairs = parse_labels(
        [
            "Haemorhous cassinii (Cassin's Finch)",
            # A repeat keeps the first entry, so regeneration is stable.
            "haemorhous cassinii (Duplicate Different Case)",
            # Anything not in the paired form is skipped rather than guessed at.
            "No parentheses here",
            "",
            "   ",
            "Cyanistes caeruleus ()",
        ]
    )

    assert pairs == [("Haemorhous cassinii", "Cassin's Finch")]
