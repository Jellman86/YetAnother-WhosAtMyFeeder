"""Add health samples table

Revision ID: b4e1c9d27a30
Revises: c7d8e9f0a1b2
Create Date: 2026-08-12 08:10:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b4e1c9d27a30"
down_revision: Union[str, None] = "c7d8e9f0a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(bind, table_name: str) -> bool:
    return table_name in sa.inspect(bind).get_table_names()


def _index_exists(bind, table_name: str, index_name: str) -> bool:
    return any(idx.get("name") == index_name for idx in sa.inspect(bind).get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "health_samples"):
        op.create_table(
            "health_samples",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("sampled_at", sa.TIMESTAMP(), nullable=False),
            sa.Column("instance_id", sa.String(), nullable=False),
            sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
    if _table_exists(bind, "health_samples") and not _index_exists(
        bind, "health_samples", "idx_health_samples_sampled_at"
    ):
        with op.batch_alter_table("health_samples", schema=None) as batch_op:
            batch_op.create_index("idx_health_samples_sampled_at", ["sampled_at"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "health_samples"):
        return
    if _index_exists(bind, "health_samples", "idx_health_samples_sampled_at"):
        with op.batch_alter_table("health_samples", schema=None) as batch_op:
            batch_op.drop_index("idx_health_samples_sampled_at")
    op.drop_table("health_samples")
