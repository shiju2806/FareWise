"""Analytics service — snapshot generation, traveler scoring, badge computation."""

import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select, and_, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analytics import AnalyticsSnapshot, TravelerScore
from app.models.policy import Approval, SavingsReport, Selection
from app.models.trip import Trip, TripLeg
from app.models.user import User

logger = logging.getLogger(__name__)

# Badge definitions
BADGE_DEFINITIONS = {
    "early_bird": {"name": "Early Bird", "desc": "Booked 14+ days in advance", "icon": "bird"},
    "budget_hero": {"name": "Budget Hero", "desc": "Saved 20%+ vs expensive on 3 trips", "icon": "piggy-bank"},
    "road_warrior": {"name": "Road Warrior", "desc": "Completed 10+ trips", "icon": "plane"},
    "policy_perfect": {"name": "Policy Perfect", "desc": "100% compliance for 3 months", "icon": "shield-check"},
    "smart_slider": {"name": "Smart Slider", "desc": "Avg slider under 40 (cost-conscious)", "icon": "sliders-horizontal"},
    "first_trip": {"name": "First Trip", "desc": "Completed your first trip", "icon": "flag"},
    "team_player": {"name": "Team Player", "desc": "Joined a group trip", "icon": "users"},
    "price_watcher": {"name": "Price Watcher", "desc": "Set up 3+ price watches", "icon": "eye"},
    "globe_trotter": {"name": "Globe Trotter", "desc": "Visited 5+ different cities", "icon": "globe"},
    "advance_planner": {"name": "Advance Planner", "desc": "Average 21+ days advance booking", "icon": "calendar-check"},
    "big_saver": {"name": "Big Saver", "desc": "Total savings over $5000", "icon": "trending-down"},
    "streak_3": {"name": "Hat Trick", "desc": "3 compliant trips in a row", "icon": "flame"},
}


def compute_tier(score: int) -> str:
    """Map score to traveler tier."""
    if score >= 750:
        return "platinum"
    if score >= 500:
        return "gold"
    if score >= 250:
        return "silver"
    return "bronze"


class AnalyticsService:
    """Pre-computes analytics snapshots and traveler scores."""

    # ─── Snapshots ───

    async def generate_daily_snapshot(self, db: AsyncSession) -> None:
        """Generate a daily analytics snapshot with key metrics."""
        today = date.today()
        yesterday = today - timedelta(days=1)

        # Count trips by status
        trip_counts = {}
        for status in ["draft", "submitted", "approved", "rejected"]:
            result = await db.execute(
                select(func.count(Trip.id)).where(
                    and_(
                        Trip.status == status,
                        func.date(Trip.created_at) <= today,
                    )
                )
            )
            trip_counts[status] = result.scalar() or 0

        # Total spend on approved trips
        spend_result = await db.execute(
            select(func.sum(Trip.total_estimated_cost)).where(
                Trip.status == "approved"
            )
        )
        total_spend = float(spend_result.scalar() or 0)

        # Total savings from savings reports
        savings_result = await db.execute(
            select(
                func.sum(SavingsReport.savings_vs_expensive),
                func.avg(SavingsReport.savings_vs_expensive),
            )
        )
        row = savings_result.one()
        total_savings = float(row[0] or 0)
        avg_savings = float(row[1] or 0)

        # Compliance rate
        compliance_result = await db.execute(
            select(func.count(SavingsReport.id)).where(
                SavingsReport.policy_status == "compliant"
            )
        )
        compliant_count = compliance_result.scalar() or 0
        total_reports_result = await db.execute(select(func.count(SavingsReport.id)))
        total_reports = total_reports_result.scalar() or 1
        compliance_rate = compliant_count / total_reports if total_reports > 0 else 1.0

        # Active users (trips created in last 30 days)
        active_result = await db.execute(
            select(func.count(func.distinct(Trip.traveler_id))).where(
                Trip.created_at >= datetime.now(timezone.utc) - timedelta(days=30)
            )
        )
        active_users = active_result.scalar() or 0

        snapshot = AnalyticsSnapshot(
            snapshot_type="daily",
            period_start=yesterday,
            period_end=today,
            metrics={
                "trip_counts": trip_counts,
                "total_spend": total_spend,
                "total_savings": total_savings,
                "avg_savings_per_trip": avg_savings,
                "compliance_rate": round(compliance_rate, 3),
                "active_users_30d": active_users,
            },
        )
        db.add(snapshot)
        await db.commit()
        logger.info("Daily analytics snapshot generated")

    async def generate_weekly_snapshot(self, db: AsyncSession) -> None:
        """Generate a weekly analytics snapshot."""
        today = date.today()
        week_start = today - timedelta(days=7)

        # Trips created this week
        new_trips_result = await db.execute(
            select(func.count(Trip.id)).where(
                func.date(Trip.created_at).between(week_start, today)
            )
        )
        new_trips = new_trips_result.scalar() or 0

        # Trips approved this week
        approved_result = await db.execute(
            select(func.count(Trip.id)).where(
                and_(
                    Trip.approved_at.isnot(None),
                    func.date(Trip.approved_at).between(week_start, today),
                )
            )
        )
        approved_trips = approved_result.scalar() or 0

        # Week's spend
        spend_result = await db.execute(
            select(func.sum(Trip.total_estimated_cost)).where(
                and_(
                    Trip.approved_at.isnot(None),
                    func.date(Trip.approved_at).between(week_start, today),
                )
            )
        )
        week_spend = float(spend_result.scalar() or 0)

        snapshot = AnalyticsSnapshot(
            snapshot_type="weekly",
            period_start=week_start,
            period_end=today,
            metrics={
                "new_trips": new_trips,
                "approved_trips": approved_trips,
                "week_spend": week_spend,
            },
        )
        db.add(snapshot)
        await db.commit()
        logger.info("Weekly analytics snapshot generated")

    async def generate_monthly_snapshot(self, db: AsyncSession) -> None:
        """Generate a monthly analytics snapshot with department breakdowns."""
        today = date.today()
        month_start = today.replace(day=1)
        prev_month_end = month_start - timedelta(days=1)
        prev_month_start = prev_month_end.replace(day=1)

        # Department spend breakdown
        dept_result = await db.execute(
            select(
                User.department,
                func.count(Trip.id),
                func.sum(Trip.total_estimated_cost),
            )
            .join(Trip, Trip.traveler_id == User.id)
            .where(
                and_(
                    Trip.approved_at.isnot(None),
                    func.date(Trip.approved_at).between(prev_month_start, prev_month_end),
                )
            )
            .group_by(User.department)
        )
        departments = {}
        for dept, count, spend in dept_result.all():
            departments[dept or "Unassigned"] = {
                "trips": count,
                "spend": float(spend or 0),
            }

        # Top routes
        route_result = await db.execute(
            select(
                TripLeg.origin_airport,
                TripLeg.destination_airport,
                func.count(TripLeg.id),
            )
            .join(Trip, Trip.id == TripLeg.trip_id)
            .where(
                and_(
                    Trip.approved_at.isnot(None),
                    func.date(Trip.approved_at).between(prev_month_start, prev_month_end),
                )
            )
            .group_by(TripLeg.origin_airport, TripLeg.destination_airport)
            .order_by(func.count(TripLeg.id).desc())
            .limit(10)
        )
        top_routes = [
            {"origin": o, "destination": d, "count": c}
            for o, d, c in route_result.all()
        ]

        snapshot = AnalyticsSnapshot(
            snapshot_type="monthly",
            period_start=prev_month_start,
            period_end=prev_month_end,
            metrics={
                "departments": departments,
                "top_routes": top_routes,
            },
        )
        db.add(snapshot)
        await db.commit()
        logger.info("Monthly analytics snapshot generated")

    # ─── Traveler Scores ───

    async def compute_traveler_scores(self, db: AsyncSession) -> None:
        """Compute scores for all active travelers."""
        today = date.today()
        period_start = today.replace(day=1)
        period = f"{today.year}-{today.month:02d}"

        # Get all active users with traveler or manager role
        users_result = await db.execute(
            select(User).where(User.is_active == True)
        )
        users = users_result.scalars().all()

        scores_to_upsert = []
        for user in users:
            score_data = await self._compute_user_score(db, user, period_start, today)
            if score_data is None:
                continue

            # Check for existing score this period
            existing = await db.execute(
                select(TravelerScore).where(
                    and_(
                        TravelerScore.user_id == user.id,
                        TravelerScore.period == period,
                    )
                )
            )
            ts = existing.scalar_one_or_none()
            if ts:
                for k, v in score_data.items():
                    setattr(ts, k, v)
            else:
                ts = TravelerScore(
                    user_id=user.id,
                    period=period,
                    period_start=period_start,
                    **score_data,
                )
                db.add(ts)
            scores_to_upsert.append(ts)

        await db.flush()

        # Compute ranks
        await self._compute_ranks(db, period)
        await db.commit()
        logger.info(f"Computed scores for {len(scores_to_upsert)} travelers")

    async def _compute_user_score(
        self, db: AsyncSession, user: User, period_start: date, period_end: date
    ) -> dict | None:
        """Compute individual user score. Returns None if no trips."""
        # Get user's approved trips
        trips_result = await db.execute(
            select(Trip).where(
                and_(
                    Trip.traveler_id == user.id,
                    Trip.status == "approved",
                )
            )
        )
        trips = trips_result.scalars().all()
        if not trips:
            return None

        trip_ids = [t.id for t in trips]

        # Savings reports
        sr_result = await db.execute(
            select(SavingsReport).where(SavingsReport.trip_id.in_(trip_ids))
        )
        reports = sr_result.scalars().all()

        total_spend = sum(float(r.selected_total or 0) for r in reports)
        total_savings = sum(float(r.savings_vs_expensive or 0) for r in reports)
        compliant = sum(1 for r in reports if r.policy_status == "compliant")
        compliance_rate = compliant / len(reports) if reports else 1.0

        # Selections for slider positions
        leg_ids = []
        for t in trips:
            legs_result = await db.execute(
                select(TripLeg.id).where(TripLeg.trip_id == t.id)
            )
            leg_ids.extend(legs_result.scalars().all())

        avg_slider = Decimal("50")
        if leg_ids:
            slider_result = await db.execute(
                select(func.avg(Selection.slider_position)).where(
                    Selection.trip_leg_id.in_(leg_ids)
                )
            )
            avg_slider = slider_result.scalar() or Decimal("50")

        # Advance booking days
        avg_advance = Decimal("0")
        advance_days_list = []
        for t in trips:
            legs_result = await db.execute(
                select(TripLeg).where(TripLeg.trip_id == t.id)
            )
            for leg in legs_result.scalars().all():
                if t.created_at and leg.preferred_date:
                    delta = (leg.preferred_date - t.created_at.date()).days
                    if delta > 0:
                        advance_days_list.append(delta)
        if advance_days_list:
            avg_advance = Decimal(str(sum(advance_days_list) / len(advance_days_list)))

        # Smart savings: savings from slider being < 50 (cost-conscious choices)
        smart_savings = total_savings * (1 - float(avg_slider) / 100) if total_savings > 0 else 0

        # Score computation (0-1000)
        savings_efficiency = min(300, (total_savings / max(total_spend, 1)) * 1000) if total_spend > 0 else 0
        compliance_score = compliance_rate * 250
        advance_score = min(150, float(avg_advance) * 5)
        cost_consciousness = min(150, (100 - float(avg_slider)) * 3) if float(avg_slider) < 50 else 0
        volume_score = min(100, len(trips) * 10)
        badge_score = 0  # computed after badges

        total_score = int(savings_efficiency + compliance_score + advance_score + cost_consciousness + volume_score + badge_score)

        # Check badges
        badges = await self._check_badges(db, user, trips, reports, avg_advance, avg_slider, compliance_rate)
        badge_score = min(50, len(badges) * 5)
        total_score = min(1000, total_score + badge_score)

        return {
            "total_trips": len(trips),
            "total_spend": Decimal(str(round(total_spend, 2))),
            "total_savings": Decimal(str(round(total_savings, 2))),
            "smart_savings": Decimal(str(round(smart_savings, 2))),
            "policy_compliance_rate": Decimal(str(round(compliance_rate, 3))),
            "avg_advance_booking_days": Decimal(str(round(float(avg_advance), 1))),
            "avg_slider_position": Decimal(str(round(float(avg_slider), 1))),
            "score": total_score,
            "badges": badges,
        }

    async def _check_badges(
        self, db: AsyncSession, user: User, trips, reports, avg_advance, avg_slider, compliance_rate
    ) -> list[str]:
        """Check and return earned badge IDs."""
        badges = []

        # first_trip
        if len(trips) >= 1:
            badges.append("first_trip")

        # road_warrior (10+ trips)
        if len(trips) >= 10:
            badges.append("road_warrior")

        # early_bird (14+ avg advance booking)
        if float(avg_advance) >= 14:
            badges.append("early_bird")

        # advance_planner (21+ avg advance)
        if float(avg_advance) >= 21:
            badges.append("advance_planner")

        # budget_hero (3+ trips with 20%+ savings)
        hero_count = sum(
            1 for r in reports
            if r.most_expensive_total and r.savings_vs_expensive
            and float(r.savings_vs_expensive) / float(r.most_expensive_total) >= 0.2
        )
        if hero_count >= 3:
            badges.append("budget_hero")

        # policy_perfect (100% compliance with 3+ trips)
        if compliance_rate >= 1.0 and len(reports) >= 3:
            badges.append("policy_perfect")

        # smart_slider (avg < 40)
        if float(avg_slider) < 40:
            badges.append("smart_slider")

        # big_saver (total savings > 5000)
        total_savings = sum(float(r.savings_vs_expensive or 0) for r in reports)
        if total_savings >= 5000:
            badges.append("big_saver")

        # globe_trotter (5+ unique destination cities)
        cities_result = await db.execute(
            select(func.count(func.distinct(TripLeg.destination_city)))
            .join(Trip, Trip.id == TripLeg.trip_id)
            .where(Trip.traveler_id == user.id)
        )
        unique_cities = cities_result.scalar() or 0
        if unique_cities >= 5:
            badges.append("globe_trotter")

        # streak_3 (3 compliant in a row - check last 3)
        if len(reports) >= 3:
            last_3_compliant = all(r.policy_status == "compliant" for r in reports[-3:])
            if last_3_compliant:
                badges.append("streak_3")

        # price_watcher (3+ active watches) - check via count
        from app.models.events import PriceWatch
        pw_result = await db.execute(
            select(func.count(PriceWatch.id)).where(
                and_(PriceWatch.user_id == user.id, PriceWatch.active == True)
            )
        )
        if (pw_result.scalar() or 0) >= 3:
            badges.append("price_watcher")

        return badges

    async def _compute_streak(self, db: AsyncSession, user_id) -> int:
        """Count consecutive compliant trips (most recent first)."""
        result = await db.execute(
            select(SavingsReport)
            .join(Trip, Trip.id == SavingsReport.trip_id)
            .where(
                and_(
                    Trip.traveler_id == user_id,
                    Trip.status.in_(["approved", "submitted"]),
                )
            )
            .order_by(Trip.updated_at.desc())
        )
        reports = result.scalars().all()
        streak = 0
        for r in reports:
            if r.policy_status == "compliant":
                streak += 1
            else:
                break
        return streak

    async def _compute_ranks(self, db: AsyncSession, period: str) -> None:
        """Compute department and company ranks for the given period."""
        # All scores for this period
        result = await db.execute(
            select(TravelerScore, User.department)
            .join(User, User.id == TravelerScore.user_id)
            .where(TravelerScore.period == period)
            .order_by(TravelerScore.score.desc())
        )
        rows = result.all()

        # Company rank
        for i, (ts, dept) in enumerate(rows, 1):
            ts.rank_in_company = i

        # Department rank
        dept_groups: dict[str, list] = {}
        for ts, dept in rows:
            dept_groups.setdefault(dept or "Unassigned", []).append(ts)

        for dept, members in dept_groups.items():
            members.sort(key=lambda x: x.score, reverse=True)
            for i, ts in enumerate(members, 1):
                ts.rank_in_department = i

    # ─── API Data Methods ───

    async def get_overview(self, db: AsyncSession) -> dict:
        """Get analytics overview for dashboard."""
        # Latest daily snapshot
        daily_result = await db.execute(
            select(AnalyticsSnapshot)
            .where(AnalyticsSnapshot.snapshot_type == "daily")
            .order_by(AnalyticsSnapshot.generated_at.desc())
            .limit(1)
        )
        latest_daily = daily_result.scalar_one_or_none()

        # Spend trend (last 12 weeks)
        twelve_weeks_ago = date.today() - timedelta(weeks=12)
        trend_result = await db.execute(
            select(AnalyticsSnapshot)
            .where(
                and_(
                    AnalyticsSnapshot.snapshot_type == "weekly",
                    AnalyticsSnapshot.period_start >= twelve_weeks_ago,
                )
            )
            .order_by(AnalyticsSnapshot.period_start)
        )
        spend_trend = [
            {
                "period_start": s.period_start.isoformat(),
                "period_end": s.period_end.isoformat(),
                "spend": s.metrics.get("week_spend", 0),
                "trips": s.metrics.get("approved_trips", 0),
            }
            for s in trend_result.scalars().all()
        ]

        # Headline live metrics
        total_trips_result = await db.execute(
            select(func.count(Trip.id)).where(Trip.status == "approved")
        )
        total_approved_trips = total_trips_result.scalar() or 0

        total_spend_result = await db.execute(
            select(func.sum(Trip.total_estimated_cost)).where(Trip.status == "approved")
        )
        total_spend = float(total_spend_result.scalar() or 0)

        total_savings_result = await db.execute(
            select(func.sum(SavingsReport.savings_vs_expensive))
        )
        total_savings = float(total_savings_result.scalar() or 0)

        active_users_result = await db.execute(
            select(func.count(func.distinct(Trip.traveler_id))).where(
                Trip.created_at >= datetime.now(timezone.utc) - timedelta(days=30)
            )
        )
        active_users = active_users_result.scalar() or 0

        return {
            "headline": {
                "total_trips": total_approved_trips,
                "total_spend": total_spend,
                "total_savings": total_savings,
                "active_users": active_users,
                "compliance_rate": latest_daily.metrics.get("compliance_rate", 1.0) if latest_daily else 1.0,
            },
            "spend_trend": spend_trend,
            "latest_snapshot": latest_daily.metrics if latest_daily else None,
        }

    async def get_department_analytics(self, db: AsyncSession, department: str) -> dict:
        """Get analytics for a specific department."""
        # Department users
        users_result = await db.execute(
            select(User).where(User.department == department)
        )
        dept_users = users_result.scalars().all()
        user_ids = [u.id for u in dept_users]

        if not user_ids:
            return {"department": department, "users": 0, "trips": 0, "spend": 0, "savings": 0}

        # Trip stats
        trips_result = await db.execute(
            select(
                func.count(Trip.id),
                func.sum(Trip.total_estimated_cost),
            )
            .where(
                and_(
                    Trip.traveler_id.in_(user_ids),
                    Trip.status == "approved",
                )
            )
        )
        row = trips_result.one()
        trip_count = row[0] or 0
        dept_spend = float(row[1] or 0)

        # Savings
        trip_ids_result = await db.execute(
            select(Trip.id).where(
                and_(Trip.traveler_id.in_(user_ids), Trip.status == "approved")
            )
        )
        trip_ids = trip_ids_result.scalars().all()
        dept_savings = 0.0
        if trip_ids:
            sav_result = await db.execute(
                select(func.sum(SavingsReport.savings_vs_expensive)).where(
                    SavingsReport.trip_id.in_(trip_ids)
                )
            )
            dept_savings = float(sav_result.scalar() or 0)

        # Top travelers in department
        period = f"{date.today().year}-{date.today().month:02d}"
        top_result = await db.execute(
            select(TravelerScore, User.first_name, User.last_name)
            .join(User, User.id == TravelerScore.user_id)
            .where(
                and_(
                    TravelerScore.period == period,
                    TravelerScore.user_id.in_(user_ids),
                )
            )
            .order_by(TravelerScore.score.desc())
            .limit(10)
        )
        top_travelers = [
            {
                "name": f"{fname} {lname}",
                "score": ts.score,
                "trips": ts.total_trips,
                "savings": float(ts.total_savings),
            }
            for ts, fname, lname in top_result.all()
        ]

        return {
            "department": department,
            "users": len(dept_users),
            "trips": trip_count,
            "spend": dept_spend,
            "savings": dept_savings,
            "top_travelers": top_travelers,
        }

    async def get_route_analytics(self, db: AsyncSession, origin: str, destination: str) -> dict:
        """Get analytics for a specific route."""
        result = await db.execute(
            select(
                func.count(TripLeg.id),
                func.avg(Selection.slider_position),
            )
            .outerjoin(Selection, Selection.trip_leg_id == TripLeg.id)
            .where(
                and_(
                    TripLeg.origin_airport == origin.upper(),
                    TripLeg.destination_airport == destination.upper(),
                )
            )
        )
        row = result.one()
        leg_count = row[0] or 0
        avg_slider = float(row[1] or 50)

        return {
            "origin": origin.upper(),
            "destination": destination.upper(),
            "total_bookings": leg_count,
            "avg_slider_position": round(avg_slider, 1),
        }

    async def get_my_stats(self, db: AsyncSession, user_id: uuid.UUID) -> dict:
        """Get personal stats and badges for a user."""
        period = f"{date.today().year}-{date.today().month:02d}"
        result = await db.execute(
            select(TravelerScore).where(
                and_(
                    TravelerScore.user_id == user_id,
                    TravelerScore.period == period,
                )
            )
        )
        current = result.scalar_one_or_none()

        # Historical scores (last 6 months)
        six_months_ago = date.today() - timedelta(days=180)
        history_result = await db.execute(
            select(TravelerScore)
            .where(
                and_(
                    TravelerScore.user_id == user_id,
                    TravelerScore.period_start >= six_months_ago,
                )
            )
            .order_by(TravelerScore.period_start)
        )
        history = [
            {
                "period": ts.period,
                "score": ts.score,
                "trips": ts.total_trips,
                "savings": float(ts.total_savings),
                "compliance": float(ts.policy_compliance_rate),
            }
            for ts in history_result.scalars().all()
        ]

        # Badge details
        earned_badges = current.badges if current else []
        badge_details = [
            {**BADGE_DEFINITIONS[b], "id": b}
            for b in earned_badges
            if b in BADGE_DEFINITIONS
        ]

        score_val = current.score if current else 0
        streak = await self._compute_streak(db, user_id)

        return {
            "current": {
                "score": score_val,
                "tier": compute_tier(score_val),
                "streak": streak,
                "rank_department": current.rank_in_department if current else None,
                "rank_company": current.rank_in_company if current else None,
                "total_trips": current.total_trips if current else 0,
                "total_spend": float(current.total_spend) if current else 0,
                "total_savings": float(current.total_savings) if current else 0,
                "compliance_rate": float(current.policy_compliance_rate) if current else 1.0,
                "avg_advance_days": float(current.avg_advance_booking_days) if current else 0,
                "avg_slider": float(current.avg_slider_position) if current else 50,
            },
            "badges": badge_details,
            "all_badges": [
                {**v, "id": k, "earned": k in earned_badges}
                for k, v in BADGE_DEFINITIONS.items()
            ],
            "history": history,
        }

    async def get_leaderboard(self, db: AsyncSession, department: str | None = None) -> dict:
        """Get leaderboard, optionally filtered by department."""
        period = f"{date.today().year}-{date.today().month:02d}"

        query = (
            select(TravelerScore, User.first_name, User.last_name, User.department)
            .join(User, User.id == TravelerScore.user_id)
            .where(TravelerScore.period == period)
        )
        if department:
            query = query.where(User.department == department)
        query = query.order_by(TravelerScore.score.desc()).limit(25)

        result = await db.execute(query)
        entries = [
            {
                "user_id": str(ts.user_id),
                "name": f"{fname} {lname}",
                "department": dept or "Unassigned",
                "score": ts.score,
                "tier": compute_tier(ts.score),
                "trips": ts.total_trips,
                "savings": float(ts.total_savings),
                "compliance": float(ts.policy_compliance_rate),
                "badges": ts.badges or [],
                "rank_company": ts.rank_in_company,
                "rank_department": ts.rank_in_department,
            }
            for ts, fname, lname, dept in result.all()
        ]

        return {
            "period": period,
            "department": department,
            "entries": entries,
        }

    async def get_savings_summary(self, db: AsyncSession) -> dict:
        """Get company-wide savings summary."""
        result = await db.execute(
            select(
                func.count(SavingsReport.id),
                func.sum(SavingsReport.selected_total),
                func.sum(SavingsReport.cheapest_total),
                func.sum(SavingsReport.most_expensive_total),
                func.sum(SavingsReport.savings_vs_expensive),
                func.avg(SavingsReport.savings_vs_expensive),
            )
        )
        row = result.one()
        return {
            "total_reports": row[0] or 0,
            "total_selected": float(row[1] or 0),
            "total_cheapest": float(row[2] or 0),
            "total_most_expensive": float(row[3] or 0),
            "total_savings": float(row[4] or 0),
            "avg_savings": float(row[5] or 0),
        }

    async def get_savings_goal(self, db: AsyncSession) -> dict:
        """Get company-wide savings progress for current quarter."""
        now = date.today()
        quarter_month = ((now.month - 1) // 3) * 3 + 1
        quarter_start = date(now.year, quarter_month, 1)
        # Next quarter start
        if quarter_month + 3 > 12:
            quarter_end = date(now.year + 1, 1, 1)
        else:
            quarter_end = date(now.year, quarter_month + 3, 1)
        quarter_label = f"Q{(now.month - 1) // 3 + 1} {now.year}"

        result = await db.execute(
            select(
                func.coalesce(func.sum(SavingsReport.savings_vs_expensive), 0),
                func.count(SavingsReport.id),
            )
            .join(Trip, Trip.id == SavingsReport.trip_id)
            .where(
                and_(
                    Trip.status.in_(["approved", "submitted"]),
                    Trip.updated_at >= quarter_start,
                    Trip.updated_at < quarter_end,
                )
            )
        )
        total_savings, trip_count = result.one()

        target = 50000  # $50k USD per quarter
        savings_float = float(total_savings)
        return {
            "quarter": quarter_label,
            "total_savings": savings_float,
            "target": target,
            "trip_count": trip_count,
            "progress_pct": min(100, round(savings_float / target * 100, 1)) if target > 0 else 0,
        }

    async def export_analytics_csv(self, db: AsyncSession) -> list[dict]:
        """Export analytics data as CSV-ready rows."""
        result = await db.execute(
            select(
                Trip.id,
                Trip.title,
                Trip.status,
                Trip.total_estimated_cost,
                Trip.created_at,
                Trip.approved_at,
                User.first_name,
                User.last_name,
                User.department,
            )
            .join(User, User.id == Trip.traveler_id)
            .order_by(Trip.created_at.desc())
        )
        rows = []
        for trip_id, title, status, cost, created, approved, fname, lname, dept in result.all():
            rows.append({
                "trip_id": str(trip_id),
                "title": title or "",
                "status": status,
                "estimated_cost": float(cost) if cost else 0,
                "created_at": created.isoformat() if created else "",
                "approved_at": approved.isoformat() if approved else "",
                "traveler": f"{fname} {lname}",
                "department": dept or "",
            })
        return rows


analytics_service = AnalyticsService()
