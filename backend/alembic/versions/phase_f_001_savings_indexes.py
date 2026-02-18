"""Add SavingsReport detail columns and core performance indexes

Revision ID: phase_f_001
Revises: phase_e_001
Create Date: 2026-02-18
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "phase_f_001"
down_revision = "phase_e_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SavingsReport detail columns for manager approval view
    op.add_column("savings_reports", sa.Column("per_leg_summary", JSONB, nullable=True))
    op.add_column("savings_reports", sa.Column("alternatives_snapshot", JSONB, nullable=True))
    op.add_column("savings_reports", sa.Column("trip_window_snapshot", JSONB, nullable=True))
    op.add_column("savings_reports", sa.Column("cheaper_months_snapshot", JSONB, nullable=True))

    # Core performance indexes — these tables had zero non-PK indexes
    op.create_index("ix_trips_traveler_id", "trips", ["traveler_id"])
    op.create_index(
        "ix_trips_traveler_status_updated",
        "trips",
        ["traveler_id", "status", "updated_at"],
    )
    op.create_index("ix_trip_legs_trip_id", "trip_legs", ["trip_id"])
    op.create_index(
        "ix_search_logs_leg_searched",
        "search_logs",
        ["trip_leg_id", "searched_at"],
    )
    op.create_index("ix_flight_options_search_log_id", "flight_options", ["search_log_id"])
    op.create_index(
        "ix_flight_options_search_price",
        "flight_options",
        ["search_log_id", "price"],
    )


def downgrade() -> None:
    op.drop_index("ix_flight_options_search_price")
    op.drop_index("ix_flight_options_search_log_id")
    op.drop_index("ix_search_logs_leg_searched")
    op.drop_index("ix_trip_legs_trip_id")
    op.drop_index("ix_trips_traveler_status_updated")
    op.drop_index("ix_trips_traveler_id")
    op.drop_column("savings_reports", "cheaper_months_snapshot")
    op.drop_column("savings_reports", "trip_window_snapshot")
    op.drop_column("savings_reports", "alternatives_snapshot")
    op.drop_column("savings_reports", "per_leg_summary")
