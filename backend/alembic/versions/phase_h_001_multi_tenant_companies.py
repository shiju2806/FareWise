"""Phase H-1: Multi-tenant companies — create companies table and add company_id FK to tenant-scoped tables.

Revision ID: phase_h_001
Revises: phase_g_002
Create Date: 2026-04-19

Strategy (safe for existing single-tenant data):
    1. Create `companies` table.
    2. Insert a "Default" company row and capture its UUID.
    3. For each tenant-scoped table, add `company_id` as NULLABLE with an FK.
    4. Backfill every existing row to the Default company.
    5. ALTER COLUMN company_id SET NOT NULL.

Tables gaining company_id in this migration:
    users, trips, policies, analytics_snapshots, traveler_scores, trip_overlaps

Notes:
    - trip_legs, selections, approvals, savings_reports, policy_violations,
      approval_history, notifications all inherit tenancy via FK chains to the
      tables above — no denormalized company_id on them (yet).
    - hotel_rate, event_cache, price_watch, agent_finding, nearby_airport are
      global market data or WIP and intentionally untouched.
"""
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "phase_h_001"
down_revision = "phase_g_002"
branch_labels = None
depends_on = None


TENANT_TABLES = (
    "users",
    "trips",
    "policies",
    "analytics_snapshots",
    "traveler_scores",
    "trip_overlaps",
)


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False, unique=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("allowed_airlines", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column("cohort_overrides", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column("credit_budget_monthly", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    default_id = uuid.uuid4()
    op.execute(
        sa.text(
            "INSERT INTO companies (id, name, slug, is_active) "
            "VALUES (:id, 'Default', 'default', TRUE)"
        ).bindparams(id=default_id)
    )

    for table in TENANT_TABLES:
        op.add_column(
            table,
            sa.Column("company_id", UUID(as_uuid=True), nullable=True),
        )
        op.execute(
            sa.text(f"UPDATE {table} SET company_id = :cid WHERE company_id IS NULL").bindparams(
                cid=default_id
            )
        )
        op.alter_column(table, "company_id", nullable=False)
        op.create_foreign_key(
            f"fk_{table}_company_id",
            table,
            "companies",
            ["company_id"],
            ["id"],
        )
        op.create_index(f"ix_{table}_company_id", table, ["company_id"])


def downgrade() -> None:
    for table in TENANT_TABLES:
        op.drop_index(f"ix_{table}_company_id", table_name=table)
        op.drop_constraint(f"fk_{table}_company_id", table, type_="foreignkey")
        op.drop_column(table, "company_id")
    op.drop_table("companies")
