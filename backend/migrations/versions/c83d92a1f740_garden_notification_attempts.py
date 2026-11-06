"""Remember Garden delivery attempts without changing captures or bird notifications.

Revision ID: c83d92a1f740
Revises: b72d91a4e630
"""

from alembic import op
import sqlalchemy as sa

revision = "c83d92a1f740"
down_revision = "b72d91a4e630"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "garden_notification_attempts" not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(
            "garden_notification_attempts",
            sa.Column("capture_id", sa.String(32), primary_key=True),
            sa.Column("channel", sa.String(16), primary_key=True),
            sa.Column("attempted_at", sa.Text(), nullable=False),
            sa.Column("state", sa.String(16), nullable=False, server_default="attempted"),
            sa.ForeignKeyConstraint(["capture_id"], ["garden_captures.id"], ondelete="CASCADE"),
            sa.CheckConstraint(
                "channel IN ('discord','telegram','pushover','email')", name="ck_garden_notification_channel"
            ),
            sa.CheckConstraint("state IN ('attempted','sent','failed','skipped')", name="ck_garden_notification_state"),
        )


def downgrade() -> None:
    if "garden_notification_attempts" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("garden_notification_attempts")
