"""Keep automatic Garden assessments separate from owner decisions.

Revision ID: b72d91a4e630
Revises: a21e40b5c610
"""

from alembic import op
import sqlalchemy as sa

revision = "b72d91a4e630"
down_revision = "a21e40b5c610"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "automation_overridden" not in {c["name"] for c in sa.inspect(bind).get_columns("garden_captures")}:
        op.add_column(
            "garden_captures",
            sa.Column("automation_overridden", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        # Prior reviews are owner decisions, including a restored pending photo.
        op.execute("UPDATE garden_captures SET automation_overridden=1")
    if "garden_automatic_checks" not in sa.inspect(bind).get_table_names():
        op.create_table(
            "garden_automatic_checks",
            sa.Column("capture_id", sa.String(32), primary_key=True),
            sa.Column("result_json", sa.Text(), nullable=False),
            sa.ForeignKeyConstraint(["capture_id"], ["garden_captures.id"], ondelete="CASCADE"),
            sa.CheckConstraint("json_valid(result_json)", name="ck_garden_automatic_check_json"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if "garden_automatic_checks" in sa.inspect(bind).get_table_names():
        # Return untouched automatic dismissals to review on rollback. Explicit
        # owner decisions and confirmations survive, as do all retained photos.
        op.execute("""UPDATE garden_captures SET status='pending' WHERE status='dismissed'
                   AND automation_overridden=0 AND id IN (SELECT capture_id FROM garden_automatic_checks)""")
        op.drop_table("garden_automatic_checks")
    if "automation_overridden" in {c["name"] for c in sa.inspect(bind).get_columns("garden_captures")}:
        op.drop_column("garden_captures", "automation_overridden")
