"""add scientific_name to audio_detections

Revision ID: b82b47ae1599
Revises: f9d3e8b4c1a2
Create Date: 2026-02-23 19:13:59.492067

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b82b47ae1599'
down_revision: Union[str, None] = 'f9d3e8b4c1a2'
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
    
    # 1) Additive schema changes
    columns = [c['name'] for c in sa.inspect(bind).get_columns('audio_detections')]
    if 'scientific_name' not in columns:
        with op.batch_alter_table('audio_detections', schema=None) as batch_op:
            batch_op.add_column(sa.Column('scientific_name', sa.String(), nullable=True))
    
    if not _has_index(bind, 'audio_detections', 'idx_audio_detections_scientific'):
        with op.batch_alter_table('audio_detections', schema=None) as batch_op:
            batch_op.create_index('idx_audio_detections_scientific', ['scientific_name'], unique=False)

    # 2) Data backfill (best effort from taxonomy_cache)
    # This joins audio_detections with taxonomy_cache to find scientific names for existing rows
    bind.execute(sa.text("""
        UPDATE audio_detections
        SET scientific_name = (
            SELECT scientific_name 
            FROM taxonomy_cache 
            WHERE LOWER(taxonomy_cache.common_name) = LOWER(audio_detections.species)
               OR LOWER(taxonomy_cache.scientific_name) = LOWER(audio_detections.species)
            LIMIT 1
        )
        WHERE scientific_name IS NULL
    """))

    # 3) Integrity checks
    bind.execute(sa.text("PRAGMA integrity_check"))
    bind.execute(sa.text("PRAGMA foreign_key_check"))


def downgrade() -> None:
    bind = op.get_bind()
    columns = [c['name'] for c in sa.inspect(bind).get_columns('audio_detections')]
    
    if 'scientific_name' in columns:
        if _has_index(bind, 'audio_detections', 'idx_audio_detections_scientific'):
            with op.batch_alter_table('audio_detections', schema=None) as batch_op:
                batch_op.drop_index('idx_audio_detections_scientific')
        
        with op.batch_alter_table('audio_detections', schema=None) as batch_op:
            batch_op.drop_column('scientific_name')
            
    # Integrity checks
    bind.execute(sa.text("PRAGMA integrity_check"))
    bind.execute(sa.text("PRAGMA foreign_key_check"))
