"""add_video_classification_model_id

Revision ID: e1a4b5c6d7e8
Revises: c4d2a1f7e9b3
Create Date: 2026-03-14 21:22:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e1a4b5c6d7e8"
down_revision: Union[str, None] = "c4d2a1f7e9b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _get_columns(conn, table: str) -> set[str]:
    rows = conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
    return {row[1] for row in rows}


def upgrade() -> None:
    conn = op.get_bind()
    cols = _get_columns(conn, "detections")
    if "video_classification_model_id" not in cols:
        op.add_column(
            "detections",
            sa.Column("video_classification_model_id", sa.String(), nullable=True),
        )


def downgrade() -> None:
    conn = op.get_bind()
    cols = _get_columns(conn, "detections")
    with op.batch_alter_table("detections", schema=None) as batch_op:
        if "video_classification_model_id" in cols:
            batch_op.drop_column("video_classification_model_id")
