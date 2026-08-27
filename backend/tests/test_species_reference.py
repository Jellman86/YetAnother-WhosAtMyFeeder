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
    assert status["taxon_count"] >= 10_000

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
    monkeypatch.setattr(settings.ebird, "locale", "en")

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


def _ioc_workbook(tmp_path, rows):
    """A minimal xlsx in the shape the IOC file uses."""
    import zipfile

    def esc(v):
        return str(v).replace("&", "&amp;").replace("<", "&lt;")

    headings = ["seq", "Order", "Family", "IOC14.2", "English", "German", "Italian", "Chinese"]
    all_rows = [headings] + rows
    sheet = ['<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>']
    for r_index, row in enumerate(all_rows, start=1):
        cells = "".join(
            f'<c r="{chr(65 + c_index)}{r_index}" t="inlineStr"><is><t>{esc(value)}</t></is></c>'
            for c_index, value in enumerate(row)
        )
        sheet.append(f'<row r="{r_index}">{cells}</row>')
    sheet.append("</sheetData></worksheet>")

    path = tmp_path / "ioc.xlsx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "xl/sharedStrings.xml", '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"/>'
        )
        archive.writestr("xl/worksheets/sheet1.xml", "".join(sheet))
    return path


def _generator():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import build_species_reference

    return build_species_reference


def _pinned_manifest(tmp_path, source_path, *, content_sha256=None, version="14.2-test"):
    """A manifest that pins the fixture workbook, so the gate admits it."""
    import hashlib
    import json

    digest = content_sha256 if content_sha256 is not None else hashlib.sha256(source_path.read_bytes()).hexdigest()
    path = tmp_path / "species_sources.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "sources": [
                    {
                        "id": "ioc-world-bird-list",
                        "name": "IOC World Bird List (Multilingual)",
                        "role": "bird-vernacular-names",
                        "version": version,
                        "url": "https://www.worldbirdnames.org/",
                        "licence": "CC-BY-3.0",
                        "citation": "IOC World Bird List. https://www.worldbirdnames.org/",
                        "redistribution": "bundled",
                        "content_sha256": digest,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_the_build_is_reproducible(tmp_path):
    """A recorded digest is only meaningful if regenerating produces the same file."""
    import hashlib

    build = _generator().build
    source = _ioc_workbook(
        tmp_path,
        [
            [
                "1",
                "PASSERIFORMES",
                "Paridae",
                "Cyanistes caeruleus",
                "Eurasian Blue Tit",
                "Blaumeise",
                "Cinciarella",
                "青山雀",
            ],
            [
                "2",
                "PASSERIFORMES",
                "Turdidae",
                "Erithacus rubecula",
                "European Robin",
                "Rotkehlchen",
                "Pettirosso",
                "欧亚鸲",
            ],
        ],
    )

    manifest = _pinned_manifest(tmp_path, source)
    first, second = tmp_path / "one.db", tmp_path / "two.db"
    first_taxa, first_names, first_digest = build(source, first, manifest_path=manifest)
    second_taxa, second_names, second_digest = build(source, second, manifest_path=manifest)

    # Two species, each with German, Italian and Chinese.
    assert (first_taxa, first_names) == (second_taxa, second_names) == (2, 6)
    assert first_digest == second_digest
    assert hashlib.sha256(first.read_bytes()).hexdigest() == first_digest
    assert first.with_suffix(".db.sha256").read_text(encoding="utf-8").split()[0] == first_digest


def test_the_build_refuses_a_source_that_is_not_the_pinned_release(tmp_path):
    """Adopting a new IOC release means updating the manifest, not just building."""
    build = _generator().build
    source = _ioc_workbook(tmp_path, [["1", "P", "F", "Cyanistes caeruleus", "Eurasian Blue Tit", "", "", ""]])
    manifest = _pinned_manifest(tmp_path, source, content_sha256="c" * 64)

    with pytest.raises(SystemExit, match="[Pp]rovenance"):
        build(source, tmp_path / "refused.db", manifest_path=manifest)


def test_the_build_records_the_pinned_release_version(tmp_path):
    import sqlite3

    build = _generator().build
    source = _ioc_workbook(tmp_path, [["1", "P", "F", "Cyanistes caeruleus", "Eurasian Blue Tit", "", "", ""]])
    output = tmp_path / "versioned.db"

    build(source, output, manifest_path=_pinned_manifest(tmp_path, source, version="15.9-example"))

    connection = sqlite3.connect(f"file:{output}?mode=ro", uri=True)
    try:
        recorded = dict(connection.execute("SELECT key, value FROM reference_meta").fetchall())
    finally:
        connection.close()
    assert recorded["source_version"] == "15.9-example"
    assert recorded["source_licence"] == "CC-BY-3.0"


def test_the_parser_keeps_species_and_skips_everything_else(tmp_path):
    parse_ioc = _generator().parse_ioc

    taxa = parse_ioc(
        [
            {"IOC14.2": "Cyanistes caeruleus", "English": "Eurasian Blue Tit", "Italian": "Cinciarella"},
            # A repeat keeps the first entry, so regeneration is stable.
            {"IOC14.2": "cyanistes caeruleus", "English": "Duplicate", "Italian": "Doppione"},
            # Order and family rows carry a single word, not a binomial.
            {"IOC14.2": "PASSERIFORMES", "English": ""},
            {"IOC14.2": "", "English": "No name at all"},
        ]
    )

    assert [taxon["scientific_name"] for taxon in taxa] == ["Cyanistes caeruleus"]
    assert taxa[0]["names"] == {"it": "Cinciarella"}


def test_a_language_with_no_name_is_simply_absent(tmp_path):
    parse_ioc = _generator().parse_ioc

    taxa = parse_ioc([{"IOC14.2": "Erithacus rubecula", "English": "European Robin", "Italian": "   "}])

    assert taxa[0]["names"] == {}
    assert taxa[0]["common_name"] == "European Robin"


def test_the_shipped_reference_carries_the_languages_we_present():
    """The point of bundling: names in the owner's language with no key and no network."""
    if not species_reference.available:
        pytest.skip("bundled reference not present in this checkout")

    status = species_reference.status()
    assert status["taxon_count"] > 10_000
    assert status["localized_name_count"] > 80_000
    assert status["source_licence"] == "CC-BY-3.0"

    for locale, expected in (("de", "Blaumeise"), ("it", "Cinciarella"), ("fr", "Mésange bleue")):
        assert species_reference.lookup("Cyanistes caeruleus", locale)["common_name"] == expected
    # English remains the fallback when no locale is asked for.
    assert species_reference.lookup("Cyanistes caeruleus")["common_name"] == "Eurasian Blue Tit"
