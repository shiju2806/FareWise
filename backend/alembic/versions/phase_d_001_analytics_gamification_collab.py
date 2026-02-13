"""Phase D: analytics snapshots, traveler scores, trip overlaps, group trips

Revision ID: phase_d_001
Revises: phase_c_001
Create Date: 2026-02-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "phase_d_001"
down_revision = "phase_c_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- analytics_snapshots ---
    op.create_table(
        "analytics_snapshots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("snapshot_type", sa.String(50), nullable=False),
        sa.Column("period_start", sa.Date, nullable=False),
        sa.Column("period_end", sa.Date, nullable=False),
        sa.Column("metrics", JSONB, nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_analytics_snapshots_type_period", "analytics_snapshots", ["snapshot_type", "period_start"])

    # --- traveler_scores ---
    op.create_table(
        "traveler_scores",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("period", sa.String(20), nullable=False),
        sa.Column("period_start", sa.Date, nullable=False),
        sa.Column("total_trips", sa.Integer, server_default="0"),
        sa.Column("total_spend", sa.Numeric(12, 2), server_default="0"),
        sa.Column("total_savings", sa.Numeric(12, 2), server_default="0"),
        sa.Column("smart_savings", sa.Numeric(12, 2), server_default="0"),
        sa.Column("policy_compliance_rate", sa.Numeric(4, 3), server_default="1.0"),
        sa.Column("avg_advance_booking_days", sa.Numeric(5, 1), server_default="0"),
        sa.Column("avg_slider_position", sa.Numeric(4, 1), server_default="50"),
        sa.Column("score", sa.Integer, server_default="0"),
        sa.Column("rank_in_department", sa.Integer, nullable=True),
        sa.Column("rank_in_company", sa.Integer, nullable=True),
        sa.Column("badges", JSONB, server_default="[]"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_traveler_scores_user_period", "traveler_scores", ["user_id", "period", "period_start"], unique=True)

    # --- trip_overlaps ---
    op.create_table(
        "trip_overlaps",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("trip_a_id", UUID(as_uuid=True), sa.ForeignKey("trips.id"), nullable=False),
        sa.Column("trip_b_id", UUID(as_uuid=True), sa.ForeignKey("trips.id"), nullable=False),
        sa.Column("overlap_city", sa.String(100), nullable=False),
        sa.Column("overlap_start", sa.Date, nullable=False),
        sa.Column("overlap_end", sa.Date, nullable=False),
        sa.Column("overlap_days", sa.Integer, nullable=False),
        sa.Column("notified", sa.Boolean, server_default="false"),
        sa.Column("dismissed_by_a", sa.Boolean, server_default="false"),
        sa.Column("dismissed_by_b", sa.Boolean, server_default="false"),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_trip_overlaps_trips", "trip_overlaps", ["trip_a_id", "trip_b_id"], unique=True)

    # --- group_trips ---
    op.create_table(
        "group_trips",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("organizer_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("destination_city", sa.String(100), nullable=False),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("end_date", sa.Date, nullable=False),
        sa.Column("status", sa.String(20), server_default="'planning'"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- group_trip_members ---
    op.create_table(
        "group_trip_members",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("group_trip_id", UUID(as_uuid=True), sa.ForeignKey("group_trips.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("trip_id", UUID(as_uuid=True), sa.ForeignKey("trips.id"), nullable=True),
        sa.Column("role", sa.String(20), server_default="'member'"),
        sa.Column("status", sa.String(20), server_default="'invited'"),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_group_trip_members_unique", "group_trip_members", ["group_trip_id", "user_id"], unique=True)


def downgrade() -> None:
    op.drop_table("group_trip_members")
    op.drop_table("group_trips")
    op.drop_table("trip_overlaps")
    op.drop_table("traveler_scores")
    op.drop_table("analytics_snapshots")
