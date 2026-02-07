"""add_leaderboard_ai_analysis

Revision ID: d1f2c3b4a5b6
Revises: c6d1a2b3e4f5
Create Date: 2026-02-01
"""

from alembic import op
import sqlalchemy as sa

revision = 'd1f2c3b4a5b6'
down_revision = 'c6d1a2b3e4f5'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    exists = conn.execute(
        sa.text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='leaderboard_analyses'")
    ).fetchone()
    if not exists:
        op.create_table(
            'leaderboard_analyses',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('config_key', sa.String(), nullable=False, unique=True),
            sa.Column('config_json', sa.Text(), nullable=False),
            sa.Column('analysis', sa.Text(), nullable=False),
            sa.Column('analysis_timestamp', sa.TIMESTAMP(), nullable=False),
            sa.Column('created_at', sa.TIMESTAMP(), nullable=False)
        )


def downgrade():
    op.execute("DROP TABLE IF EXISTS leaderboard_analyses")
