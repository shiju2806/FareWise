import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import airports, approvals, audit, auth, bundles, events, hotels, notifications, policies, price_watches, search, trips, users

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup — launch background scheduler
    scheduler = None
    if settings.scheduler_enabled:
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            from apscheduler.triggers.interval import IntervalTrigger
            from apscheduler.triggers.cron import CronTrigger

            scheduler = AsyncIOScheduler()

            async def _run_price_checks():
                from app.database import async_session_factory
                from app.services.price_watch_service import price_watch_service
                async with async_session_factory() as db:
                    alerts = await price_watch_service.check_all_watches(db)
                    if alerts:
                        logger.info(f"Price watch: {len(alerts)} alerts triggered")

            async def _run_unbooked_hotels():
                from app.database import async_session_factory
                from app.services.proactive_alert_service import proactive_alert_service
                async with async_session_factory() as db:
                    count = await proactive_alert_service.check_unbooked_hotels(db)
                    if count:
                        logger.info(f"Unbooked hotels: {count} reminders sent")

            async def _run_event_alerts():
                from app.database import async_session_factory
                from app.services.proactive_alert_service import proactive_alert_service
                async with async_session_factory() as db:
                    count = await proactive_alert_service.check_event_alerts(db)
                    if count:
                        logger.info(f"Event alerts: {count} warnings sent")

            async def _cleanup_events():
                from app.database import async_session_factory
                from app.services.event_service import event_service
                async with async_session_factory() as db:
                    count = await event_service.cleanup_expired_cache(db)
                    if count:
                        logger.info(f"Event cache: {count} expired entries removed")

            scheduler.add_job(_run_price_checks, IntervalTrigger(hours=settings.price_watch_check_interval_hours), id="price_checks")
            scheduler.add_job(_run_unbooked_hotels, CronTrigger(hour=9, minute=0), id="unbooked_hotels")
            scheduler.add_job(_run_event_alerts, CronTrigger(hour=10, minute=0), id="event_alerts")
            scheduler.add_job(_cleanup_events, CronTrigger(hour=2, minute=0), id="cleanup_events")

            scheduler.start()
            logger.info("Background scheduler started")
        except ImportError:
            logger.warning("APScheduler not installed — background jobs disabled")
        except Exception as e:
            logger.error(f"Scheduler failed to start: {e}")

    yield

    # Shutdown
    if scheduler:
        scheduler.shutdown(wait=False)
        logger.info("Background scheduler stopped")


app = FastAPI(
    title="FareWise",
    description="Travel Cost Optimization Platform",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(trips.router, prefix="/api/trips", tags=["trips"])
app.include_router(search.router, prefix="/api/search", tags=["search"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(airports.router, prefix="/api/airports", tags=["airports"])
app.include_router(policies.router, prefix="/api/policies", tags=["policies"])
app.include_router(approvals.router, prefix="/api", tags=["approvals"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["notifications"])
app.include_router(audit.router, prefix="/api/audit", tags=["audit"])
app.include_router(events.router, prefix="/api/events", tags=["events"])
app.include_router(hotels.router, prefix="/api/search", tags=["hotels"])
app.include_router(bundles.router, prefix="/api/search", tags=["bundles"])
app.include_router(price_watches.router, prefix="/api", tags=["price-watches", "alerts"])


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "farewise"}
