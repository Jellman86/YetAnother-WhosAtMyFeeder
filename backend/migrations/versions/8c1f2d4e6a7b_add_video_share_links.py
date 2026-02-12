"""Add expiring video share links table.

Revision ID: 8c1f2d4e6a7b
Revises: a3d9c1e7b5f2
Create Date: 2026-02-12 21:05:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "8c1f2d4e6a7b"
down_revision = "a3d9c1e7b5f2"
branch_labels = None
depends_on = None


def _table_exists(conn, name: str) -> bool:
    return (
        conn.execute(
            sa.text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:name"),
            {"name": name},
        ).fetchone()
        is not None
    )


def _index_names(conn, table: str) -> set[str]:
    rows = conn.execute(sa.text(f"PRAGMA index_list({table})")).fetchall()
    return {row[1] for row in rows}


def upgrade() -> None:
    conn = op.get_bind()

    if not _table_exists(conn, "video_share_links"):
        op.create_table(
            "video_share_links",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("token_hash", sa.String(), nullable=False, unique=True),
            sa.Column("frigate_event", sa.String(), nullable=False),
            sa.Column("created_by", sa.String(), nullable=True),
            sa.Column("watermark_label", sa.String(), nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
            sa.Column("expires_at", sa.TIMESTAMP(), nullable=False),
            sa.Column("revoked", sa.Boolean(), server_default="0", nullable=False),
        )

    indexes = _index_names(conn, "video_share_links")
    if "ix_video_share_links_token_hash" not in indexes:
        op.create_index(
            "ix_video_share_links_token_hash",
            "video_share_links",
            ["token_hash"],
            unique=False,
        )
    if "ix_video_share_links_event" not in indexes:
        op.create_index(
            "ix_video_share_links_event",
            "video_share_links",
            ["frigate_event"],
            unique=False,
        )
    if "ix_video_share_links_expires_at" not in indexes:
        op.create_index(
            "ix_video_share_links_expires_at",
            "video_share_links",
            ["expires_at"],
            unique=False,
        )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_video_share_links_expires_at")
    op.execute("DROP INDEX IF EXISTS ix_video_share_links_event")
    op.execute("DROP INDEX IF EXISTS ix_video_share_links_token_hash")
    op.execute("DROP TABLE IF EXISTS video_share_links")
