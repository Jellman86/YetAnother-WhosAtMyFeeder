"""Keep owner species corrections separate from model evidence.

Revision ID: f17d29a0c631
Revises: e026a10c26b1
"""

from alembic import op
import sqlalchemy as sa

revision = "f17d29a0c631"
down_revision = "e026a10c26b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "garden_owner_identifications" not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(
            "garden_owner_identifications",
            sa.Column(
                "capture_id", sa.String(32), sa.ForeignKey("garden_captures.id", ondelete="CASCADE"), primary_key=True
            ),
            sa.Column("species_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(256), nullable=False),
            sa.Column("scientific_name", sa.String(256), nullable=False),
            sa.Column("changed_at", sa.String(), nullable=False),
            sa.CheckConstraint("species_id > 0", name="ck_garden_owner_species"),
            sa.CheckConstraint(
                "length(name) BETWEEN 1 AND 256 AND length(scientific_name) BETWEEN 1 AND 256",
                name="ck_garden_owner_names",
            ),
        )


def downgrade() -> None:
    if "garden_owner_identifications" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("garden_owner_identifications")
