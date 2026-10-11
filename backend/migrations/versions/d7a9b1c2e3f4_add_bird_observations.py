"""Store counted birds beneath a Frigate capture.

Revision ID: d7a9b1c2e3f4
Revises: c1d2e3f4a5b6
"""

from alembic import op
import sqlalchemy as sa

revision = "d7a9b1c2e3f4"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("bird_observations"):
        op.create_table(
            "bird_observations",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "frigate_event",
                sa.String(),
                sa.ForeignKey("detections.frigate_event", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("bird_index", sa.Integer(), nullable=False),
            sa.Column("candidate_id", sa.String(), nullable=False),
            sa.Column("clip_variant", sa.String(), nullable=False),
            sa.Column("frame_index", sa.Integer(), nullable=False),
            sa.Column("crop_box_json", sa.Text(), nullable=False),
            sa.Column("detector_confidence", sa.Float()),
            sa.Column("species", sa.String(), nullable=False),
            sa.Column("classifier_label", sa.String()),
            sa.Column("classifier_score", sa.Float(), nullable=False),
            sa.Column("manual_species", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("is_hidden", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.UniqueConstraint("frigate_event", "bird_index", name="uq_bird_observations_event_index"),
        )
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("bird_observations")}
    if "ix_bird_observations_event" not in indexes:
        op.create_index("ix_bird_observations_event", "bird_observations", ["frigate_event"])
    if "ix_bird_observations_species" not in indexes:
        op.create_index("ix_bird_observations_species", "bird_observations", ["species"])


def downgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("bird_observations"):
        return
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("bird_observations")}
    if "ix_bird_observations_species" in indexes:
        op.drop_index("ix_bird_observations_species", table_name="bird_observations")
    if "ix_bird_observations_event" in indexes:
        op.drop_index("ix_bird_observations_event", table_name="bird_observations")
    op.drop_table("bird_observations")
