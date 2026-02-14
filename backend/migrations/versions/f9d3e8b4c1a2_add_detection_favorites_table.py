"""add detection favorites table

Revision ID: f9d3e8b4c1a2
Revises: 8c1f2d4e6a7b
Create Date: 2026-02-14 17:45:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f9d3e8b4c1a2"
down_revision: Union[str, None] = "8c1f2d4e6a7b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _has_index(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    if not _has_table(inspector, table_name):
        return False
    return any(idx.get("name") == index_name for idx in inspector.get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "detection_favorites"):
        op.create_table(
            "detection_favorites",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("detection_id", sa.Integer(), nullable=False),
            sa.Column("created_by", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.ForeignKeyConstraint(["detection_id"], ["detections.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("detection_id", name="uq_detection_favorites_detection_id"),
        )
        # Refresh inspector after DDL so subsequent index checks are accurate.
        inspector = sa.inspect(bind)

    if not _has_index(inspector, "detection_favorites", "idx_detection_favorites_detection_id"):
        op.create_index("idx_detection_favorites_detection_id", "detection_favorites", ["detection_id"])

    if not _has_index(inspector, "detection_favorites", "idx_detection_favorites_created_at"):
        op.create_index("idx_detection_favorites_created_at", "detection_favorites", ["created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_index(inspector, "detection_favorites", "idx_detection_favorites_created_at"):
        op.drop_index("idx_detection_favorites_created_at", table_name="detection_favorites")
        inspector = sa.inspect(bind)

    if _has_index(inspector, "detection_favorites", "idx_detection_favorites_detection_id"):
        op.drop_index("idx_detection_favorites_detection_id", table_name="detection_favorites")
        inspector = sa.inspect(bind)

    if _has_table(inspector, "detection_favorites"):
        op.drop_table("detection_favorites")
