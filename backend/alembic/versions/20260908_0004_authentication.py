"""Add usernames and server-side login sessions.

Revision ID: 20260908_0004
Revises: 20260907_0003
"""
from alembic import op
import sqlalchemy as sa

revision = "20260908_0004"
down_revision = "20260907_0003"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("users", sa.Column("username", sa.String(100), nullable=True))
    op.add_column("inspections", sa.Column("user_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_inspections_user_id_users", "inspections", "users", ["user_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_inspections_user_id", "inspections", ["user_id"])
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_table("auth_sessions", sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.Column("token_hash", sa.String(64), nullable=False), sa.Column("user_id", sa.Uuid(), nullable=False), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"), sa.UniqueConstraint("token_hash"))
    op.create_index("ix_auth_sessions_token_hash", "auth_sessions", ["token_hash"])
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])

def downgrade() -> None:
    op.drop_table("auth_sessions"); op.drop_index("ix_users_username", table_name="users"); op.drop_index("ix_inspections_user_id", table_name="inspections"); op.drop_column("inspections", "user_id"); op.drop_column("users", "username")
