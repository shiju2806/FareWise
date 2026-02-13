"""Seed script for Phase D — generates synthetic analytics snapshots, scores, badges."""

import asyncio
import random
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select

from app.database import async_session_factory
from app.models.analytics import AnalyticsSnapshot, TravelerScore
from app.models.user import User

DEPARTMENTS = ["Finance", "Engineering", "Sales", "Marketing", "IT"]


async def seed_phase_d():
    async with async_session_factory() as db:
        # Get existing users
        result = await db.execute(select(User).where(User.is_active == True))
        users = result.scalars().all()
        if not users:
            print("No users found — run seed first")
            return

        print(f"Seeding Phase D data for {len(users)} users...")

        # ─── Daily snapshots (last 90 days) ───
        today = date.today()
        for days_back in range(90, 0, -1):
            d = today - timedelta(days=days_back)
            base_trips = random.randint(5, 20)
            base_spend = random.uniform(10000, 50000)
            snapshot = AnalyticsSnapshot(
                snapshot_type="daily",
                period_start=d - timedelta(days=1),
                period_end=d,
                metrics={
                    "trip_counts": {
                        "draft": random.randint(2, 10),
                        "submitted": random.randint(1, 5),
                        "approved": base_trips,
                        "rejected": random.randint(0, 2),
                    },
                    "total_spend": round(base_spend, 2),
                    "total_savings": round(base_spend * random.uniform(0.1, 0.3), 2),
                    "avg_savings_per_trip": round(base_spend * random.uniform(0.1, 0.3) / max(base_trips, 1), 2),
                    "compliance_rate": round(random.uniform(0.85, 1.0), 3),
                    "active_users_30d": random.randint(3, len(users)),
                },
            )
            db.add(snapshot)

        # ─── Weekly snapshots (last 12 weeks) ───
        for weeks_back in range(12, 0, -1):
            week_end = today - timedelta(weeks=weeks_back - 1)
            week_start = week_end - timedelta(days=7)
            snapshot = AnalyticsSnapshot(
                snapshot_type="weekly",
                period_start=week_start,
                period_end=week_end,
                metrics={
                    "new_trips": random.randint(10, 40),
                    "approved_trips": random.randint(8, 30),
                    "week_spend": round(random.uniform(20000, 80000), 2),
                },
            )
            db.add(snapshot)

        # ─── Monthly snapshots (last 3 months) ───
        for months_back in range(3, 0, -1):
            month_end = today.replace(day=1) - timedelta(days=1)
            for _ in range(months_back - 1):
                month_end = month_end.replace(day=1) - timedelta(days=1)
            month_start = month_end.replace(day=1)

            dept_data = {}
            for dept in DEPARTMENTS:
                dept_data[dept] = {
                    "trips": random.randint(5, 20),
                    "spend": round(random.uniform(10000, 50000), 2),
                }

            routes = [
                ("YYZ", "YVR"), ("YYZ", "YUL"), ("YVR", "YYC"),
                ("YOW", "YYZ"), ("YUL", "YVR"), ("YYZ", "LAX"),
            ]
            top_routes = [
                {"origin": o, "destination": d, "count": random.randint(5, 25)}
                for o, d in routes[:random.randint(3, 6)]
            ]

            snapshot = AnalyticsSnapshot(
                snapshot_type="monthly",
                period_start=month_start,
                period_end=month_end,
                metrics={
                    "departments": dept_data,
                    "top_routes": top_routes,
                },
            )
            db.add(snapshot)

        # ─── Traveler scores (last 3 months) ───
        badge_pool = [
            "first_trip", "early_bird", "budget_hero", "road_warrior",
            "policy_perfect", "smart_slider", "globe_trotter", "streak_3",
        ]

        for months_back in range(3, 0, -1):
            period_date = today.replace(day=1)
            for _ in range(months_back - 1):
                period_date = (period_date - timedelta(days=1)).replace(day=1)
            period = f"{period_date.year}-{period_date.month:02d}"

            for user in users:
                trips = random.randint(1, 8)
                spend = round(random.uniform(500, 8000), 2)
                savings = round(spend * random.uniform(0.05, 0.35), 2)
                compliance = round(random.uniform(0.85, 1.0), 3)
                advance_days = round(random.uniform(5, 30), 1)
                slider = round(random.uniform(20, 70), 1)

                # Score
                sav_eff = min(300, (savings / max(spend, 1)) * 1000)
                comp_score = compliance * 250
                adv_score = min(150, advance_days * 5)
                cost_score = min(150, (100 - slider) * 3) if slider < 50 else 0
                vol_score = min(100, trips * 10)
                num_badges = random.randint(1, min(5, len(badge_pool)))
                earned = random.sample(badge_pool, num_badges)
                badge_bonus = min(50, num_badges * 5)
                total_score = min(1000, int(sav_eff + comp_score + adv_score + cost_score + vol_score + badge_bonus))

                ts = TravelerScore(
                    user_id=user.id,
                    period=period,
                    period_start=period_date,
                    total_trips=trips,
                    total_spend=Decimal(str(spend)),
                    total_savings=Decimal(str(savings)),
                    smart_savings=Decimal(str(round(savings * (1 - slider / 100), 2))),
                    policy_compliance_rate=Decimal(str(compliance)),
                    avg_advance_booking_days=Decimal(str(advance_days)),
                    avg_slider_position=Decimal(str(slider)),
                    score=total_score,
                    badges=earned,
                )
                db.add(ts)

        await db.flush()

        # Compute ranks per period
        for months_back in range(3, 0, -1):
            period_date = today.replace(day=1)
            for _ in range(months_back - 1):
                period_date = (period_date - timedelta(days=1)).replace(day=1)
            period = f"{period_date.year}-{period_date.month:02d}"

            scores_result = await db.execute(
                select(TravelerScore, User.department)
                .join(User, User.id == TravelerScore.user_id)
                .where(TravelerScore.period == period)
                .order_by(TravelerScore.score.desc())
            )
            rows = scores_result.all()

            for i, (ts, dept) in enumerate(rows, 1):
                ts.rank_in_company = i

            dept_groups: dict[str, list] = {}
            for ts, dept in rows:
                dept_groups.setdefault(dept or "Unassigned", []).append(ts)
            for members in dept_groups.values():
                members.sort(key=lambda x: x.score, reverse=True)
                for i, ts in enumerate(members, 1):
                    ts.rank_in_department = i

        await db.commit()
        print("Phase D seed data created successfully!")
        print(f"  - 90 daily snapshots")
        print(f"  - 12 weekly snapshots")
        print(f"  - 3 monthly snapshots")
        print(f"  - {len(users) * 3} traveler scores (3 months × {len(users)} users)")


if __name__ == "__main__":
    asyncio.run(seed_phase_d())
