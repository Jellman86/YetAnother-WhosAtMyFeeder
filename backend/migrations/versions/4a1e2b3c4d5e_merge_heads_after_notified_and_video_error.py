"""Merge heads after notified_at and video error additions.

Revision ID: 4a1e2b3c4d5e
Revises: 7ab928e69c06, b1c2d3e4f5a6
Create Date: 2026-01-24 00:00:00.000000
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "4a1e2b3c4d5e"
down_revision = ("7ab928e69c06", "b1c2d3e4f5a6")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
