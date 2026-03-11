"""Phase G-1: Add companion pricing snapshot to SavingsReport

Revision ID: phase_g_001
Revises: phase_f_001
Create Date: 2026-03-06
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "phase_g_001"
down_revision = "phase_f_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("savings_reports", sa.Column("companion_snapshot", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("savings_reports", "companion_snapshot")
