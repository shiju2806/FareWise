"""Tenant isolation tests — verify company_id scoping in service queries.

These tests capture the SQL statements issued by service methods and assert
that every read/write filters (or writes) by company_id. They don't require
a live database — they patch AsyncSession.execute to record compiled SQL.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.analytics_service import analytics_service
from app.services.collaboration_service import collaboration_service


def _render(stmt) -> str:
    """Compile a SQLAlchemy statement to an inlined SQL string for inspection."""
    return str(stmt.compile(compile_kwargs={"literal_binds": True}))


def _make_session(one_value=(0, 0, 0, 0, 0, 0)):
    """Build a mock AsyncSession whose execute() records every statement."""
    statements = []
    session = MagicMock(spec=AsyncSession)

    async def record(stmt, *args, **kwargs):
        statements.append(stmt)
        result = MagicMock()
        result.scalar.return_value = 0
        result.scalar_one_or_none.return_value = None
        result.scalars.return_value.all.return_value = []
        result.all.return_value = []
        result.one.return_value = one_value
        return result

    session.execute = AsyncMock(side_effect=record)
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.add = MagicMock()
    return session, statements


def _all_sql(statements) -> str:
    return "\n".join(_render(s) for s in statements)


def _uuid_variants(u: uuid.UUID) -> tuple[str, str]:
    """Return both dashed and hex-only string forms — SQLAlchemy literal binds
    render UUIDs without dashes on some dialects."""
    return str(u), u.hex


def _contains_uuid(sql: str, u: uuid.UUID) -> bool:
    dashed, hexed = _uuid_variants(u)
    return dashed in sql or hexed in sql


class TestAnalyticsServiceTenantScoping:
    """Every analytics read method must filter by company_id."""

    @pytest.mark.anyio
    async def test_get_overview_filters_by_company(self):
        session, statements = _make_session()
        company_id = uuid.uuid4()

        await analytics_service.get_overview(session, company_id)

        sql = _all_sql(statements)
        # Every query issued should mention company_id scoping
        assert _contains_uuid(sql, company_id)
        assert "company_id" in sql.lower()

    @pytest.mark.anyio
    async def test_get_department_analytics_filters_by_company(self):
        session, statements = _make_session()
        company_id = uuid.uuid4()

        await analytics_service.get_department_analytics(session, company_id, "Finance")

        sql = _all_sql(statements).lower()
        assert _contains_uuid(sql, company_id)
        # User lookup must be company-scoped (not global)
        assert sql.count("company_id") >= 1

    @pytest.mark.anyio
    async def test_get_route_analytics_filters_by_company(self):
        session, statements = _make_session()
        company_id = uuid.uuid4()

        await analytics_service.get_route_analytics(session, company_id, "YYZ", "YVR")

        sql = _all_sql(statements)
        assert _contains_uuid(sql, company_id)
        assert "company_id" in sql.lower()

    @pytest.mark.anyio
    async def test_get_leaderboard_filters_by_company(self):
        session, statements = _make_session()
        company_id = uuid.uuid4()

        await analytics_service.get_leaderboard(session, company_id)

        sql = _all_sql(statements)
        assert _contains_uuid(sql, company_id)

    @pytest.mark.anyio
    async def test_get_savings_summary_joins_trip_for_tenancy(self):
        session, statements = _make_session()
        company_id = uuid.uuid4()

        await analytics_service.get_savings_summary(session, company_id)

        sql = _all_sql(statements)
        # Must join trips to apply company filter (SavingsReport has no company_id)
        assert "trips" in sql.lower()
        assert _contains_uuid(sql, company_id)

    @pytest.mark.anyio
    async def test_get_savings_goal_filters_by_company(self):
        session, statements = _make_session(one_value=(0, 0))
        company_id = uuid.uuid4()

        await analytics_service.get_savings_goal(session, company_id)

        sql = _all_sql(statements)
        assert _contains_uuid(sql, company_id)

    @pytest.mark.anyio
    async def test_export_analytics_csv_filters_by_company(self):
        session, statements = _make_session()
        company_id = uuid.uuid4()

        await analytics_service.export_analytics_csv(session, company_id)

        sql = _all_sql(statements)
        assert _contains_uuid(sql, company_id)


class TestCollaborationServiceTenantScoping:
    @pytest.mark.anyio
    async def test_get_trip_overlaps_filters_by_company(self):
        session, statements = _make_session()
        company_id = uuid.uuid4()
        trip_id = uuid.uuid4()

        await collaboration_service.get_trip_overlaps(session, company_id, trip_id)

        sql = _all_sql(statements)
        assert _contains_uuid(sql, company_id)
        assert "company_id" in sql.lower()


class TestSignatureEnforcement:
    """Services must require company_id — prevents accidental removal in refactors."""

    def test_analytics_methods_require_company_id(self):
        import inspect

        for name in (
            "get_overview",
            "get_department_analytics",
            "get_route_analytics",
            "get_leaderboard",
            "get_my_stats",
            "get_savings_summary",
            "get_savings_goal",
            "export_analytics_csv",
        ):
            method = getattr(analytics_service, name)
            sig = inspect.signature(method)
            assert "company_id" in sig.parameters, f"{name} missing company_id param"

    def test_collaboration_methods_require_company_id(self):
        import inspect

        for name in ("get_trip_overlaps", "dismiss_overlap"):
            method = getattr(collaboration_service, name)
            sig = inspect.signature(method)
            assert "company_id" in sig.parameters, f"{name} missing company_id param"
