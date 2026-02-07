"""add_oauth_tokens_table

Revision ID: 10b7668f28ac
Revises: 5b3af58c84f7
Create Date: 2026-01-16 07:43:23.803214

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '10b7668f28ac'
down_revision: Union[str, None] = '5b3af58c84f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(conn, name: str) -> bool:
    return (
        conn.execute(
            sa.text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:name"),
            {"name": name},
        ).fetchone()
        is not None
    )


def _index_exists(conn, name: str) -> bool:
    return (
        conn.execute(
            sa.text("SELECT 1 FROM sqlite_master WHERE type='index' AND name=:name"),
            {"name": name},
        ).fetchone()
        is not None
    )


def upgrade() -> None:
    conn = op.get_bind()
    if not _table_exists(conn, "oauth_tokens"):
        op.create_table(
            'oauth_tokens',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('provider', sa.String(), nullable=False),  # 'gmail', 'outlook', etc.
            sa.Column('email', sa.String(), nullable=False),  # User's email address
            sa.Column('access_token', sa.String(), nullable=False),  # OAuth access token
            sa.Column('refresh_token', sa.String(), nullable=True),  # OAuth refresh token
            sa.Column('token_type', sa.String(), nullable=True),  # Usually 'Bearer'
            sa.Column('expires_at', sa.DateTime(), nullable=True),  # Token expiration timestamp
            sa.Column('scope', sa.String(), nullable=True),  # OAuth scopes granted
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id')
        )

    # Ensure indexes exist even if the table came from a partial/older state.
    if not _index_exists(conn, "ix_oauth_tokens_provider"):
        op.create_index('ix_oauth_tokens_provider', 'oauth_tokens', ['provider'])
    if not _index_exists(conn, "ix_oauth_tokens_email"):
        op.create_index('ix_oauth_tokens_email', 'oauth_tokens', ['email'])


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_oauth_tokens_email")
    op.execute("DROP INDEX IF EXISTS ix_oauth_tokens_provider")
    op.execute("DROP TABLE IF EXISTS oauth_tokens")
