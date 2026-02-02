"""Add thumbnail_url to taxonomy_cache

Revision ID: e2f3a4b5c6d7
Revises: d1f2c3b4a5b6
Create Date: 2026-02-02 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'e2f3a4b5c6d7'
down_revision = 'd1f2c3b4a5b6'
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table('taxonomy_cache', schema=None) as batch_op:
        batch_op.add_column(sa.Column('thumbnail_url', sa.String(), nullable=True))

def downgrade():
    with op.batch_alter_table('taxonomy_cache', schema=None) as batch_op:
        batch_op.drop_column('thumbnail_url')
