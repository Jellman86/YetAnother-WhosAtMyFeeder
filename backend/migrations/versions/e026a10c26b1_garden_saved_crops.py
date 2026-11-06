"""Keep bounded confirmed-animal crops independently of temporary full photos.

Revision ID: e026a10c26b1
Revises: c83d92a1f740
"""

from alembic import op
import sqlalchemy as sa

revision = "e026a10c26b1"
down_revision = "c83d92a1f740"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "garden_saved_crops" not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(
            "garden_saved_crops",
            sa.Column(
                "capture_id", sa.String(32), sa.ForeignKey("garden_captures.id", ondelete="CASCADE"), primary_key=True
            ),
            sa.Column("image", sa.LargeBinary(), nullable=True),
            sa.Column("evidence_json", sa.Text(), nullable=True),
            sa.Column("state", sa.String(20), nullable=False),
            sa.Column("retry_after", sa.String(), nullable=True),
            sa.Column("updated_at", sa.String(), nullable=False),
            sa.CheckConstraint("state IN ('available','unavailable','evicted')", name="ck_garden_crop_state"),
            sa.CheckConstraint("image IS NULL OR length(image) BETWEEN 1 AND 131072", name="ck_garden_crop_size"),
            sa.CheckConstraint(
                "(state='available' AND image IS NOT NULL AND evidence_json IS NOT NULL) OR (state!='available' AND image IS NULL)",
                name="ck_garden_crop_available",
            ),
        )


def downgrade() -> None:
    if "garden_saved_crops" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("garden_saved_crops")
