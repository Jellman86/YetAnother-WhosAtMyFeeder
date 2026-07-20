"""Add video classification input provenance.

Revision ID: e7a1c9d4b2f6
Revises: d6e7f8a9b0c1
Create Date: 2026-07-20 17:05:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "e7a1c9d4b2f6"
down_revision: Union[str, None] = "d6e7f8a9b0c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_names(bind) -> set[str]:
    return {str(column["name"]) for column in inspect(bind).get_columns("detections")}


def upgrade() -> None:
    bind = op.get_bind()
    if "video_classification_input_source" not in _column_names(bind):
        op.add_column(
            "detections",
            sa.Column("video_classification_input_source", sa.String(length=64), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if "video_classification_input_source" not in _column_names(bind):
        return
    with op.batch_alter_table("detections", schema=None) as batch_op:
        batch_op.drop_column("video_classification_input_source")
