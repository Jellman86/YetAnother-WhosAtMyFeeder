"""add_video_classification_runtime_columns

Revision ID: c4d2a1f7e9b3
Revises: b3f1a7d9c2e4
Create Date: 2026-03-12 22:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c4d2a1f7e9b3"
down_revision: Union[str, None] = "b3f1a7d9c2e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _get_columns(conn, table: str) -> set[str]:
    rows = conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
    return {row[1] for row in rows}


def upgrade() -> None:
    conn = op.get_bind()
    cols = _get_columns(conn, "detections")
    if "video_classification_provider" not in cols:
        op.add_column("detections", sa.Column("video_classification_provider", sa.String(), nullable=True))
    if "video_classification_backend" not in cols:
        op.add_column("detections", sa.Column("video_classification_backend", sa.String(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    cols = _get_columns(conn, "detections")
    with op.batch_alter_table("detections", schema=None) as batch_op:
        if "video_classification_backend" in cols:
            batch_op.drop_column("video_classification_backend")
        if "video_classification_provider" in cols:
            batch_op.drop_column("video_classification_provider")
