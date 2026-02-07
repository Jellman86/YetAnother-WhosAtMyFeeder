"""add_video_classification_error

Revision ID: 7ab928e69c06
Revises: 0f2a3b6c9d11
Create Date: 2026-01-19 15:43:11.557445

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7ab928e69c06'
down_revision: Union[str, None] = '0f2a3b6c9d11'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _get_columns(conn, table: str) -> set[str]:
    rows = conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
    return {row[1] for row in rows}


def upgrade() -> None:
    conn = op.get_bind()
    cols = _get_columns(conn, "detections")
    if "video_classification_error" not in cols:
        op.add_column("detections", sa.Column("video_classification_error", sa.String(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    cols = _get_columns(conn, "detections")
    with op.batch_alter_table("detections", schema=None) as batch_op:
        if "video_classification_error" in cols:
            batch_op.drop_column("video_classification_error")
