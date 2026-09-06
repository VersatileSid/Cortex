"""Add structured evidence to persisted compliance findings.

Revision ID: 20260906_0002
Revises: 20260903_0001
"""

from alembic import op
import sqlalchemy as sa

revision = "20260906_0002"
down_revision = "20260903_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("compliance_results", sa.Column("field_name", sa.String(100), nullable=True))
    op.add_column("compliance_results", sa.Column("value", sa.Text(), nullable=True))
    op.add_column("compliance_results", sa.Column("confidence", sa.Numeric(5, 4), nullable=True))
    op.add_column("compliance_results", sa.Column("evidence", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("compliance_results", "evidence")
    op.drop_column("compliance_results", "confidence")
    op.drop_column("compliance_results", "value")
    op.drop_column("compliance_results", "field_name")
