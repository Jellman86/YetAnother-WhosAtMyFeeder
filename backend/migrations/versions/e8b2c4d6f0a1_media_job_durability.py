"""Own derived media records by visit and retain maintenance summaries.

Revision ID: e8b2c4d6f0a1
Revises: d7a9b1c2e3f4

Only orphaned derived photo/frame references are pruned. Detection history,
favourites, and files are preserved. Downgrade removes the added schema.
"""

from alembic import op
import sqlalchemy as sa

revision = "e8b2c4d6f0a1"
down_revision = "d7a9b1c2e3f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "revision" not in {column["name"] for column in inspector.get_columns("processing_job_state")}:
        with op.batch_alter_table("processing_job_state") as batch:
            batch.add_column(sa.Column("revision", sa.Integer(), nullable=False, server_default="0"))
    for table in ("snapshot_candidates", "video_classification_top_frames"):
        if inspector.has_table(table):
            op.execute(
                f"DELETE FROM {table} WHERE NOT EXISTS (SELECT 1 FROM detections d WHERE d.frigate_event = {table}.frigate_event)"
            )
            for action in ("INSERT", "UPDATE OF frigate_event"):
                trigger_action = "insert" if action == "INSERT" else "update"
                op.execute(
                    f"CREATE TRIGGER IF NOT EXISTS guard_{table}_{trigger_action} BEFORE {action} ON {table} WHEN NOT EXISTS (SELECT 1 FROM detections WHERE frigate_event=NEW.frigate_event) BEGIN SELECT RAISE(ABORT, 'media visit does not exist'); END"
                )
            op.execute(
                f"CREATE TRIGGER IF NOT EXISTS delete_{table}_with_visit AFTER DELETE ON detections BEGIN DELETE FROM {table} WHERE frigate_event = OLD.frigate_event; END"
            )
    if not inspector.has_table("maintenance_job_history"):
        op.create_table(
            "maintenance_job_history",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("kind", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("payload_json", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("maintenance_job_history")}
    if "ix_maintenance_job_kind_updated" not in indexes:
        op.create_index("ix_maintenance_job_kind_updated", "maintenance_job_history", ["kind", "updated_at"])


def downgrade() -> None:
    with op.batch_alter_table("processing_job_state") as batch:
        batch.drop_column("revision")
    for table in ("snapshot_candidates", "video_classification_top_frames"):
        op.execute(f"DROP TRIGGER IF EXISTS delete_{table}_with_visit")
        for action in ("insert", "update"):
            op.execute(f"DROP TRIGGER IF EXISTS guard_{table}_{action}")
    if sa.inspect(op.get_bind()).has_table("maintenance_job_history"):
        op.drop_table("maintenance_job_history")
