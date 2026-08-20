"""The dedicated migration stream for the species catalogue database.

`species_catalog.db` lives beside `speciesid.db` but is versioned by its own
single-head Alembic environment, so taxonomy and translations can be enriched,
validated, and rolled back without ever holding a migration lock over detection
history. The same §3 bar applies: reversible, idempotent, one head, and
constraints in the schema rather than in application code.
"""

import sqlite3

import pytest

from app.services.species_catalog_migrations import (
    catalog_alembic_config,
    catalog_migration_heads,
    downgrade_catalog,
    upgrade_catalog,
)

EXPECTED_TABLES = {
    "catalogue_releases",
    "species",
    "species_concepts",
    "species_names",
    "species_aliases",
    "model_artifacts",
    "model_output_taxa",
    "species_name_overrides",
}


@pytest.fixture
def catalog_path(tmp_path):
    return tmp_path / "species_catalog.db"


def _tables(path) -> set[str]:
    connection = sqlite3.connect(path)
    try:
        rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    finally:
        connection.close()
    return {row[0] for row in rows if not row[0].startswith("sqlite_")}


def _schema_dump(path) -> str:
    connection = sqlite3.connect(path)
    try:
        rows = connection.execute(
            "SELECT COALESCE(sql, '') FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
    finally:
        connection.close()
    return "\n".join(row[0] for row in rows)


def _connect(path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def test_the_catalogue_stream_has_exactly_one_head():
    assert len(catalog_migration_heads()) == 1


def test_a_fresh_upgrade_creates_the_full_catalogue_schema(catalog_path):
    upgrade_catalog(catalog_path)

    assert EXPECTED_TABLES <= _tables(catalog_path)
    assert "alembic_version" in _tables(catalog_path)


def test_upgrade_downgrade_upgrade_is_a_no_op(catalog_path):
    upgrade_catalog(catalog_path)
    first = _schema_dump(catalog_path)

    downgrade_catalog(catalog_path, "base")
    assert not (EXPECTED_TABLES & _tables(catalog_path)), "downgrade must remove the catalogue schema"

    upgrade_catalog(catalog_path)
    assert _schema_dump(catalog_path) == first


def test_rerunning_the_upgrade_changes_nothing(catalog_path):
    upgrade_catalog(catalog_path)
    first = _schema_dump(catalog_path)

    upgrade_catalog(catalog_path)

    assert _schema_dump(catalog_path) == first


def test_the_config_points_at_the_requested_database(catalog_path):
    config = catalog_alembic_config(catalog_path)

    assert str(catalog_path) in (config.get_main_option("sqlalchemy.url") or "")


class TestSchemaConstraints:
    """§3: what the database can enforce, the database enforces."""

    @pytest.fixture(autouse=True)
    def _migrated(self, catalog_path):
        upgrade_catalog(catalog_path)
        self.path = catalog_path

    def _seed_release_species_artifact(self, connection) -> None:
        connection.execute(
            "INSERT INTO catalogue_releases (schema_version, source_manifest, content_sha256, generated_at, state)"
            " VALUES (1, '{}', 'seed-sha', '2026-08-19T00:00:00Z', 'active')"
        )
        connection.execute("INSERT INTO species (species_id, rank, status) VALUES (1, 'species', 'accepted')")
        connection.execute(
            "INSERT INTO model_artifacts (id, registry_id, model_sha256, output_width, runtime)"
            " VALUES (1, 'rope_vit_b14_inat21', 'deadbeef', 10000, 'onnx')"
        )

    def test_at_most_one_release_can_be_active(self):
        connection = _connect(self.path)
        try:
            connection.execute(
                "INSERT INTO catalogue_releases (schema_version, source_manifest, content_sha256, generated_at, state)"
                " VALUES (1, '{}', 'aaa', '2026-08-19T00:00:00Z', 'active')"
            )
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO catalogue_releases (schema_version, source_manifest, content_sha256, generated_at, state)"
                    " VALUES (1, '{}', 'bbb', '2026-08-19T00:00:00Z', 'active')"
                )
            # A second staged or retired release is fine.
            connection.execute(
                "INSERT INTO catalogue_releases (schema_version, source_manifest, content_sha256, generated_at, state)"
                " VALUES (1, '{}', 'ccc', '2026-08-19T00:00:00Z', 'staged')"
            )
        finally:
            connection.close()

    def test_an_unknown_release_state_is_rejected(self):
        connection = _connect(self.path)
        try:
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO catalogue_releases (schema_version, source_manifest, content_sha256, generated_at, state)"
                    " VALUES (1, '{}', 'ddd', '2026-08-19T00:00:00Z', 'probably_fine')"
                )
        finally:
            connection.close()

    def test_a_model_artifact_checksum_is_unique(self):
        connection = _connect(self.path)
        try:
            self._seed_release_species_artifact(connection)
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO model_artifacts (registry_id, model_sha256, output_width, runtime)"
                    " VALUES ('a_republished_model', 'deadbeef', 707, 'onnx')"
                )
        finally:
            connection.close()

    def test_an_output_index_maps_exactly_once_per_artifact(self):
        connection = _connect(self.path)
        try:
            self._seed_release_species_artifact(connection)
            connection.execute(
                "INSERT INTO model_output_taxa (model_artifact_id, output_index, class_kind, species_id, source_label)"
                " VALUES (1, 0, 'species', 1, 'Cyanistes caeruleus')"
            )
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO model_output_taxa (model_artifact_id, output_index, class_kind, species_id, source_label)"
                    " VALUES (1, 0, 'species', 1, 'a second meaning for index 0')"
                )
        finally:
            connection.close()

    def test_a_species_class_must_name_a_species(self):
        connection = _connect(self.path)
        try:
            self._seed_release_species_artifact(connection)
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO model_output_taxa (model_artifact_id, output_index, class_kind, species_id, source_label)"
                    " VALUES (1, 1, 'species', NULL, 'a species with no identity')"
                )
            # A background class deliberately has no species.
            connection.execute(
                "INSERT INTO model_output_taxa (model_artifact_id, output_index, class_kind, species_id, source_label)"
                " VALUES (1, 1, 'background', NULL, 'background')"
            )
        finally:
            connection.close()

    def test_an_unknown_class_kind_is_rejected(self):
        connection = _connect(self.path)
        try:
            self._seed_release_species_artifact(connection)
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO model_output_taxa (model_artifact_id, output_index, class_kind, species_id, source_label)"
                    " VALUES (1, 2, 'mystery', NULL, 'x')"
                )
        finally:
            connection.close()

    def test_a_mapping_row_cannot_point_at_a_missing_artifact_or_species(self):
        connection = _connect(self.path)
        try:
            self._seed_release_species_artifact(connection)
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO model_output_taxa (model_artifact_id, output_index, class_kind, species_id, source_label)"
                    " VALUES (99, 0, 'species', 1, 'orphaned artifact')"
                )
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO model_output_taxa (model_artifact_id, output_index, class_kind, species_id, source_label)"
                    " VALUES (1, 3, 'species', 99, 'orphaned species')"
                )
        finally:
            connection.close()

    def test_a_provider_concept_is_unique_per_release(self):
        connection = _connect(self.path)
        try:
            self._seed_release_species_artifact(connection)
            connection.execute(
                "INSERT INTO species_concepts (species_id, provider, provider_taxon_id, source_release, scientific_name)"
                " VALUES (1, 'catalogue-of-life', 'COL123', 'COL26.7', 'Cyanistes caeruleus')"
            )
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO species_concepts (species_id, provider, provider_taxon_id, source_release, scientific_name)"
                    " VALUES (1, 'catalogue-of-life', 'COL123', 'COL26.7', 'a second reading of the same concept')"
                )
        finally:
            connection.close()

    def test_language_tags_wider_than_five_characters_fit(self):
        """RFC 5646 tags such as `zh-Hant` and `pt-BR` are the reason the old
        five-character column could not be reused."""
        connection = _connect(self.path)
        try:
            self._seed_release_species_artifact(connection)
            connection.execute(
                "INSERT INTO species_names (species_id, language_tag, name, name_kind, provider, source_release)"
                " VALUES (1, 'zh-Hant', '青山雀', 'vernacular', 'ioc-world-bird-list', '14.2')"
            )
        finally:
            connection.close()

    def test_one_owner_override_per_species_and_language(self):
        connection = _connect(self.path)
        try:
            self._seed_release_species_artifact(connection)
            connection.execute(
                "INSERT INTO species_name_overrides (species_id, language_tag, name) VALUES (1, '', 'My blue tit')"
            )
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO species_name_overrides (species_id, language_tag, name) VALUES (1, '', 'Another name')"
                )
            # A per-language override coexists with the all-languages one.
            connection.execute(
                "INSERT INTO species_name_overrides (species_id, language_tag, name) VALUES (1, 'de', 'Meine Meise')"
            )
        finally:
            connection.close()

    def test_a_synonym_can_point_at_its_accepted_species(self):
        connection = _connect(self.path)
        try:
            self._seed_release_species_artifact(connection)
            connection.execute(
                "INSERT INTO species (species_id, rank, status, accepted_species_id)"
                " VALUES (2, 'species', 'deprecated', 1)"
            )
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO species (species_id, rank, status, accepted_species_id)"
                    " VALUES (3, 'species', 'deprecated', 99)"
                )
        finally:
            connection.close()
