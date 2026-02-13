"""Phase C: events, hotels, price watches tables + schema mods

Revision ID: phase_c_001
Revises: phase_b_001
Create Date: 2026-02-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "phase_c_001"
down_revision = "phase_b_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- events_cache ---
    op.create_table(
        "events_cache",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("external_id", sa.String(100), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("labels", JSONB, server_default="[]"),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("end_date", sa.Date, nullable=False),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("country", sa.String(10)),
        sa.Column("latitude", sa.Numeric(9, 6)),
        sa.Column("longitude", sa.Numeric(9, 6)),
        sa.Column("venue_name", sa.String(300)),
        sa.Column("rank", sa.Integer),
        sa.Column("local_rank", sa.Integer),
        sa.Column("phq_attendance", sa.Integer),
        sa.Column("demand_impact", JSONB),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_events_city_date", "events_cache", ["city", "start_date", "end_date"])
    op.create_index("idx_events_expires", "events_cache", ["expires_at"])
    op.create_index("idx_events_external", "events_cache", ["external_id"], unique=True)

    # --- hotel_searches ---
    op.create_table(
        "hotel_searches",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("trip_leg_id", UUID(as_uuid=True), sa.ForeignKey("trip_legs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("check_in", sa.Date, nullable=False),
        sa.Column("check_out", sa.Date, nullable=False),
        sa.Column("guests", sa.Integer, server_default="1"),
        sa.Column("search_params", JSONB, nullable=False),
        sa.Column("results_count", sa.Integer),
        sa.Column("cheapest_rate", sa.Numeric(10, 2)),
        sa.Column("most_expensive_rate", sa.Numeric(10, 2)),
        sa.Column("cached", sa.Boolean, server_default="false"),
        sa.Column("searched_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- hotel_options ---
    op.create_table(
        "hotel_options",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("hotel_search_id", UUID(as_uuid=True), sa.ForeignKey("hotel_searches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("hotel_name", sa.String(300), nullable=False),
        sa.Column("hotel_chain", sa.String(100)),
        sa.Column("star_rating", sa.Numeric(2, 1)),
        sa.Column("user_rating", sa.Numeric(2, 1)),
        sa.Column("address", sa.String(500)),
        sa.Column("latitude", sa.Numeric(9, 6)),
        sa.Column("longitude", sa.Numeric(9, 6)),
        sa.Column("distance_km", sa.Numeric(5, 2)),
        sa.Column("nightly_rate", sa.Numeric(10, 2), nullable=False),
        sa.Column("total_rate", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(3), server_default="CAD"),
        sa.Column("room_type", sa.String(100)),
        sa.Column("amenities", JSONB, server_default="[]"),
        sa.Column("cancellation_policy", sa.String(50)),
        sa.Column("is_preferred_vendor", sa.Boolean, server_default="false"),
        sa.Column("raw_response", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_hotel_options_search", "hotel_options", ["hotel_search_id"])
    op.create_index("idx_hotel_options_rate", "hotel_options", ["nightly_rate"])

    # --- hotel_selections ---
    op.create_table(
        "hotel_selections",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("trip_leg_id", UUID(as_uuid=True), sa.ForeignKey("trip_legs.id"), nullable=False),
        sa.Column("hotel_option_id", UUID(as_uuid=True), sa.ForeignKey("hotel_options.id"), nullable=False),
        sa.Column("check_in", sa.Date, nullable=False),
        sa.Column("check_out", sa.Date, nullable=False),
        sa.Column("justification_note", sa.Text),
        sa.Column("selected_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- price_watches ---
    op.create_table(
        "price_watches",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("watch_type", sa.String(20), nullable=False),
        sa.Column("origin", sa.String(10)),
        sa.Column("destination", sa.String(10)),
        sa.Column("target_date", sa.Date, nullable=False),
        sa.Column("flexibility_days", sa.Integer, server_default="3"),
        sa.Column("target_price", sa.Numeric(10, 2)),
        sa.Column("current_best_price", sa.Numeric(10, 2)),
        sa.Column("cabin_class", sa.String(20), server_default="'economy'"),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("last_checked_at", sa.DateTime(timezone=True)),
        sa.Column("alert_count", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_price_watches_active", "price_watches", ["is_active", "last_checked_at"])
    op.create_index("idx_price_watches_user", "price_watches", ["user_id"])

    # --- price_watch_history ---
    op.create_table(
        "price_watch_history",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("price_watch_id", UUID(as_uuid=True), sa.ForeignKey("price_watches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_watch_history", "price_watch_history", ["price_watch_id", "checked_at"])

    # --- Schema modifications to existing tables ---

    # trip_legs: add hotel fields
    op.add_column("trip_legs", sa.Column("needs_hotel", sa.Boolean, server_default="false"))
    op.add_column("trip_legs", sa.Column("hotel_check_in", sa.Date))
    op.add_column("trip_legs", sa.Column("hotel_check_out", sa.Date))
    op.add_column("trip_legs", sa.Column("hotel_guests", sa.Integer, server_default="1"))
    op.add_column("trip_legs", sa.Column("hotel_max_stars", sa.Numeric(2, 1)))

    # savings_reports: add hotel + event data
    op.add_column("savings_reports", sa.Column("hotel_selected_total", sa.Numeric(10, 2)))
    op.add_column("savings_reports", sa.Column("hotel_cheapest_total", sa.Numeric(10, 2)))
    op.add_column("savings_reports", sa.Column("bundle_savings", sa.Numeric(10, 2)))
    op.add_column("savings_reports", sa.Column("events_impacting_price", JSONB, server_default="[]"))

    # search_logs: add event context
    op.add_column("search_logs", sa.Column("events_during_travel", JSONB, server_default="[]"))


def downgrade() -> None:
    op.drop_column("search_logs", "events_during_travel")
    op.drop_column("savings_reports", "events_impacting_price")
    op.drop_column("savings_reports", "bundle_savings")
    op.drop_column("savings_reports", "hotel_cheapest_total")
    op.drop_column("savings_reports", "hotel_selected_total")
    op.drop_column("trip_legs", "hotel_max_stars")
    op.drop_column("trip_legs", "hotel_guests")
    op.drop_column("trip_legs", "hotel_check_out")
    op.drop_column("trip_legs", "hotel_check_in")
    op.drop_column("trip_legs", "needs_hotel")

    op.drop_table("price_watch_history")
    op.drop_table("price_watches")
    op.drop_table("hotel_selections")
    op.drop_table("hotel_options")
    op.drop_table("hotel_searches")
    op.drop_table("events_cache")
