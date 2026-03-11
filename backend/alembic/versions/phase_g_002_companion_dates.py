"""Phase G-2: Add companion_preferred_date to TripLeg

Revision ID: phase_g_002
Revises: phase_g_001
Create Date: 2026-03-06
"""
from alembic import op
import sqlalchemy as sa

revision = "phase_g_002"
down_revision = "phase_g_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trip_legs", sa.Column("companion_preferred_date", sa.Date, nullable=True))


def downgrade() -> None:
    op.drop_column("trip_legs", "companion_preferred_date")
