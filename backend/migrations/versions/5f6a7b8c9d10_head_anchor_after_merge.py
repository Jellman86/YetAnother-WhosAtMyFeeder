"""Head anchor after merge to keep downgrades unambiguous.

Revision ID: 5f6a7b8c9d10
Revises: 4a1e2b3c4d5e
Create Date: 2026-01-24 00:00:00.000000
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "5f6a7b8c9d10"
down_revision = "4a1e2b3c4d5e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
