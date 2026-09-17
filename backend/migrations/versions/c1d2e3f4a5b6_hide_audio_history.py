"""Preserve local audio removals across MQTT replays.

Revision ID: c1d2e3f4a5b6
Revises: b8e1f2a3c4d5
"""

from alembic import op
import sqlalchemy as sa

revision = "c1d2e3f4a5b6"
down_revision = "b8e1f2a3c4d5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("audio_detections")}
    if "is_hidden" not in columns:
        op.add_column(
            "audio_detections", sa.Column("is_hidden", sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("audio_detections")}
    if "is_hidden" in columns:
        op.drop_column("audio_detections", "is_hidden")
