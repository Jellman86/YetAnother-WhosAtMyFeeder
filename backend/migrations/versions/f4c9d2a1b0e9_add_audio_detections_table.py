"""Add audio_detections table.

Revision ID: f4c9d2a1b0e9
Revises: 6a7b8c9d0e1f
Create Date: 2026-01-31 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f4c9d2a1b0e9"
down_revision = "6a7b8c9d0e1f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    exists = conn.execute(
        sa.text(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='audio_detections'"
        )
    ).fetchone()
    if not exists:
        op.create_table(
            "audio_detections",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("timestamp", sa.TIMESTAMP(), nullable=False),
            sa.Column("species", sa.String(), nullable=False),
            sa.Column("confidence", sa.Float(), nullable=False),
            sa.Column("sensor_id", sa.String(), nullable=True),
            sa.Column("raw_data", sa.Text(), nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.now(), nullable=True),
        )

    index_exists = conn.execute(
        sa.text(
            "SELECT 1 FROM sqlite_master WHERE type='index' AND name='idx_audio_detections_time'"
        )
    ).fetchone()
    if not index_exists:
        with op.batch_alter_table("audio_detections", schema=None) as batch_op:
            batch_op.create_index("idx_audio_detections_time", ["timestamp"], unique=False)

    index_exists = conn.execute(
        sa.text(
            "SELECT 1 FROM sqlite_master WHERE type='index' AND name='idx_audio_detections_sensor'"
        )
    ).fetchone()
    if not index_exists:
        with op.batch_alter_table("audio_detections", schema=None) as batch_op:
            batch_op.create_index("idx_audio_detections_sensor", ["sensor_id"], unique=False)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_audio_detections_sensor")
    op.execute("DROP INDEX IF EXISTS idx_audio_detections_time")
    op.execute("DROP TABLE IF EXISTS audio_detections")
