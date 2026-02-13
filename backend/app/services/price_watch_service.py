"""Price watch service — manages price watches and triggers alerts."""

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.events import PriceWatch, PriceWatchHistory
from app.models.policy import Notification
from app.services.amadeus_client import amadeus_client

logger = logging.getLogger(__name__)


class PriceWatchService:
    """Manages price watches and triggers alerts on price drops."""

    async def create_watch(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        watch_type: str,
        origin: str | None,
        destination: str | None,
        target_date: str,
        flexibility_days: int = 3,
        target_price: float | None = None,
        cabin_class: str = "economy",
        current_price: float | None = None,
    ) -> dict:
        """Create a new price watch."""
        from datetime import date as date_type

        td = date_type.fromisoformat(target_date)

        # If no target, default to 15% below current
        if target_price is None and current_price:
            target_price = round(current_price * 0.85, 2)

        watch = PriceWatch(
            user_id=user_id,
            watch_type=watch_type,
            origin=origin,
            destination=destination,
            target_date=td,
            flexibility_days=flexibility_days,
            target_price=Decimal(str(target_price)) if target_price else None,
            current_best_price=Decimal(str(current_price)) if current_price else None,
            cabin_class=cabin_class,
        )
        db.add(watch)
        await db.flush()

        # Log initial price
        if current_price:
            db.add(PriceWatchHistory(
                price_watch_id=watch.id,
                price=Decimal(str(current_price)),
            ))

        await db.commit()

        return self._watch_to_dict(watch)

    async def get_user_watches(
        self, db: AsyncSession, user_id: uuid.UUID
    ) -> list[dict]:
        """Get all active watches for a user with price history."""
        result = await db.execute(
            select(PriceWatch).where(
                PriceWatch.user_id == user_id,
                PriceWatch.is_active == True,
            ).order_by(PriceWatch.created_at.desc())
        )
        watches = result.scalars().all()

        output = []
        for w in watches:
            d = self._watch_to_dict(w)
            # Fetch history for sparkline
            hist_result = await db.execute(
                select(PriceWatchHistory).where(
                    PriceWatchHistory.price_watch_id == w.id
                ).order_by(PriceWatchHistory.checked_at.desc()).limit(14)
            )
            history = hist_result.scalars().all()
            d["price_history"] = [
                {"price": float(h.price), "checked_at": h.checked_at.isoformat()}
                for h in reversed(history)
            ]

            # Trend
            if len(history) >= 2:
                latest = float(history[0].price)
                previous = float(history[1].price)
                if latest < previous:
                    d["trend"] = "down"
                elif latest > previous:
                    d["trend"] = "up"
                else:
                    d["trend"] = "flat"
            else:
                d["trend"] = "flat"

            output.append(d)

        return output

    async def delete_watch(
        self, db: AsyncSession, watch_id: uuid.UUID, user_id: uuid.UUID
    ) -> bool:
        """Deactivate a price watch."""
        result = await db.execute(
            select(PriceWatch).where(
                PriceWatch.id == watch_id,
                PriceWatch.user_id == user_id,
            )
        )
        watch = result.scalar_one_or_none()
        if not watch:
            return False

        watch.is_active = False
        await db.commit()
        return True

    async def check_watch(self, db: AsyncSession, watch: PriceWatch) -> dict | None:
        """Check a single watch and return alert if price dropped below target."""
        from datetime import date

        if watch.watch_type == "flight" and watch.origin and watch.destination:
            flights = await amadeus_client.search_flight_offers(
                origin=watch.origin,
                destination=watch.destination,
                departure_date=watch.target_date,
                cabin_class=watch.cabin_class,
                adults=1,
                max_results=5,
            )
            if flights:
                current = min(f["price"] for f in flights)
            else:
                return None
        else:
            return None

        # Log price
        db.add(PriceWatchHistory(
            price_watch_id=watch.id,
            price=Decimal(str(current)),
        ))

        watch.current_best_price = Decimal(str(current))
        watch.last_checked_at = datetime.now(timezone.utc)

        # Check if target met
        alert = None
        if watch.target_price and current <= float(watch.target_price):
            watch.alert_count += 1
            alert = {
                "type": "price_drop",
                "watch_id": str(watch.id),
                "route": f"{watch.origin} -> {watch.destination}",
                "target_price": float(watch.target_price),
                "current_price": current,
                "message": (
                    f"Price dropped to ${current:.0f} for "
                    f"{watch.origin} -> {watch.destination} on {watch.target_date}! "
                    f"(Target: ${float(watch.target_price):.0f})"
                ),
            }

            # Create notification
            db.add(Notification(
                user_id=watch.user_id,
                type="price_drop",
                title="Price Drop Alert",
                body=alert["message"],
                reference_type="price_watch",
                reference_id=watch.id,
            ))

        await db.commit()
        return alert

    async def check_all_watches(self, db: AsyncSession) -> list[dict]:
        """Check all active watches. Called by scheduler."""
        result = await db.execute(
            select(PriceWatch).where(PriceWatch.is_active == True)
        )
        watches = result.scalars().all()

        alerts = []
        for watch in watches:
            try:
                alert = await self.check_watch(db, watch)
                if alert:
                    alerts.append(alert)
            except Exception as e:
                logger.error(f"Error checking watch {watch.id}: {e}")

        return alerts

    @staticmethod
    def _watch_to_dict(watch: PriceWatch) -> dict:
        return {
            "id": str(watch.id),
            "watch_type": watch.watch_type,
            "origin": watch.origin,
            "destination": watch.destination,
            "target_date": watch.target_date.isoformat(),
            "flexibility_days": watch.flexibility_days,
            "target_price": float(watch.target_price) if watch.target_price else None,
            "current_best_price": float(watch.current_best_price) if watch.current_best_price else None,
            "cabin_class": watch.cabin_class,
            "is_active": watch.is_active,
            "last_checked_at": watch.last_checked_at.isoformat() if watch.last_checked_at else None,
            "alert_count": watch.alert_count,
            "created_at": watch.created_at.isoformat() if watch.created_at else None,
        }


price_watch_service = PriceWatchService()
