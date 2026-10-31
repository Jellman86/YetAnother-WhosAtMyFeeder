"""Keep the capture time read from an uploaded file's own metadata.

Revision ID: 7fa03c365538
Revises: f17d29a0c631
Create Date: 2026-10-31 10:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7fa03c365538"
down_revision: Union[str, None] = "f17d29a0c631"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns() -> set[str]:
    rows = op.get_bind().execute(sa.text("PRAGMA table_info(manual_observation_drafts)")).fetchall()
    return {str(row[1]) for row in rows}


def upgrade() -> None:
    columns = _columns()
    if "captured_at" not in columns:
        op.add_column("manual_observation_drafts", sa.Column("captured_at", sa.DateTime(), nullable=True))
    if "captured_at_source" not in columns:
        op.add_column(
            "manual_observation_drafts", sa.Column("captured_at_source", sa.String(length=32), nullable=True)
        )


def downgrade() -> None:
    columns = _columns()
    with op.batch_alter_table("manual_observation_drafts", schema=None) as batch_op:
        if "captured_at_source" in columns:
            batch_op.drop_column("captured_at_source")
        if "captured_at" in columns:
            batch_op.drop_column("captured_at")
