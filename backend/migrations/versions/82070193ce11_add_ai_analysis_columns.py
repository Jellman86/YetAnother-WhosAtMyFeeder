"""add_ai_analysis_columns

Revision ID: 82070193ce11
Revises: d784e5774ad1
Create Date: 2026-01-13 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '82070193ce11'
down_revision: Union[str, None] = 'd784e5774ad1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _get_columns(conn, table: str) -> set[str]:
    rows = conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
    return {row[1] for row in rows}


def upgrade() -> None:
    conn = op.get_bind()
    cols = _get_columns(conn, "detections")
    if "ai_analysis" not in cols:
        op.add_column('detections', sa.Column('ai_analysis', sa.String(), nullable=True))
    if "ai_analysis_timestamp" not in cols:
        op.add_column('detections', sa.Column('ai_analysis_timestamp', sa.TIMESTAMP(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    cols = _get_columns(conn, "detections")
    with op.batch_alter_table("detections", schema=None) as batch_op:
        if "ai_analysis_timestamp" in cols:
            batch_op.drop_column('ai_analysis_timestamp')
        if "ai_analysis" in cols:
            batch_op.drop_column('ai_analysis')
