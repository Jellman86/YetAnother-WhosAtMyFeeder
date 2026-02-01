"""Add detailed weather columns to detections.

Revision ID: c6d1a2b3e4f5
Revises: f4c9d2a1b0e9
Create Date: 2026-01-31 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c6d1a2b3e4f5"
down_revision = "f4c9d2a1b0e9"
branch_labels = None
depends_on = None


def _get_columns(conn) -> set[str]:
    rows = conn.execute(sa.text("PRAGMA table_info(detections)")).fetchall()
    return {row[1] for row in rows}


def upgrade() -> None:
    conn = op.get_bind()
    columns = _get_columns(conn)
    additions = [
        ("weather_cloud_cover", sa.Float()),
        ("weather_wind_speed", sa.Float()),
        ("weather_wind_direction", sa.Float()),
        ("weather_precipitation", sa.Float()),
        ("weather_rain", sa.Float()),
        ("weather_snowfall", sa.Float()),
    ]

    for name, coltype in additions:
        if name not in columns:
            op.add_column("detections", sa.Column(name, coltype))


def downgrade() -> None:
    conn = op.get_bind()
    columns = _get_columns(conn)
    removals = [
        "weather_cloud_cover",
        "weather_wind_speed",
        "weather_wind_direction",
        "weather_precipitation",
        "weather_rain",
        "weather_snowfall",
    ]

    with op.batch_alter_table("detections", schema=None) as batch_op:
        for name in removals:
            if name in columns:
                batch_op.drop_column(name)
