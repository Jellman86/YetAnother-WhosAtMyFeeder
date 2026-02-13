"""Add ai_conversation_turns table.

Revision ID: c9d2e3f4a5b6
Revises: b7c1a2d3e4f5
Create Date: 2026-02-07 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "c9d2e3f4a5b6"
down_revision = "b7c1a2d3e4f5"
branch_labels = None
depends_on = None


def _table_exists(conn, name: str) -> bool:
    rows = conn.execute(
        sa.text("SELECT name FROM sqlite_master WHERE type='table' AND name=:name"),
        {"name": name},
    ).fetchall()
    return bool(rows)


def _index_exists(conn, table: str, name: str) -> bool:
    rows = conn.execute(sa.text(f"PRAGMA index_list({table})")).fetchall()
    return any(row[1] == name for row in rows)


def upgrade() -> None:
    conn = op.get_bind()
    if not _table_exists(conn, "ai_conversation_turns"):
        op.create_table(
            "ai_conversation_turns",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("frigate_event", sa.String(), nullable=False),
            sa.Column("role", sa.String(), nullable=False),
            sa.Column("content", sa.String(), nullable=False),
            sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        )

    if _table_exists(conn, "ai_conversation_turns") and not _index_exists(conn, "ai_conversation_turns", "idx_ai_conversation_event"):
        op.create_index("idx_ai_conversation_event", "ai_conversation_turns", ["frigate_event"])
    if _table_exists(conn, "ai_conversation_turns") and not _index_exists(conn, "ai_conversation_turns", "idx_ai_conversation_created"):
        op.create_index("idx_ai_conversation_created", "ai_conversation_turns", ["created_at"])


def downgrade() -> None:
    conn = op.get_bind()
    if _table_exists(conn, "ai_conversation_turns"):
        if _index_exists(conn, "ai_conversation_turns", "idx_ai_conversation_created"):
            op.drop_index("idx_ai_conversation_created", table_name="ai_conversation_turns")
        if _index_exists(conn, "ai_conversation_turns", "idx_ai_conversation_event"):
            op.drop_index("idx_ai_conversation_event", table_name="ai_conversation_turns")
        op.drop_table("ai_conversation_turns")
