"""Store reviewable garden suggestions independently from bird detections.

Revision ID: f912a3d4e510
Revises: e71b90c4d210
"""

from alembic import op
import sqlalchemy as sa

revision = "f912a3d4e510"
down_revision = "e71b90c4d210"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "garden_identifications" not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(
            "garden_identifications",
            sa.Column("capture_id", sa.String(32), primary_key=True),
            sa.Column("result_json", sa.Text(), nullable=False),
            sa.ForeignKeyConstraint(["capture_id"], ["garden_captures.id"], ondelete="CASCADE"),
            sa.CheckConstraint("json_valid(result_json)", name="ck_garden_identification_json"),
        )


def downgrade() -> None:
    if "garden_identifications" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("garden_identifications")
