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


def upgrade() -> None:
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
    op.create_index('ix_oauth_tokens_provider', 'oauth_tokens', ['provider'])
    op.create_index('ix_oauth_tokens_email', 'oauth_tokens', ['email'])


def downgrade() -> None:
    op.drop_index('ix_oauth_tokens_email', table_name='oauth_tokens')
    op.drop_index('ix_oauth_tokens_provider', table_name='oauth_tokens')
    op.drop_table('oauth_tokens')
