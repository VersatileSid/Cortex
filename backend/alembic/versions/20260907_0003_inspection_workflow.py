"""Persist inspection workflow completion and recoverable failures.

Revision ID: 20260907_0003
Revises: 20260906_0002
"""

from alembic import op
import sqlalchemy as sa

revision = "20260907_0003"
down_revision = "20260906_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("inspections", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("inspections", sa.Column("failure_stage", sa.String(30), nullable=True))
    op.add_column("inspections", sa.Column("failure_message", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("inspections", "failure_message")
    op.drop_column("inspections", "failure_stage")
    op.drop_column("inspections", "completed_at")
