"""add ai_usage_log table

Revision ID: cc180b75ba56
Revises: b82b47ae1599
Create Date: 2026-02-23 19:40:47.037257

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cc180b75ba56'
down_revision: Union[str, None] = 'b82b47ae1599'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _has_index(bind, table_name: str, index_name: str) -> bool:
    if not _has_table(bind, table_name):
        return False
    inspector = sa.inspect(bind)
    indexes = inspector.get_indexes(table_name)
    return any(idx['name'] == index_name for idx in indexes)


def upgrade() -> None:
    bind = op.get_bind()
    
    # 1) Create table if not exists
    if not _has_table(bind, 'ai_usage_log'):
        op.create_table(
            'ai_usage_log',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('timestamp', sa.TIMESTAMP(), nullable=False),
            sa.Column('provider', sa.String(), nullable=False),
            sa.Column('model', sa.String(), nullable=False),
            sa.Column('feature', sa.String(), nullable=False),
            sa.Column('input_tokens', sa.Integer(), server_default='0', nullable=False),
            sa.Column('output_tokens', sa.Integer(), server_default='0', nullable=False),
            sa.Column('total_tokens', sa.Integer(), server_default='0', nullable=False)
        )

    # 2) Create indexes if not exist
    if not _has_index(bind, 'ai_usage_log', 'idx_ai_usage_timestamp'):
        with op.batch_alter_table('ai_usage_log', schema=None) as batch_op:
            batch_op.create_index('idx_ai_usage_timestamp', ['timestamp'], unique=False)
            
    if not _has_index(bind, 'ai_usage_log', 'idx_ai_usage_provider_model'):
        with op.batch_alter_table('ai_usage_log', schema=None) as batch_op:
            batch_op.create_index('idx_ai_usage_provider_model', ['provider', 'model'], unique=False)

    # 3) Integrity checks
    bind.execute(sa.text("PRAGMA integrity_check"))
    bind.execute(sa.text("PRAGMA foreign_key_check"))


def downgrade() -> None:
    bind = op.get_bind()
    
    # Drop indexes first
    if _has_index(bind, 'ai_usage_log', 'idx_ai_usage_provider_model'):
        with op.batch_alter_table('ai_usage_log', schema=None) as batch_op:
            batch_op.drop_index('idx_ai_usage_provider_model')
            
    if _has_index(bind, 'ai_usage_log', 'idx_ai_usage_timestamp'):
        with op.batch_alter_table('ai_usage_log', schema=None) as batch_op:
            batch_op.drop_index('idx_ai_usage_timestamp')

    # Drop table
    if _has_table(bind, 'ai_usage_log'):
        op.drop_table('ai_usage_log')
            
    # Integrity checks
    bind.execute(sa.text("PRAGMA integrity_check"))
    bind.execute(sa.text("PRAGMA foreign_key_check"))
