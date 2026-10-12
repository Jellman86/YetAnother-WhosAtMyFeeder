import gzip
import hashlib
import json
import sqlite3

import pytest

from app.repositories.garden_catalog import GardenCatalog, read_shipped_package
from app.services.species_catalog_migrations import upgrade_catalog


@pytest.fixture
def catalogue(tmp_path):
    path = tmp_path / "catalog.db"
    upgrade_catalog(path)
    return GardenCatalog(path)


def test_package_is_checksum_bound_and_has_every_ordered_output():
    raw, checksum = read_shipped_package()
    assert hashlib.sha256(raw).hexdigest() == checksum
    payload = json.loads(raw)
    assert len(payload["outputs"]) == 2498
    assert set(payload["model_sha256"]) == {"4.0.3a", "4.0.3b"}


def test_catalogue_import_is_idempotent_and_outputs_share_canonical_identity(catalogue):
    catalogue.initialize()
    first = catalogue.load()
    catalogue.initialize()
    second = catalogue.load()
    assert first == second
    assert set(first["bindings"]) == {v["id"] for v in [*first["outputs"], *first["taxonomy"]]}
    with sqlite3.connect(catalogue.path) as db:
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        for variant in ("4.0.3a", "4.0.3b"):
            assert (
                db.execute(
                    "SELECT COUNT(*) FROM model_output_taxa t JOIN model_artifacts a ON a.id=t.model_artifact_id "
                    "WHERE a.model_sha256=?",
                    (first["model_sha256"][variant],),
                ).fetchone()[0]
                == 2498
            )


def test_existing_species_and_owner_names_are_preserved(catalogue):
    with sqlite3.connect(catalogue.path) as db:
        db.execute("INSERT INTO species(species_id,rank,status) VALUES (123,'species','accepted')")
        db.execute(
            "INSERT INTO species_concepts(species_id,provider,provider_taxon_id,source_release,scientific_name) "
            "VALUES (123,'test','fox','1','Vulpes vulpes')"
        )
        db.execute("INSERT INTO species_name_overrides(species_id,language_tag,name) VALUES (123,'','Our fox')")
    catalogue.initialize()
    bundle = catalogue.load()
    fox = next(t for t in bundle["taxonomy"] if t["ranks"][3:] == ["vulpes", "vulpes"])
    assert bundle["bindings"][fox["id"]] == 123
    with sqlite3.connect(catalogue.path) as db:
        assert db.execute("SELECT name FROM species_name_overrides").fetchall() == [("Our fox",)]


def test_ambiguous_name_never_selects_an_arbitrary_existing_species(catalogue):
    with sqlite3.connect(catalogue.path) as db:
        for identity in (1, 2):
            db.execute("INSERT INTO species(species_id,rank,status) VALUES (?,'species','accepted')", (identity,))
            db.execute(
                "INSERT INTO species_concepts(species_id,provider,provider_taxon_id,source_release,scientific_name) "
                "VALUES (?,'test',?,'1','Vulpes vulpes')",
                (identity, str(identity)),
            )
    catalogue.initialize()
    bundle = catalogue.load()
    fox = next(t for t in bundle["taxonomy"] if t["ranks"][3:] == ["vulpes", "vulpes"])
    assert bundle["bindings"][fox["id"]] is None


def test_tampered_package_is_refused_before_catalogue_writes(catalogue, tmp_path):
    raw, _ = read_shipped_package()
    data = json.loads(raw)
    data["outputs"].reverse()
    source = tmp_path / "altered.json.gz"
    source.write_bytes(gzip.compress(json.dumps(data).encode()))
    with pytest.raises(ValueError, match="checksum"):
        catalogue.initialize(source)
    with sqlite3.connect(catalogue.path) as db:
        assert db.execute("SELECT COUNT(*) FROM garden_model_packages").fetchone()[0] == 0


def test_existing_display_name_is_not_shadowed_by_lower_priority_model_name(catalogue):
    from app.services.species_names import SpeciesNameLookup

    with sqlite3.connect(catalogue.path) as db:
        db.execute("INSERT INTO species(species_id,rank,status) VALUES (123,'species','accepted')")
        db.execute(
            "INSERT INTO species_concepts(species_id,provider,provider_taxon_id,source_release,scientific_name) "
            "VALUES (123,'test','fox','1','Vulpes vulpes')"
        )
        db.execute(
            "INSERT INTO species_names(species_id,language_tag,name,name_kind,preferred,provider,source_release) "
            "VALUES (123,'en','Existing fox name','vernacular',1,'test','1')"
        )
    catalogue.initialize()
    assert SpeciesNameLookup(catalogue.path).display_names([123], language="en") == {123: "Existing fox name"}


def test_new_garden_species_has_canonical_parent_chain(catalogue):
    catalogue.initialize()
    bundle = catalogue.load()
    fox = next(t for t in bundle["taxonomy"] if t["ranks"][3:] == ["vulpes", "vulpes"])
    with sqlite3.connect(catalogue.path) as db:
        chain = db.execute(
            """WITH RECURSIVE lineage(id,parent,rank) AS (
            SELECT species_id,parent_species_id,rank FROM species WHERE species_id=? UNION ALL
            SELECT s.species_id,s.parent_species_id,s.rank FROM species s JOIN lineage l ON s.species_id=l.parent)
            SELECT rank FROM lineage""",
            (bundle["bindings"][fox["id"]],),
        ).fetchall()
    assert chain == [("species",), ("genus",), ("family",), ("order",), ("class",), ("kingdom",)]


def test_catalogue_migration_roundtrip_reuses_durable_species_and_model_identities(catalogue):
    from app.services.species_catalog_migrations import downgrade_catalog

    catalogue.initialize()
    before = catalogue.load()
    downgrade_catalog(catalogue.path)
    upgrade_catalog(catalogue.path)
    catalogue.initialize()
    assert catalogue.load() == before
    with sqlite3.connect(catalogue.path) as db:
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert db.execute("SELECT COUNT(*) FROM model_artifacts").fetchone() == (2,)
