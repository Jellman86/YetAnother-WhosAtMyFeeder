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


def upgrade() -> None:
    op.add_column("detections", sa.Column("video_classification_error", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("detections", "video_classification_error")
