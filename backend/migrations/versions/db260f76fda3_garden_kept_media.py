"""Record the full photograph and clip YA-WAMF keeps for a confirmed Garden animal.

The bytes live under the media cache's garden folder, named by capture ID. This
table is the authority: a file without a row here is never served and is swept.

Revision ID: db260f76fda3
Revises: 7fa03c365538
"""

from alembic import op
import sqlalchemy as sa

revision = "db260f76fda3"
down_revision = "7fa03c365538"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "garden_kept_media" not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(
            "garden_kept_media",
            sa.Column(
                "capture_id", sa.String(32), sa.ForeignKey("garden_captures.id", ondelete="CASCADE"), primary_key=True
            ),
            sa.Column("photo_state", sa.String(16), nullable=False),
            sa.Column("photo_source", sa.String(20), nullable=True),
            sa.Column("photo_sha256", sa.String(64), nullable=True),
            sa.Column("photo_bytes", sa.Integer(), nullable=True),
            sa.Column("clip_state", sa.String(16), nullable=True),
            sa.Column("clip_sha256", sa.String(64), nullable=True),
            sa.Column("clip_bytes", sa.Integer(), nullable=True),
            # The recording span the media covers, so a later person event erases it as it does crops.
            sa.Column("source_start", sa.Float(), nullable=True),
            sa.Column("source_end", sa.Float(), nullable=True),
            sa.Column("retry_after", sa.String(), nullable=True),
            sa.Column("updated_at", sa.String(), nullable=False),
            sa.CheckConstraint(
                "photo_state IN ('kept','retry','missing','changed','evicted')", name="ck_garden_kept_photo_state"
            ),
            sa.CheckConstraint(
                "clip_state IS NULL OR clip_state IN ('kept','retry','missing','evicted')",
                name="ck_garden_kept_clip_state",
            ),
            sa.CheckConstraint(
                "(photo_state='kept' AND COALESCE(photo_source, '') IN ('frigate_snapshot','motion_photo')"
                " AND COALESCE(length(photo_sha256), 0)=64 AND COALESCE(photo_bytes, 0) > 0)"
                " OR (photo_state!='kept' AND photo_sha256 IS NULL AND photo_bytes IS NULL)",
                name="ck_garden_kept_photo",
            ),
            sa.CheckConstraint(
                "(clip_state='kept' AND COALESCE(length(clip_sha256), 0)=64 AND COALESCE(clip_bytes, 0) > 0)"
                " OR (clip_state IS NOT 'kept' AND clip_sha256 IS NULL AND clip_bytes IS NULL)",
                name="ck_garden_kept_clip",
            ),
        )


def downgrade() -> None:
    # Files already kept under media_cache/garden stay on disk until the folder is removed;
    # without this table no version of YA-WAMF serves them.
    if "garden_kept_media" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("garden_kept_media")
