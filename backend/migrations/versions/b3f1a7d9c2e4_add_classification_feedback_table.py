"""add classification_feedback table

Revision ID: b3f1a7d9c2e4
Revises: cc180b75ba56
Create Date: 2026-02-27 12:28:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b3f1a7d9c2e4"
down_revision: Union[str, None] = "cc180b75ba56"
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
    return any(idx["name"] == index_name for idx in indexes)


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_table(bind, "classification_feedback"):
        op.create_table(
            "classification_feedback",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
            sa.Column("frigate_event", sa.String(), nullable=True),
            sa.Column("camera_name", sa.String(), nullable=False),
            sa.Column("model_id", sa.String(), nullable=False),
            sa.Column("predicted_label", sa.String(), nullable=False),
            sa.Column("corrected_label", sa.String(), nullable=False),
            sa.Column("predicted_score", sa.Float(), nullable=True),
            sa.Column("source", sa.String(), server_default="manual_tag", nullable=False),
        )

    if not _has_index(bind, "classification_feedback", "idx_classification_feedback_camera_model_time"):
        with op.batch_alter_table("classification_feedback", schema=None) as batch_op:
            batch_op.create_index(
                "idx_classification_feedback_camera_model_time",
                ["camera_name", "model_id", "created_at"],
                unique=False,
            )

    if not _has_index(bind, "classification_feedback", "idx_classification_feedback_camera_model_predicted_time"):
        with op.batch_alter_table("classification_feedback", schema=None) as batch_op:
            batch_op.create_index(
                "idx_classification_feedback_camera_model_predicted_time",
                ["camera_name", "model_id", "predicted_label", "created_at"],
                unique=False,
            )

    bind.execute(sa.text("PRAGMA integrity_check"))
    bind.execute(sa.text("PRAGMA foreign_key_check"))


def downgrade() -> None:
    bind = op.get_bind()

    if _has_index(bind, "classification_feedback", "idx_classification_feedback_camera_model_predicted_time"):
        with op.batch_alter_table("classification_feedback", schema=None) as batch_op:
            batch_op.drop_index("idx_classification_feedback_camera_model_predicted_time")

    if _has_index(bind, "classification_feedback", "idx_classification_feedback_camera_model_time"):
        with op.batch_alter_table("classification_feedback", schema=None) as batch_op:
            batch_op.drop_index("idx_classification_feedback_camera_model_time")

    if _has_table(bind, "classification_feedback"):
        op.drop_table("classification_feedback")

    bind.execute(sa.text("PRAGMA integrity_check"))
    bind.execute(sa.text("PRAGMA foreign_key_check"))
