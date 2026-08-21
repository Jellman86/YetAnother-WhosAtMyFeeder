"""species catalogue schema

The initial schema for /data/species_catalog.db, from the catalogue design
(docs/plans/2026-08-12-versioned-species-catalogue-design.md): opaque species
identity with synonym links, provider concepts, RFC 5646 named translations,
aliases that fail closed, checksum-keyed model artifacts, and the
output-index mapping with declared class kinds. Constraints live here, not in
application code.

Revision ID: b7c2f4a91e00
Revises:
Create Date: 2026-08-19 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7c2f4a91e00"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = (
    "species_name_overrides",
    "model_output_taxa",
    "model_artifacts",
    "species_aliases",
    "species_names",
    "species_concepts",
    "species",
    "catalogue_releases",
)


def _has_table(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "catalogue_releases"):
        op.create_table(
            "catalogue_releases",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("schema_version", sa.Integer(), nullable=False),
            sa.Column("source_manifest", sa.Text(), nullable=False),
            sa.Column("content_sha256", sa.String(), nullable=False),
            sa.Column("generated_at", sa.String(), nullable=False),
            sa.Column("state", sa.String(), nullable=False),
            sa.Column("activated_at", sa.String(), nullable=True),
            sa.CheckConstraint("state IN ('staged', 'active', 'retired')", name="ck_catalogue_releases_state"),
            sa.UniqueConstraint("content_sha256", name="uq_catalogue_releases_content"),
        )
        op.create_index(
            "uq_catalogue_releases_one_active",
            "catalogue_releases",
            ["state"],
            unique=True,
            sqlite_where=sa.text("state = 'active'"),
        )

    if not _has_table(inspector, "species"):
        op.create_table(
            "species",
            sa.Column("species_id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("rank", sa.String(), nullable=False, server_default="species"),
            sa.Column("status", sa.String(), nullable=False, server_default="accepted"),
            sa.Column("accepted_species_id", sa.Integer(), nullable=True),
            sa.CheckConstraint("status IN ('accepted', 'deprecated')", name="ck_species_status"),
            sa.ForeignKeyConstraint(["accepted_species_id"], ["species.species_id"], name="fk_species_accepted"),
            sqlite_autoincrement=True,
        )

    if not _has_table(inspector, "species_concepts"):
        op.create_table(
            "species_concepts",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("species_id", sa.Integer(), nullable=False),
            sa.Column("provider", sa.String(), nullable=False),
            sa.Column("provider_taxon_id", sa.String(), nullable=False),
            sa.Column("source_release", sa.String(), nullable=False),
            sa.Column("scientific_name", sa.String(), nullable=False),
            sa.Column("authorship", sa.String(), nullable=True),
            sa.Column("accepted_name_usage", sa.String(), nullable=True),
            sa.Column("status", sa.String(), nullable=True),
            sa.ForeignKeyConstraint(["species_id"], ["species.species_id"], name="fk_species_concepts_species"),
            sa.UniqueConstraint(
                "provider", "source_release", "provider_taxon_id", name="uq_species_concepts_provider_concept"
            ),
        )
        op.create_index("idx_species_concepts_species", "species_concepts", ["species_id"])
        op.create_index(
            "idx_species_concepts_scientific",
            "species_concepts",
            [sa.text("scientific_name COLLATE NOCASE")],
        )

    if not _has_table(inspector, "species_names"):
        op.create_table(
            "species_names",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("species_id", sa.Integer(), nullable=False),
            sa.Column("language_tag", sa.String(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("name_kind", sa.String(), nullable=False, server_default="vernacular"),
            sa.Column("preferred", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("region", sa.String(), nullable=True),
            sa.Column("provider", sa.String(), nullable=False),
            sa.Column("source_release", sa.String(), nullable=False),
            sa.ForeignKeyConstraint(["species_id"], ["species.species_id"], name="fk_species_names_species"),
            sa.UniqueConstraint(
                "species_id",
                "language_tag",
                "provider",
                "source_release",
                "name",
                name="uq_species_names_provider_name",
            ),
        )
        op.create_index("idx_species_names_species_language", "species_names", ["species_id", "language_tag"])

    if not _has_table(inspector, "species_aliases"):
        op.create_table(
            "species_aliases",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("alias", sa.String(), nullable=False),
            sa.Column("alias_kind", sa.String(), nullable=False),
            sa.Column("species_id", sa.Integer(), nullable=True),
            sa.Column("resolution", sa.String(), nullable=False, server_default="resolved"),
            sa.Column("source", sa.String(), nullable=False),
            sa.Column("confidence", sa.Float(), nullable=True),
            sa.CheckConstraint(
                "resolution IN ('resolved', 'candidate', 'unresolved')", name="ck_species_aliases_resolution"
            ),
            sa.ForeignKeyConstraint(["species_id"], ["species.species_id"], name="fk_species_aliases_species"),
            sa.UniqueConstraint("alias", "alias_kind", "species_id", "source", name="uq_species_aliases_row"),
        )
        op.create_index("idx_species_aliases_alias", "species_aliases", [sa.text("alias COLLATE NOCASE")])
        # SQLite treats NULLs as distinct in the unique constraint above, so
        # unresolved aliases (species_id IS NULL) need their own uniqueness or
        # they duplicate silently on every writer.
        op.create_index(
            "uq_species_aliases_unresolved",
            "species_aliases",
            ["alias", "alias_kind", "source"],
            unique=True,
            sqlite_where=sa.text("species_id IS NULL"),
        )

    if not _has_table(inspector, "model_artifacts"):
        op.create_table(
            "model_artifacts",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("registry_id", sa.String(), nullable=False),
            sa.Column("model_sha256", sa.String(), nullable=False),
            sa.Column("mapping_set_sha256", sa.String(), nullable=True),
            sa.Column("output_width", sa.Integer(), nullable=False),
            sa.Column("runtime", sa.String(), nullable=False),
            sa.Column("model_version", sa.String(), nullable=True),
            sa.Column("state", sa.String(), nullable=False, server_default="registered"),
            sa.CheckConstraint("state IN ('registered', 'installed', 'retired')", name="ck_model_artifacts_state"),
            sa.CheckConstraint("output_width > 0", name="ck_model_artifacts_output_width"),
            sa.UniqueConstraint("model_sha256", name="uq_model_artifacts_checksum"),
        )
        op.create_index("idx_model_artifacts_registry", "model_artifacts", ["registry_id"])

    if not _has_table(inspector, "model_output_taxa"):
        op.create_table(
            "model_output_taxa",
            sa.Column("model_artifact_id", sa.Integer(), nullable=False),
            sa.Column("output_index", sa.Integer(), nullable=False),
            sa.Column("class_kind", sa.String(), nullable=False),
            sa.Column("species_id", sa.Integer(), nullable=True),
            sa.Column("source_label", sa.String(), nullable=False),
            sa.PrimaryKeyConstraint("model_artifact_id", "output_index", name="pk_model_output_taxa"),
            sa.CheckConstraint("output_index >= 0", name="ck_model_output_taxa_index"),
            sa.CheckConstraint(
                "class_kind IN ('species', 'hybrid', 'aggregate', 'background', 'unknown')",
                name="ck_model_output_taxa_kind",
            ),
            sa.CheckConstraint(
                "class_kind != 'species' OR species_id IS NOT NULL", name="ck_model_output_taxa_species_identity"
            ),
            sa.ForeignKeyConstraint(
                ["model_artifact_id"], ["model_artifacts.id"], name="fk_model_output_taxa_artifact", ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(["species_id"], ["species.species_id"], name="fk_model_output_taxa_species"),
        )
        op.create_index("idx_model_output_taxa_species", "model_output_taxa", ["species_id"])

    if not _has_table(inspector, "species_name_overrides"):
        op.create_table(
            "species_name_overrides",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("species_id", sa.Integer(), nullable=False),
            # '' means every language; NULL would make the unique constraint
            # unenforceable because SQLite treats NULLs as distinct.
            sa.Column("language_tag", sa.String(), nullable=False, server_default=""),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("updated_at", sa.String(), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
            sa.ForeignKeyConstraint(["species_id"], ["species.species_id"], name="fk_species_name_overrides_species"),
            sa.UniqueConstraint("species_id", "language_tag", name="uq_species_name_overrides_scope"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for table_name in _TABLES:
        if _has_table(inspector, table_name):
            op.drop_table(table_name)
