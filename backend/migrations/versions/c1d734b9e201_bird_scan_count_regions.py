"""Retain count completeness and uncounted regions on their immutable scene.

Existing scans stay legacy results. Downgrade removes only the new qualification
metadata; scan jobs, bird observations and owner corrections remain intact.

Revision ID: c1d734b9e201
Revises: b8230ca9d42c
"""

from alembic import op
import sqlalchemy as sa

revision = "c1d734b9e201"
down_revision = "b8230ca9d42c"
branch_labels = None
depends_on = None

TABLE = "bird_scan_jobs"
STATUS_CHECK = "ck_bird_scan_count_status"
REGIONS_CHECK = "ck_bird_scan_count_regions"


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns(TABLE)}
    checks = {check["name"] for check in inspector.get_check_constraints(TABLE)}
    if {"count_status", "count_regions_json"} <= columns and {STATUS_CHECK, REGIONS_CHECK} <= checks:
        return
    with op.batch_alter_table(TABLE, recreate="always") as batch:
        if "count_status" not in columns:
            batch.add_column(sa.Column("count_status", sa.String(16), nullable=False, server_default="legacy"))
        if "count_regions_json" not in columns:
            batch.add_column(sa.Column("count_regions_json", sa.Text(), nullable=False, server_default="[]"))
        if STATUS_CHECK not in checks:
            batch.create_check_constraint(
                STATUS_CHECK, "count_status IN ('legacy','complete','incomplete','ambiguous','not_measured')"
            )
        if REGIONS_CHECK not in checks:
            batch.create_check_constraint(
                REGIONS_CHECK, "json_valid(count_regions_json) AND json_type(count_regions_json) = 'array'"
            )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns(TABLE)}
    checks = {check["name"] for check in inspector.get_check_constraints(TABLE)}
    if not {"count_status", "count_regions_json"}.intersection(columns):
        return
    with op.batch_alter_table(TABLE, recreate="always") as batch:
        for name in (STATUS_CHECK, REGIONS_CHECK):
            if name in checks:
                batch.drop_constraint(name, type_="check")
        for name in ("count_status", "count_regions_json"):
            if name in columns:
                batch.drop_column(name)
