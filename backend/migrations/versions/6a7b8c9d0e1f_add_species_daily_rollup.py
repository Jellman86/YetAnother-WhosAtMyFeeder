"""Add species daily rollup table for leaderboard stats.

Revision ID: 6a7b8c9d0e1f
Revises: 5f6a7b8c9d10
Create Date: 2026-01-24 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "6a7b8c9d0e1f"
down_revision = "5f6a7b8c9d10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "species_daily_rollup",
        sa.Column("rollup_date", sa.Date(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("detection_count", sa.Integer(), nullable=False),
        sa.Column("camera_count", sa.Integer(), nullable=False),
        sa.Column("avg_confidence", sa.Float(), nullable=True),
        sa.Column("max_confidence", sa.Float(), nullable=True),
        sa.Column("min_confidence", sa.Float(), nullable=True),
        sa.Column("first_seen", sa.TIMESTAMP(), nullable=True),
        sa.Column("last_seen", sa.TIMESTAMP(), nullable=True),
        sa.PrimaryKeyConstraint("rollup_date", "display_name", name="pk_species_daily_rollup"),
    )
    op.create_index(
        "idx_species_rollup_date",
        "species_daily_rollup",
        ["rollup_date"],
        unique=False,
    )
    op.create_index(
        "idx_species_rollup_display",
        "species_daily_rollup",
        ["display_name"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_species_rollup_display", table_name="species_daily_rollup")
    op.drop_index("idx_species_rollup_date", table_name="species_daily_rollup")
    op.drop_table("species_daily_rollup")
