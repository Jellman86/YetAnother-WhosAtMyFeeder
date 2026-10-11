"""Place every catalogue taxon in its classification.

Revision ID: c4e8d1a7b2f3
Revises: b7c2f4a91e00
Create Date: 2026-10-04

The catalogue held species only. A taxon now points at the next higher taxon in
its classification, so the ranks above a species (genus, family, order, class,
phylum, kingdom) are catalogue rows of their own, with their own identity and
names, and a species' lineage is a walk up `parent_species_id`. `sequence`
orders siblings the way the source lists them (IOC's sequence for birds).

Both columns are nullable: a taxon whose classification no pinned source gives
simply has no parent, which is a gap to report, never one to fill by guessing.

Downgrading removes the columns but keeps the higher taxa as rows: identities are never deleted,
because something may already refer to them.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4e8d1a7b2f3"
down_revision: str | Sequence[str] | None = "b7c2f4a91e00"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    # Plain ADD COLUMN rather than a batch table rebuild: SQLite accepts a nullable column with a
    # REFERENCES clause in place, and a rebuild would re-emit the table's constraints in whatever
    # order reflection returns them, so the same upgrade could write two different schemas.
    present = _columns("species")
    if "parent_species_id" not in present:
        # Written out because Alembic's SQLite dialect refuses any constraint on an added column,
        # though SQLite itself accepts a REFERENCES clause on a nullable one.
        op.execute(
            "ALTER TABLE species ADD COLUMN parent_species_id INTEGER"
            " CONSTRAINT fk_species_parent REFERENCES species (species_id)"
        )
    if "sequence" not in present:
        op.add_column("species", sa.Column("sequence", sa.Integer(), nullable=True))
    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("species")}
    if "idx_species_parent" not in indexes:
        op.create_index("idx_species_parent", "species", ["parent_species_id"])


def downgrade() -> None:
    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("species")}
    if "idx_species_parent" in indexes:
        op.drop_index("idx_species_parent", table_name="species")
    present = _columns("species")
    if "sequence" in present:
        op.drop_column("species", "sequence")
    if "parent_species_id" in present:
        # A column with a REFERENCES clause cannot be dropped in place, so this one rebuilds the table.
        with op.batch_alter_table("species") as batch:
            batch.drop_column("parent_species_id")
