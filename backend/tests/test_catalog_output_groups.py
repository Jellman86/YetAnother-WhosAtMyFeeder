"""Admission groups are durable catalogue evidence, covered by the release digest."""

import sqlite3

import pytest

from app.services.species_catalog_migrations import upgrade_catalog, downgrade_catalog
from app.services.species_catalog_release import release_content_digest


@pytest.fixture
def catalogue(tmp_path):
    path = tmp_path / "catalog.db"
    upgrade_catalog(path)
    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO model_artifacts(registry_id,model_sha256,output_width,runtime) VALUES ('test',?,1,'onnx')",
            ("a" * 64,),
        )
        db.execute(
            "INSERT INTO model_output_taxa(model_artifact_id,output_index,class_kind,source_label) VALUES (1,0,'unknown','Sciurus carolinensis')"
        )
        db.commit()
    return path


def test_group_defaults_unknown_and_database_rejects_unsupported_values(catalogue):
    with sqlite3.connect(catalogue) as db:
        assert db.execute("SELECT taxonomic_group FROM model_output_taxa").fetchone() == ("unknown",)
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE model_output_taxa SET taxonomic_group='guess'")


def test_group_migration_is_reversible_and_preserves_output_identity(catalogue):
    with sqlite3.connect(catalogue) as db:
        before = db.execute(
            "SELECT model_artifact_id,output_index,class_kind,species_id,source_label FROM model_output_taxa"
        ).fetchall()
    downgrade_catalog(catalogue, "f81c20d9a410")
    upgrade_catalog(catalogue)
    upgrade_catalog(catalogue)
    with sqlite3.connect(catalogue) as db:
        assert (
            db.execute(
                "SELECT model_artifact_id,output_index,class_kind,species_id,source_label FROM model_output_taxa"
            ).fetchall()
            == before
        )
        assert db.execute("SELECT taxonomic_group FROM model_output_taxa").fetchone() == ("unknown",)


def digest(db, version):
    return release_content_digest(db, schema_version=version, source_manifest="{}", generated_at="2026-10-15")


def test_version_two_digest_attests_group_and_original_source_label(catalogue):
    with sqlite3.connect(catalogue) as db:
        original = digest(db, 2)
        db.execute("UPDATE model_output_taxa SET taxonomic_group='nonbird'")
        grouped = digest(db, 2)
        assert grouped != original
        db.execute("UPDATE model_output_taxa SET source_label='Salvia microphylla'")
        assert digest(db, 2) != grouped


def test_legacy_digest_keeps_its_old_definition(catalogue):
    with sqlite3.connect(catalogue) as db:
        original = digest(db, 1)
        db.execute("UPDATE model_output_taxa SET taxonomic_group='nonbird',source_label='Salvia microphylla'")
        assert digest(db, 1) == original


def incoming(group="nonbird"):
    return [
        {
            "output_index": 0,
            "class_kind": "unknown",
            "species_id": None,
            "source_label": "Sciurus carolinensis",
            "taxonomic_group": group,
        }
    ]


def test_import_adds_group_evidence_without_requiring_canonical_identity(catalogue):
    from app.services.species_catalog_importer import complete_artifact_mapping

    with sqlite3.connect(catalogue) as db:
        complete_artifact_mapping(db, artifact_row_id=1, bundle_rows=incoming())
        assert db.execute("SELECT class_kind,species_id,taxonomic_group FROM model_output_taxa").fetchone() == (
            "unknown",
            None,
            "nonbird",
        )


def test_group_enrichment_preserves_a_richer_live_species_mapping(catalogue):
    from app.services.species_catalog_importer import complete_artifact_mapping

    with sqlite3.connect(catalogue) as db:
        db.execute("INSERT INTO species(species_id,rank,status) VALUES (1,'species','accepted')")
        db.execute("UPDATE model_output_taxa SET class_kind='species',species_id=1")
        complete_artifact_mapping(db, artifact_row_id=1, bundle_rows=incoming())
        assert db.execute("SELECT class_kind,species_id,taxonomic_group FROM model_output_taxa").fetchone() == (
            "species",
            1,
            "nonbird",
        )


def test_conflicting_known_groups_are_not_overwritten(catalogue):
    from app.services.species_catalog_importer import complete_artifact_mapping, CatalogImportError

    with sqlite3.connect(catalogue) as db:
        db.execute("UPDATE model_output_taxa SET taxonomic_group='bird'")
        with pytest.raises(CatalogImportError):
            complete_artifact_mapping(db, artifact_row_id=1, bundle_rows=incoming())
        assert db.execute("SELECT taxonomic_group FROM model_output_taxa").fetchone() == ("bird",)


def test_incoming_unknown_does_not_withdraw_known_group_evidence(catalogue):
    from app.services.species_catalog_importer import complete_artifact_mapping

    with sqlite3.connect(catalogue) as db:
        db.execute("UPDATE model_output_taxa SET taxonomic_group='nonbird'")
        complete_artifact_mapping(db, artifact_row_id=1, bundle_rows=incoming("unknown"))
        assert db.execute("SELECT taxonomic_group FROM model_output_taxa").fetchone() == ("nonbird",)


def make_release(path, version):
    with sqlite3.connect(path) as db:
        db.execute("UPDATE model_output_taxa SET taxonomic_group='nonbird'")
        content = digest(db, version)
        db.execute(
            "INSERT INTO catalogue_releases(schema_version,source_manifest,content_sha256,generated_at,state) VALUES (?,'{}',?,'2026-10-15','active')",
            (version, content),
        )
        db.commit()


def test_legacy_release_cannot_smuggle_unattested_group_evidence(catalogue):
    from app.services.species_catalog_importer import _read_bundle, CatalogImportError

    make_release(catalogue, 1)
    with pytest.raises(CatalogImportError):
        _read_bundle(catalogue)


def test_new_release_import_persists_attested_groups(catalogue, tmp_path):
    from app.services.species_catalog_importer import import_release

    make_release(catalogue, 2)
    live = tmp_path / "live.db"
    upgrade_catalog(live)
    import_release(catalogue, catalog_path=live)
    with sqlite3.connect(live) as db:
        assert db.execute("SELECT class_kind,species_id,taxonomic_group FROM model_output_taxa").fetchone() == (
            "unknown",
            None,
            "nonbird",
        )


def test_group_only_import_preserves_richer_identity_and_held_mapping_digest(catalogue, tmp_path):
    from app.services.species_catalog_importer import import_release

    with sqlite3.connect(catalogue) as db:
        db.execute("UPDATE model_artifacts SET mapping_set_sha256=?", ("e" * 64,))
        db.commit()
    make_release(catalogue, 2)
    live = tmp_path / "enriched.db"
    upgrade_catalog(live)
    with sqlite3.connect(live) as db:
        db.execute("INSERT INTO species(species_id,rank,status) VALUES (1,'species','accepted')")
        db.execute(
            "INSERT INTO model_artifacts(registry_id,model_sha256,mapping_set_sha256,output_width,runtime) VALUES ('test',?,?,1,'onnx')",
            ("a" * 64, "f" * 64),
        )
        db.execute(
            "INSERT INTO model_output_taxa(model_artifact_id,output_index,class_kind,species_id,source_label) VALUES (1,0,'species',1,'Sciurus carolinensis')"
        )
        db.commit()
    import_release(catalogue, catalog_path=live)
    with sqlite3.connect(live) as db:
        assert db.execute("SELECT class_kind,species_id,taxonomic_group FROM model_output_taxa").fetchone() == (
            "species",
            1,
            "nonbird",
        )
        assert db.execute("SELECT mapping_set_sha256 FROM model_artifacts").fetchone() == ("f" * 64,)


def test_cold_group_lookup_is_unknown_until_explicit_warm(catalogue):
    from app.services.species_catalog_resolver import SpeciesCatalogResolver

    with sqlite3.connect(catalogue) as db:
        db.execute("UPDATE model_output_taxa SET taxonomic_group='nonbird'")
    resolver = SpeciesCatalogResolver(catalogue)
    assert resolver.cached_output_group("a" * 64, 0, "Sciurus carolinensis") == "unknown"
    assert resolver.warm_output_groups()
    assert resolver.cached_output_group("a" * 64, 0, "Sciurus carolinensis") == "nonbird"


def test_cached_group_lookup_performs_no_file_database_or_stat_access(catalogue, monkeypatch):
    from app.services import species_catalog_resolver as module

    with sqlite3.connect(catalogue) as db:
        db.execute("UPDATE model_output_taxa SET taxonomic_group='nonbird'")
    resolver = module.SpeciesCatalogResolver(catalogue)
    assert resolver.warm_output_groups()

    def forbidden(*args, **kwargs):
        raise AssertionError("cached admission must be pure")

    monkeypatch.setattr(module.sqlite3, "connect", forbidden)
    monkeypatch.setattr(type(catalogue), "stat", forbidden)
    assert resolver.cached_output_group("a" * 64, 0, "Sciurus carolinensis") == "nonbird"


@pytest.mark.parametrize(
    ("model", "index", "label"),
    [
        ("", 0, "Sciurus carolinensis"),
        ("c" * 64, 0, "Sciurus carolinensis"),
        ("a" * 64, True, "Sciurus carolinensis"),
        ("a" * 64, -1, "Sciurus carolinensis"),
        ("a" * 64, 1, "Sciurus carolinensis"),
        ("a" * 64, 0, "Erithacus rubecula"),
        ("a" * 64, 0, ""),
        ("a" * 64, 0, "99999_Animalia_Chordata_Mammalia_Rodentia_Sciuridae_Sciurus_carolinensis"),
    ],
)
def test_group_lookup_requires_matching_producer_index_and_bound_label(catalogue, model, index, label):
    from app.services.species_catalog_resolver import SpeciesCatalogResolver

    with sqlite3.connect(catalogue) as db:
        db.execute("UPDATE model_output_taxa SET taxonomic_group='nonbird'")
    resolver = SpeciesCatalogResolver(catalogue)
    assert resolver.warm_output_groups()
    assert resolver.cached_output_group(model, index, label) == "unknown"
    assert resolver.fresh_output_group(model, index, label) == "unknown"


def test_fresh_guard_and_force_warm_observe_same_size_wal_changes(catalogue):
    from app.services.species_catalog_resolver import SpeciesCatalogResolver

    with sqlite3.connect(catalogue) as writer:
        writer.execute("PRAGMA journal_mode=WAL")
        resolver = SpeciesCatalogResolver(catalogue)
        assert resolver.warm_output_groups()
        assert resolver.cached_output_group("a" * 64, 0, "Sciurus carolinensis") == "unknown"
        writer.execute("UPDATE model_output_taxa SET taxonomic_group='nonbird'")
        writer.commit()
        assert resolver.fresh_output_group("a" * 64, 0, "Sciurus carolinensis") == "nonbird"
        assert resolver.cached_output_group("a" * 64, 0, "Sciurus carolinensis") == "unknown"
        assert resolver.warm_output_groups()
        assert resolver.cached_output_group("a" * 64, 0, "Sciurus carolinensis") == "nonbird"


def test_failed_refresh_invalidates_previously_warm_evidence(catalogue):
    from app.services.species_catalog_resolver import SpeciesCatalogResolver

    with sqlite3.connect(catalogue) as db:
        db.execute("UPDATE model_output_taxa SET taxonomic_group='nonbird'")
    resolver = SpeciesCatalogResolver(catalogue)
    assert resolver.warm_output_groups()
    catalogue.unlink()
    assert not resolver.warm_output_groups()
    assert resolver.cached_output_group("a" * 64, 0, "Sciurus carolinensis") == "unknown"
    assert resolver.fresh_output_group("a" * 64, 0, "Sciurus carolinensis") == "unknown"


def test_explicit_invalidation_discards_snapshot_without_io(catalogue, monkeypatch):
    from app.services import species_catalog_resolver as module

    with sqlite3.connect(catalogue) as db:
        db.execute("UPDATE model_output_taxa SET taxonomic_group='nonbird'")
    resolver = module.SpeciesCatalogResolver(catalogue)
    assert resolver.warm_output_groups()

    def forbidden(*args, **kwargs):
        raise AssertionError("invalidation must not block")

    monkeypatch.setattr(module.sqlite3, "connect", forbidden)
    resolver.invalidate_output_groups()
    assert resolver.cached_output_group("a" * 64, 0, "Sciurus carolinensis") == "unknown"


@pytest.mark.parametrize("extra_kind", ["identity_gain", "absent_output"])
def test_group_enrichment_refuses_mixed_identity_merge_atomically(catalogue, tmp_path, extra_kind):
    from app.services.species_catalog_importer import import_release, CatalogImportError

    live = tmp_path / "mixed.db"
    upgrade_catalog(live)
    with sqlite3.connect(catalogue) as db:
        db.execute("INSERT INTO species(species_id,rank,status) VALUES (2,'species','accepted')")
        db.execute(
            "INSERT INTO species_concepts(species_id,provider,provider_taxon_id,source_release,scientific_name) VALUES (2,'ioc','robin','test','Erithacus rubecula')"
        )
        db.execute("UPDATE model_artifacts SET output_width=2,mapping_set_sha256=?", ("e" * 64,))
        db.execute(
            "INSERT INTO model_output_taxa(model_artifact_id,output_index,class_kind,species_id,source_label,taxonomic_group) VALUES (1,1,'species',2,'Erithacus rubecula','bird')"
        )
    make_release(catalogue, 2)
    with sqlite3.connect(live) as db:
        db.execute("INSERT INTO species(species_id,rank,status) VALUES (1,'species','accepted')")
        db.execute(
            "INSERT INTO model_artifacts(registry_id,model_sha256,mapping_set_sha256,output_width,runtime) VALUES ('test',?,?,2,'onnx')",
            ("a" * 64, "f" * 64),
        )
        db.execute(
            "INSERT INTO model_output_taxa(model_artifact_id,output_index,class_kind,species_id,source_label) VALUES (1,0,'species',1,'Sciurus carolinensis')"
        )
        if extra_kind == "identity_gain":
            db.execute(
                "INSERT INTO model_output_taxa(model_artifact_id,output_index,class_kind,source_label) VALUES (1,1,'unknown','Erithacus rubecula')"
            )
        before = db.execute("SELECT * FROM model_output_taxa").fetchall()
    with pytest.raises(CatalogImportError):
        import_release(catalogue, catalog_path=live)
    with sqlite3.connect(live) as db:
        assert db.execute("SELECT * FROM model_output_taxa").fetchall() == before
        assert db.execute("SELECT mapping_set_sha256 FROM model_artifacts").fetchone() == ("f" * 64,)
        assert db.execute("SELECT count(*) FROM catalogue_releases").fetchone() == (0,)


def test_successful_import_refreshes_the_matching_live_resolver(catalogue, tmp_path, monkeypatch):
    from app.services import species_catalog_resolver as module
    from app.services.species_catalog_importer import import_release

    live = tmp_path / "warm.db"
    upgrade_catalog(live)
    resolver = module.SpeciesCatalogResolver(live)
    monkeypatch.setattr(module, "species_catalog_resolver", resolver)
    assert resolver.warm_output_groups()
    make_release(catalogue, 2)
    import_release(catalogue, catalog_path=live)
    assert resolver.cached_output_group("a" * 64, 0, "Sciurus carolinensis") == "nonbird"
    with sqlite3.connect(live) as db:
        db.execute("UPDATE model_output_taxa SET taxonomic_group='unknown'")
    import_release(catalogue, catalog_path=live)
    assert resolver.cached_output_group("a" * 64, 0, "Sciurus carolinensis") == "nonbird"


def test_refreshing_an_unrelated_catalogue_does_not_discard_live_evidence(catalogue, tmp_path):
    from app.services.species_catalog_resolver import SpeciesCatalogResolver

    resolver = SpeciesCatalogResolver(catalogue)
    with sqlite3.connect(catalogue) as db:
        db.execute("UPDATE model_output_taxa SET taxonomic_group='nonbird'")
    assert resolver.warm_output_groups()
    assert resolver.refresh_output_groups_for(tmp_path / "other.db") is False
    assert resolver.cached_output_group("a" * 64, 0, "Sciurus carolinensis") == "nonbird"
