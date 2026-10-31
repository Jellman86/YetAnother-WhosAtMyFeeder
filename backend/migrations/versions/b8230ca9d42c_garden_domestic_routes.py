"""Record why a Garden capture is a domestic bird the owner keeps.

The row names the declared bird and keeps the model evidence that stood for it,
so a routed record shows what the bird model or SpeciesNet originally said.

Revision ID: b8230ca9d42c
Revises: 7fa03c365538
"""

from alembic import op
import sqlalchemy as sa

revision = "b8230ca9d42c"
down_revision = "7fa03c365538"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "garden_domestic_routes" not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(
            "garden_domestic_routes",
            sa.Column(
                "capture_id", sa.String(32), sa.ForeignKey("garden_captures.id", ondelete="CASCADE"), primary_key=True
            ),
            sa.Column("domestic_bird", sa.String(32), nullable=False),
            sa.Column("origin", sa.String(32), nullable=False),
            sa.Column("source_label", sa.String(256), nullable=False),
            sa.Column("source_scientific_name", sa.String(256), nullable=True),
            sa.Column("source_score", sa.Float(), nullable=True),
            sa.Column("source_model", sa.String(256), nullable=True),
            sa.Column("detection_id", sa.Integer(), nullable=True),
            sa.Column("routed_at", sa.String(), nullable=False),
            sa.CheckConstraint(
                "origin IN ('bird_detection','garden_check','moved_from_birds')", name="ck_garden_domestic_origin"
            ),
            sa.CheckConstraint(
                "source_score IS NULL OR (source_score >= 0 AND source_score <= 1)", name="ck_garden_domestic_score"
            ),
            sa.CheckConstraint(
                "length(domestic_bird) BETWEEN 1 AND 32 AND length(source_label) BETWEEN 1 AND 256",
                name="ck_garden_domestic_names",
            ),
        )


def downgrade() -> None:
    if "garden_domestic_routes" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("garden_domestic_routes")
