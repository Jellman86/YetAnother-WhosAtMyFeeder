"""Separate owner-reviewed garden captures from bird history.

Revision ID: e71b90c4d210
Revises: d2f643a11e00
"""

from alembic import op
import sqlalchemy as sa

revision = "e71b90c4d210"
down_revision = "d2f643a11e00"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "garden_captures" not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(
            "garden_captures",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("event_key", sa.String(64), nullable=False, unique=True),
            sa.Column("frigate_event", sa.String(128), nullable=True, unique=True),
            sa.Column("camera", sa.String(100), nullable=False),
            sa.Column("label", sa.String(32), nullable=False),
            sa.Column("observed_at", sa.String(), nullable=False),
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column("has_snapshot", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("reviewed_at", sa.String(), nullable=True),
            sa.CheckConstraint("status IN ('pending', 'confirmed', 'dismissed', 'blocked')", name="ck_garden_status"),
            sa.CheckConstraint(
                "status != 'blocked' OR (frigate_event IS NULL AND camera = '' AND label = '' AND has_snapshot = 0)",
                name="ck_garden_blocked_private",
            ),
        )
    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("garden_captures")}
    if "idx_garden_status_time" not in indexes:
        op.create_index("idx_garden_status_time", "garden_captures", ["status", "observed_at", "id"])


def downgrade() -> None:
    if "garden_captures" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("garden_captures")
