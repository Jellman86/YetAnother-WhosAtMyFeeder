"""Every catalogue taxon in its classification.

Birds take order, family and genus from the pinned IOC release that names them, and the ranks
above Aves from Catalogue of Life; each taxon points at its parent, so a lineage is a walk up
the catalogue and a branch is the taxa beneath one parent. Adding the classification must not
change any species' identity, nor let a genus or family name start resolving detection history.
"""

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import build_species_catalog_seed as seed_builder  # noqa: E402
import build_species_reference as reference_builder  # noqa: E402
from app.services.species_catalog_release import connection_content_digest  # noqa: E402
from app.services.species_catalog_resolver import SpeciesCatalogResolver  # noqa: E402
from app.services.taxonomy_tree import TaxonomyTree  # noqa: E402

MULTILINGUAL = hashlib.sha256(b"multilingual").hexdigest()
MASTER = hashlib.sha256(b"master").hexdigest()
COL = hashlib.sha256(b"col export").hexdigest()

SPECIES = [
    # id, scientific, english, order, family, sequence
    (1, "Prunella modularis", "Dunnock", "Passeriformes", "Prunellidae", 300),
    (2, "Prunella collaris", "Alpine Accentor", "Passeriformes", "Prunellidae", 299),
    (3, "Parus major", "Great Tit", "Passeriformes", "Paridae", 200),
    (4, "Columba palumbus", "Common Wood Pigeon", "Columbiformes", "Columbidae", 50),
]


def _reference(tmp_path) -> Path:
    path = tmp_path / "species_reference.db"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE reference_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE taxon (id INTEGER PRIMARY KEY, scientific_name TEXT NOT NULL, common_name TEXT,
            order_name TEXT NOT NULL, family_name TEXT NOT NULL, sequence INTEGER NOT NULL);
        CREATE TABLE family (name TEXT PRIMARY KEY, common_name TEXT NOT NULL) WITHOUT ROWID;
        CREATE TABLE taxon_name (taxon_id INTEGER NOT NULL, locale TEXT NOT NULL, common_name TEXT NOT NULL,
            PRIMARY KEY (taxon_id, locale)) WITHOUT ROWID;
        """
    )
    connection.executemany(
        "INSERT INTO reference_meta VALUES (?, ?)",
        [("schema_version", "3"), ("source_sha256", MULTILINGUAL), ("master_source_sha256", MASTER)],
    )
    connection.executemany("INSERT INTO taxon VALUES (?, ?, ?, ?, ?, ?)", SPECIES)
    connection.executemany(
        "INSERT INTO family VALUES (?, ?)",
        [("Prunellidae", "Accentors"), ("Paridae", "Tits, Chickadees"), ("Columbidae", "Pigeons, Doves")],
    )
    connection.commit()
    connection.close()
    return path


def _manifest(tmp_path) -> Path:
    def source(source_id, digest, redistribution="bundled"):
        return {
            "id": source_id,
            "name": source_id,
            "role": "test",
            "version": "14.2" if source_id.startswith("ioc") else "COL26.7",
            "url": "https://example.org/",
            "licence": "CC-BY-3.0",
            "citation": source_id,
            "redistribution": redistribution,
            "content_sha256": digest,
        }

    path = tmp_path / "species_sources.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "frozen_on": "2026-08-19",
                "sources": [
                    source("ioc-world-bird-list", MULTILINGUAL),
                    source("ioc-world-bird-list-master", MASTER),
                    source("catalogue-of-life", COL, "build-input"),
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def _col_concepts(tmp_path) -> Path:
    path = tmp_path / "col.json"
    path.write_text(json.dumps({"source": {"export_sha256": COL}, "concepts": [], "unresolved": []}))
    return path


@pytest.fixture
def seed(tmp_path):
    output = tmp_path / "species_catalog.db"
    seed_builder.build(
        _reference(tmp_path), output, manifest_path=_manifest(tmp_path), col_concepts_path=_col_concepts(tmp_path)
    )
    return output


def _id(path: Path, scientific: str) -> int:
    connection = sqlite3.connect(path)
    try:
        return connection.execute(
            "SELECT species_id FROM species_concepts WHERE scientific_name = ?", (scientific,)
        ).fetchone()[0]
    finally:
        connection.close()


def test_a_species_lineage_runs_from_animalia_through_its_ioc_genus_family_and_order(seed):
    lineage = TaxonomyTree(seed).lineage(_id(seed, "Prunella modularis"))
    assert [(t.rank, t.scientific_name) for t in lineage] == [
        ("kingdom", "Animalia"),
        ("phylum", "Chordata"),
        ("subphylum", "Vertebrata"),
        ("infraphylum", "Gnathostomata"),
        ("parvphylum", "Osteichthyes"),
        ("megaclass", "Tetrapoda"),
        ("class", "Aves"),
        ("order", "Passeriformes"),
        ("family", "Prunellidae"),
        ("genus", "Prunella"),
        ("species", "Prunella modularis"),
    ]
    # Catalogue of Life's intermediate ranks are kept, flagged so a view can collapse them.
    assert [t.scientific_name for t in lineage if t.principal] == [
        "Animalia",
        "Chordata",
        "Aves",
        "Passeriformes",
        "Prunellidae",
        "Prunella",
        "Prunella modularis",
    ]
    family = lineage[-3]
    assert family.name == "Accentors" and family.source == "ioc-world-bird-list"
    assert lineage[0].source == "catalogue-of-life"
    assert lineage[-1].name == "Dunnock"


def test_a_branch_lists_its_children_in_ioc_order_with_their_species_counts(seed):
    tree = TaxonomyTree(seed)
    orders = tree.children(_id(seed, "Aves"))
    assert [(t.scientific_name, t.species_count) for t in orders] == [("Columbiformes", 1), ("Passeriformes", 3)]
    families = tree.children(_id(seed, "Passeriformes"))
    assert [t.scientific_name for t in families] == ["Paridae", "Prunellidae"]
    species = tree.children(_id(seed, "Prunella"))
    # Sequence, not insertion or alphabetical order: IOC lists the Alpine Accentor first.
    assert [t.scientific_name for t in species] == ["Prunella collaris", "Prunella modularis"]


def test_the_classification_leaves_every_species_its_identity_and_count(seed, tmp_path):
    # Species keep ids 1..n; the ranks above are numbered after them.
    for species_id, scientific, *_ in SPECIES:
        assert _id(seed, scientific) == species_id
    assert _id(seed, "Prunella") > len(SPECIES)
    connection = sqlite3.connect(seed)
    try:
        assert connection.execute("SELECT COUNT(*) FROM species WHERE rank = 'species'").fetchone()[0] == len(SPECIES)
    finally:
        connection.close()


def test_a_genus_or_family_name_never_resolves_detection_history(seed):
    resolver = SpeciesCatalogResolver(seed)
    assert resolver.resolve_scientific_name("Prunella modularis") == (_id(seed, "Prunella modularis"), "resolved")
    for higher in ("Prunella", "Prunellidae", "Passeriformes", "Aves"):
        assert resolver.resolve_scientific_name(higher) == (None, "unknown")


def test_the_release_digest_covers_the_classification(seed):
    connection = sqlite3.connect(seed)
    try:
        before = connection_content_digest(connection)
        dunnock = connection.execute(
            "SELECT species_id FROM species_concepts WHERE scientific_name = 'Prunella modularis'"
        ).fetchone()[0]
        parus = connection.execute(
            "SELECT species_id FROM species_concepts WHERE scientific_name = 'Parus'"
        ).fetchone()[0]
        connection.execute("UPDATE species SET parent_species_id = ? WHERE species_id = ?", (parus, dunnock))
        assert connection_content_digest(connection) != before
    finally:
        connection.close()


def test_a_reference_without_a_classification_still_builds_a_species_only_seed(tmp_path):
    # The previous reference schema: no order, family or sequence. The seed is the same as before.
    path = tmp_path / "old_reference.db"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE reference_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE taxon (id INTEGER PRIMARY KEY, scientific_name TEXT NOT NULL, common_name TEXT);
        CREATE TABLE taxon_name (taxon_id INTEGER NOT NULL, locale TEXT NOT NULL, common_name TEXT NOT NULL,
            PRIMARY KEY (taxon_id, locale)) WITHOUT ROWID;
        """
    )
    connection.execute("INSERT INTO reference_meta VALUES ('source_sha256', ?)", (MULTILINGUAL,))
    connection.execute("INSERT INTO taxon VALUES (1, 'Prunella modularis', 'Dunnock')")
    connection.commit()
    connection.close()
    output = tmp_path / "old_seed.db"
    seed_builder.build(path, output, manifest_path=_manifest(tmp_path))
    check = sqlite3.connect(output)
    try:
        assert check.execute("SELECT rank, parent_species_id FROM species").fetchall() == [("species", None)]
    finally:
        check.close()


def test_the_reference_reads_order_family_and_sequence_and_refuses_a_row_without_them():
    rows = [
        {
            "seq": "300",
            "Order": "PASSERIFORMES",
            "Family": "Prunellidae",
            "IOC14.2": "Prunella modularis",
            "English": "Dunnock",
        },
        {"seq": "", "Order": "PASSERIFORMES", "Family": "Prunellidae", "IOC14.2": "Prunellidae", "English": ""},
    ]
    taxa = reference_builder.parse_ioc(rows)
    assert taxa[0]["order_name"] == "Passeriformes"
    assert taxa[0]["family_name"] == "Prunellidae"
    assert taxa[0]["sequence"] == 300
    with pytest.raises(SystemExit):
        reference_builder.parse_ioc(
            [{"seq": "x", "Order": "", "Family": "Prunellidae", "IOC14.2": "Prunella modularis", "English": "Dunnock"}]
        )


def test_family_names_come_from_the_master_lists_family_rows():
    rows = [
        {"A": "IOC WORLD BIRD LIST (14.2)"},
        {
            "A": "Infraclass",
            "B": "Parvclass",
            "C": "Order",
            "D": "Family (Scientific)",
            "E": "Family (English)",
            "F": "Genus",
        },
        {"C": "PASSERIFORMES"},
        {"D": "Prunellidae", "E": "Accentors"},
        {"F": "Prunella"},
    ]
    assert reference_builder.parse_family_names(rows) == {"Prunellidae": "Accentors"}


def test_the_shipped_reference_classifies_every_species():
    reference = Path(__file__).resolve().parents[1] / "app" / "assets" / "species_reference.db"
    connection = sqlite3.connect(f"file:{reference}?mode=ro", uri=True)
    try:
        orders, families, genera, species = connection.execute(
            "SELECT COUNT(DISTINCT order_name), COUNT(DISTINCT family_name),"
            " COUNT(DISTINCT substr(scientific_name, 1, instr(scientific_name, ' ') - 1)), COUNT(*) FROM taxon"
        ).fetchone()
        named_families = connection.execute("SELECT COUNT(*) FROM family").fetchone()[0]
    finally:
        connection.close()
    # IOC 14.2's own totals, from the master list's header.
    assert (orders, families, genera, species) == (44, 254, 2392, 11276)
    assert named_families == families


def test_an_existing_catalogue_receives_the_classification_with_its_own_identities(tmp_path):
    from app.services.species_catalog_importer import import_release

    # A live catalogue from before the classification: species only, numbered its own way.
    old_reference = tmp_path / "old_reference.db"
    connection = sqlite3.connect(old_reference)
    connection.executescript(
        """
        CREATE TABLE reference_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE taxon (id INTEGER PRIMARY KEY, scientific_name TEXT NOT NULL, common_name TEXT);
        CREATE TABLE taxon_name (taxon_id INTEGER NOT NULL, locale TEXT NOT NULL, common_name TEXT NOT NULL,
            PRIMARY KEY (taxon_id, locale)) WITHOUT ROWID;
        """
    )
    connection.execute("INSERT INTO reference_meta VALUES ('source_sha256', ?)", (MULTILINGUAL,))
    connection.executemany(
        "INSERT INTO taxon VALUES (?, ?, ?)", [(1, "Parus major", "Great Tit"), (2, "Prunella modularis", "Dunnock")]
    )
    connection.commit()
    connection.close()
    live = tmp_path / "live.db"
    seed_builder.build(old_reference, live, manifest_path=_manifest(tmp_path))
    live_dunnock = _id(live, "Prunella modularis")

    bundle = tmp_path / "bundle.db"
    seed_builder.build(
        _reference(tmp_path), bundle, manifest_path=_manifest(tmp_path), col_concepts_path=_col_concepts(tmp_path)
    )
    result = import_release(bundle, live)
    assert result.status == "imported"

    # The Dunnock keeps the identity the live catalogue gave it, and gains its place.
    assert _id(live, "Prunella modularis") == live_dunnock
    lineage = TaxonomyTree(live).lineage(live_dunnock)
    assert [t.scientific_name for t in lineage if t.principal] == [
        "Animalia",
        "Chordata",
        "Aves",
        "Passeriformes",
        "Prunellidae",
        "Prunella",
        "Prunella modularis",
    ]
    check = sqlite3.connect(live)
    try:
        assert check.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        check.close()


def test_the_taxonomy_routes_answer_lineage_and_branches_and_404_an_unknown_taxon(seed, monkeypatch):
    from fastapi.testclient import TestClient

    from app.auth import AuthContext, AuthLevel, get_auth_context_with_legacy
    from app.main import app
    from app.services import taxonomy_tree as tree_module

    monkeypatch.setattr(tree_module, "taxonomy_tree", TaxonomyTree(seed))
    from app.routers import taxonomy as taxonomy_router

    monkeypatch.setattr(taxonomy_router, "taxonomy_tree", TaxonomyTree(seed))
    app.dependency_overrides[get_auth_context_with_legacy] = lambda: AuthContext(auth_level=AuthLevel.OWNER)
    try:
        client = TestClient(app)
        lineage = client.get(f"/api/taxonomy/{_id(seed, 'Prunella modularis')}/lineage").json()["lineage"]
        assert lineage[-1]["scientific_name"] == "Prunella modularis"
        assert lineage[-3] | {"taxon_id": 0, "parent_id": 0} == {
            "taxon_id": 0,
            "rank": "family",
            "scientific_name": "Prunellidae",
            "name": "Accentors",
            "source": "ioc-world-bird-list",
            "principal": True,
            "parent_id": 0,
            "species_count": None,
        }
        children = client.get(f"/api/taxonomy/{_id(seed, 'Passeriformes')}/children").json()["children"]
        assert [(c["scientific_name"], c["species_count"]) for c in children] == [("Paridae", 1), ("Prunellidae", 2)]
        assert client.get("/api/taxonomy/999999/lineage").status_code == 404
    finally:
        app.dependency_overrides.pop(get_auth_context_with_legacy, None)
