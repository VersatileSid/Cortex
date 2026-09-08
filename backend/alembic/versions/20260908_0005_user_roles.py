"""Normalize legacy user roles and store optional official organization.

Revision ID: 20260908_0005
Revises: 20260908_0004
"""
from alembic import op
import sqlalchemy as sa

revision = "20260908_0005"
down_revision = "20260908_0004"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("users", sa.Column("organization", sa.String(200), nullable=True))
    op.execute("UPDATE users SET role = 'OFFICIAL' WHERE role IS NULL OR role NOT IN ('OFFICIAL', 'MANUFACTURER')")
    op.alter_column("users", "role", existing_type=sa.String(50), server_default="OFFICIAL", nullable=False)

def downgrade() -> None:
    op.alter_column("users", "role", existing_type=sa.String(50), server_default=None)
    op.drop_column("users", "organization")
