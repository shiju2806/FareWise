"""Phase B: Policy engine, approvals, savings, notifications

Revision ID: phase_b_001
Revises: 19210203a29b
Create Date: 2026-02-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'phase_b_001'
down_revision: Union[str, None] = '19210203a29b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Expand policies table ---
    op.add_column('policies', sa.Column('description', sa.Text(), nullable=True))
    op.add_column('policies', sa.Column('severity', sa.Integer(), nullable=False, server_default='5'))
    op.add_column('policies', sa.Column('exception_roles', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='[]'))
    op.add_column('policies', sa.Column('created_by', sa.UUID(), nullable=True))
    op.add_column('policies', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.create_foreign_key('fk_policies_created_by', 'policies', 'users', ['created_by'], ['id'])

    # --- Expand trips table ---
    op.add_column('trips', sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('trips', sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('trips', sa.Column('rejected_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('trips', sa.Column('rejection_reason', sa.Text(), nullable=True))

    # --- Create approvals table ---
    op.create_table('approvals',
        sa.Column('id', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('trip_id', sa.UUID(), nullable=False),
        sa.Column('approver_id', sa.UUID(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('comments', sa.Text(), nullable=True),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('escalated_from', sa.UUID(), nullable=True),
        sa.Column('escalation_reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['trip_id'], ['trips.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['approver_id'], ['users.id']),
        sa.ForeignKeyConstraint(['escalated_from'], ['approvals.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_approvals_trip', 'approvals', ['trip_id'])
    op.create_index('idx_approvals_approver', 'approvals', ['approver_id', 'status'])

    # --- Create savings_reports table ---
    op.create_table('savings_reports',
        sa.Column('id', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('trip_id', sa.UUID(), nullable=False),
        sa.Column('selected_total', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('cheapest_total', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('most_expensive_total', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('policy_limit_total', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('savings_vs_expensive', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('premium_vs_cheapest', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('narrative', sa.Text(), nullable=False),
        sa.Column('narrative_html', sa.Text(), nullable=True),
        sa.Column('policy_status', sa.String(length=20), nullable=False),
        sa.Column('policy_checks', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('slider_positions', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('generated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['trip_id'], ['trips.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    # --- Create policy_violations table ---
    op.create_table('policy_violations',
        sa.Column('id', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('trip_id', sa.UUID(), nullable=False),
        sa.Column('trip_leg_id', sa.UUID(), nullable=True),
        sa.Column('policy_id', sa.UUID(), nullable=False),
        sa.Column('violation_type', sa.String(length=20), nullable=False),
        sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('traveler_justification', sa.Text(), nullable=True),
        sa.Column('resolved', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('resolved_by', sa.UUID(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['trip_id'], ['trips.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['trip_leg_id'], ['trip_legs.id']),
        sa.ForeignKeyConstraint(['policy_id'], ['policies.id']),
        sa.ForeignKeyConstraint(['resolved_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_violations_trip', 'policy_violations', ['trip_id'])

    # --- Create approval_history table ---
    op.create_table('approval_history',
        sa.Column('id', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('approval_id', sa.UUID(), nullable=False),
        sa.Column('action', sa.String(length=30), nullable=False),
        sa.Column('actor_id', sa.UUID(), nullable=False),
        sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['approval_id'], ['approvals.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['actor_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_approval_history', 'approval_history', ['approval_id'])

    # --- Create notifications table ---
    op.create_table('notifications',
        sa.Column('id', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('type', sa.String(length=50), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('reference_type', sa.String(length=50), nullable=True),
        sa.Column('reference_id', sa.UUID(), nullable=True),
        sa.Column('is_read', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_notifications_user', 'notifications', ['user_id', 'is_read'])


def downgrade() -> None:
    op.drop_table('notifications')
    op.drop_table('approval_history')
    op.drop_table('policy_violations')
    op.drop_table('savings_reports')
    op.drop_table('approvals')

    op.drop_column('trips', 'rejection_reason')
    op.drop_column('trips', 'rejected_at')
    op.drop_column('trips', 'approved_at')
    op.drop_column('trips', 'submitted_at')

    op.drop_constraint('fk_policies_created_by', 'policies', type_='foreignkey')
    op.drop_column('policies', 'updated_at')
    op.drop_column('policies', 'created_by')
    op.drop_column('policies', 'exception_roles')
    op.drop_column('policies', 'severity')
    op.drop_column('policies', 'description')
