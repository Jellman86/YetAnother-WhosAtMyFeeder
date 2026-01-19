"""Merge heads after manual_tagged addition.

Revision ID: 0f2a3b6c9d11
Revises: c2f1a9d9c0ab, e3b4b2e7f6a1
Create Date: 2026-01-19 14:20:00.000000
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "0f2a3b6c9d11"
down_revision = ("c2f1a9d9c0ab", "e3b4b2e7f6a1")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
