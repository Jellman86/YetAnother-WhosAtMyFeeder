"""Add thumbnail_url to taxonomy_cache

Revision ID: e2f3a4b5c6d7
Revises: d1f2c3b4a5b6
Create Date: 2026-02-02 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'e2f3a4b5c6d7'
down_revision = 'd1f2c3b4a5b6'
branch_labels = None
depends_on = None

def upgrade():
    conn = op.get_bind()
    # Check if the column already exists using PRAGMA (project convention)
    rows = conn.execute(sa.text("PRAGMA table_info(taxonomy_cache)")).fetchall()
    columns = {row[1] for row in rows}
    
    if 'thumbnail_url' not in columns:
        op.add_column('taxonomy_cache', sa.Column('thumbnail_url', sa.String(), nullable=True))

def downgrade():
    conn = op.get_bind()
    rows = conn.execute(sa.text("PRAGMA table_info(taxonomy_cache)")).fetchall()
    columns = {row[1] for row in rows}
    
    if 'thumbnail_url' in columns:
        with op.batch_alter_table('taxonomy_cache', schema=None) as batch_op:
            batch_op.drop_column('thumbnail_url')
