"""Add travel_preferences JSONB column to users table

Revision ID: phase_e_001
Revises: phase_d_001
Create Date: 2026-02-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "phase_e_001"
down_revision = "phase_d_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("travel_preferences", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("users", "travel_preferences")
