"""Keep the regional species list and the range filter's decisions (#696).

Three new tables and nothing else: no existing row is read, rewritten or
removed, because the range filter applies to new admissions only.

- `range_lists` holds the one current regional list (its region, when it was
  fetched and for which location).
- `range_list_taxa` holds eBird's species taxonomy for that list, marking which
  species were recorded in the region. Taxonomy rows are kept, not just the
  regional ones, because an absence only counts as evidence for a species
  eBird names at all.
- `range_filter_decisions` remembers each detection the filter changed or set
  aside, so a vagrant can be found and recovered and a fallback can show what
  the model first said.

Revision ID: a6b9e2d41c70
Revises: 7fa03c365538
Create Date: 2026-10-31
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a6b9e2d41c70"
down_revision: Union[str, None] = "7fa03c365538"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    tables = _tables()
    if "range_lists" not in tables:
        op.create_table(
            "range_lists",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("source", sa.String(16), nullable=False),
            sa.Column("region_code", sa.String(16), nullable=False),
            sa.Column("region_codes", sa.Text(), nullable=False),
            sa.Column("region_name", sa.String(200), nullable=True),
            sa.Column("region_level", sa.String(16), nullable=False),
            sa.Column("location_key", sa.String(64), nullable=False),
            sa.Column("fetched_at", sa.DateTime(), nullable=False),
            sa.Column("region_species_total", sa.Integer(), nullable=False),
            sa.Column("note", sa.String(64), nullable=True),
            sa.CheckConstraint("source IN ('ebird')", name="ck_range_lists_source"),
            sa.CheckConstraint("region_level IN ('county','state','country')", name="ck_range_lists_level"),
            sa.UniqueConstraint("source", name="uq_range_lists_source"),
        )
    if "range_list_taxa" not in tables:
        op.create_table(
            "range_list_taxa",
            sa.Column("list_id", sa.Integer(), nullable=False),
            sa.Column("species_code", sa.String(16), nullable=False),
            sa.Column("scientific_name", sa.String(200), nullable=False),
            sa.Column("common_name", sa.String(200), nullable=True),
            sa.Column("in_region", sa.Boolean(), nullable=False, server_default="0"),
            sa.PrimaryKeyConstraint("list_id", "species_code"),
            sa.ForeignKeyConstraint(["list_id"], ["range_lists.id"], ondelete="CASCADE"),
        )
    if "range_filter_decisions" not in tables:
        op.create_table(
            "range_filter_decisions",
            sa.Column("frigate_event", sa.String(), primary_key=True),
            sa.Column("outcome", sa.String(16), nullable=False),
            sa.Column("camera", sa.String(), nullable=True),
            sa.Column("detected_at", sa.DateTime(), nullable=True),
            sa.Column("decided_at", sa.DateTime(), nullable=False),
            sa.Column("original_label", sa.String(), nullable=False),
            sa.Column("original_score", sa.Float(), nullable=False),
            sa.Column("original_species_id", sa.Integer(), nullable=True),
            sa.Column("chosen_label", sa.String(), nullable=True),
            sa.Column("chosen_score", sa.Float(), nullable=True),
            sa.Column("region_code", sa.String(16), nullable=False),
            sa.Column("source", sa.String(16), nullable=False),
            sa.CheckConstraint("outcome IN ('fallback','skipped')", name="ck_range_filter_decisions_outcome"),
        )
        op.create_index("idx_range_filter_decisions_decided_at", "range_filter_decisions", ["decided_at"])


def downgrade() -> None:
    tables = _tables()
    if "range_filter_decisions" in tables:
        op.drop_index("idx_range_filter_decisions_decided_at", table_name="range_filter_decisions")
        op.drop_table("range_filter_decisions")
    if "range_list_taxa" in tables:
        op.drop_table("range_list_taxa")
    if "range_lists" in tables:
        op.drop_table("range_lists")
