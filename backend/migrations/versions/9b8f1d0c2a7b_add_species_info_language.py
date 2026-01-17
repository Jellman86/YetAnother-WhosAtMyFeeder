"""Add language support to species info cache

Revision ID: 9b8f1d0c2a7b
Revises: 7f4b5c1b1b77
Create Date: 2026-01-18 13:52:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9b8f1d0c2a7b'
down_revision: Union[str, None] = '7f4b5c1b1b77'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if 'species_info_cache' not in tables:
        return

    # Create a new table with language column + composite unique key
    op.create_table(
        'species_info_cache_new',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('species_name', sa.String(), nullable=False),
        sa.Column('language', sa.String(), nullable=False, server_default='en'),
        sa.Column('title', sa.String(), nullable=True),
        sa.Column('taxa_id', sa.Integer(), nullable=True),
        sa.Column('source', sa.String(), nullable=True),
        sa.Column('source_url', sa.String(), nullable=True),
        sa.Column('summary_source', sa.String(), nullable=True),
        sa.Column('summary_source_url', sa.String(), nullable=True),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('extract', sa.String(), nullable=True),
        sa.Column('thumbnail_url', sa.String(), nullable=True),
        sa.Column('wikipedia_url', sa.String(), nullable=True),
        sa.Column('scientific_name', sa.String(), nullable=True),
        sa.Column('conservation_status', sa.String(), nullable=True),
        sa.Column('cached_at', sa.TIMESTAMP(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('species_name', 'language', name='uq_species_info_name_lang')
    )

    op.create_index('idx_species_info_name', 'species_info_cache_new', ['species_name'])
    op.create_index('idx_species_info_taxa_id', 'species_info_cache_new', ['taxa_id'])

    # Copy existing data as English
    op.execute(
        """
        INSERT INTO species_info_cache_new
        (id, species_name, language, title, taxa_id, source, source_url, summary_source, summary_source_url,
         description, extract, thumbnail_url, wikipedia_url, scientific_name, conservation_status, cached_at)
        SELECT id, species_name, 'en', title, taxa_id, source, source_url, summary_source, summary_source_url,
               description, extract, thumbnail_url, wikipedia_url, scientific_name, conservation_status, cached_at
        FROM species_info_cache
        """
    )

    op.drop_table('species_info_cache')
    op.rename_table('species_info_cache_new', 'species_info_cache')


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if 'species_info_cache' not in tables:
        return

    op.create_table(
        'species_info_cache_old',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('species_name', sa.String(), nullable=False, unique=True),
        sa.Column('title', sa.String(), nullable=True),
        sa.Column('taxa_id', sa.Integer(), nullable=True),
        sa.Column('source', sa.String(), nullable=True),
        sa.Column('source_url', sa.String(), nullable=True),
        sa.Column('summary_source', sa.String(), nullable=True),
        sa.Column('summary_source_url', sa.String(), nullable=True),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('extract', sa.String(), nullable=True),
        sa.Column('thumbnail_url', sa.String(), nullable=True),
        sa.Column('wikipedia_url', sa.String(), nullable=True),
        sa.Column('scientific_name', sa.String(), nullable=True),
        sa.Column('conservation_status', sa.String(), nullable=True),
        sa.Column('cached_at', sa.TIMESTAMP(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('species_name')
    )
    op.create_index('idx_species_info_name', 'species_info_cache_old', ['species_name'])
    op.create_index('idx_species_info_taxa_id', 'species_info_cache_old', ['taxa_id'])

    op.execute(
        """
        INSERT INTO species_info_cache_old
        (id, species_name, title, taxa_id, source, source_url, summary_source, summary_source_url,
         description, extract, thumbnail_url, wikipedia_url, scientific_name, conservation_status, cached_at)
        SELECT id, species_name, title, taxa_id, source, source_url, summary_source, summary_source_url,
               description, extract, thumbnail_url, wikipedia_url, scientific_name, conservation_status, cached_at
        FROM species_info_cache
        """
    )

    op.drop_table('species_info_cache')
    op.rename_table('species_info_cache_old', 'species_info_cache')
