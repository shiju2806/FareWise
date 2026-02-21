import logging
import os
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings

# ─── Logging setup (file + console) ───
_LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
_LOG_DIR.mkdir(exist_ok=True)

_log_level = getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO)

logging.basicConfig(
    level=_log_level,
    format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler(
            _LOG_DIR / "farewise.log",
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8",
        ),
    ],
)

# Quiet noisy libraries
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

from app.routers import airports, analytics, approvals, audit, auth, bundles, collaboration, events, hotels, notifications, policies, price_watches, reports, search, trip_analysis, trips, trips_calendar, users

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

            # Phase D — analytics scheduler jobs
            async def _run_daily_snapshot():
                if not settings.analytics_snapshot_enabled:
                    return
                from app.database import async_session_factory
                from app.services.analytics_service import analytics_service
                async with async_session_factory() as db:
                    await analytics_service.generate_daily_snapshot(db)
                    logger.info("Daily analytics snapshot completed")

            async def _run_traveler_scores():
                if not settings.gamification_enabled:
                    return
                from app.database import async_session_factory
                from app.services.analytics_service import analytics_service
                async with async_session_factory() as db:
                    await analytics_service.compute_traveler_scores(db)
                    logger.info("Traveler scores computation completed")

            async def _run_weekly_snapshot():
                if not settings.analytics_snapshot_enabled:
                    return
                from app.database import async_session_factory
                from app.services.analytics_service import analytics_service
                async with async_session_factory() as db:
                    await analytics_service.generate_weekly_snapshot(db)
                    logger.info("Weekly analytics snapshot completed")

            async def _run_monthly_snapshot():
                if not settings.analytics_snapshot_enabled:
                    return
                from app.database import async_session_factory
                from app.services.analytics_service import analytics_service
                async with async_session_factory() as db:
                    await analytics_service.generate_monthly_snapshot(db)
                    logger.info("Monthly analytics snapshot completed")

            scheduler.add_job(_run_price_checks, IntervalTrigger(hours=settings.price_watch_check_interval_hours), id="price_checks")
            scheduler.add_job(_run_unbooked_hotels, CronTrigger(hour=9, minute=0), id="unbooked_hotels")
            scheduler.add_job(_run_event_alerts, CronTrigger(hour=10, minute=0), id="event_alerts")
            scheduler.add_job(_cleanup_events, CronTrigger(hour=2, minute=0), id="cleanup_events")
            scheduler.add_job(_run_daily_snapshot, CronTrigger(hour=1, minute=0), id="daily_snapshot")
            scheduler.add_job(_run_traveler_scores, CronTrigger(hour=2, minute=30), id="traveler_scores")
            scheduler.add_job(_run_weekly_snapshot, CronTrigger(day_of_week="mon", hour=3, minute=0), id="weekly_snapshot")
            scheduler.add_job(_run_monthly_snapshot, CronTrigger(day="1", hour=4, minute=0), id="monthly_snapshot")

            scheduler.start()
            logger.info("Background scheduler started")
        except ImportError:
            logger.warning("APScheduler not installed — background jobs disabled")
        except Exception as e:
            logger.error(f"Scheduler failed to start: {e}")

    # Auto-seed users/policies if DB is empty (dev/MVP convenience)
    try:
        from app.seed import seed
        await seed()
    except Exception as e:
        logger.warning(f"Auto-seed skipped: {e}")

    # Create DB1B asyncpg pool for historical fare data
    db1b_pool = None
    if settings.db1b_enabled:
        try:
            import asyncpg
            from app.services.db1b_client import db1b_client

            db1b_pool = await asyncpg.create_pool(
                settings.db1b_database_url,
                min_size=settings.db1b_pool_min,
                max_size=settings.db1b_pool_max,
                timeout=settings.db1b_pool_timeout,
                command_timeout=settings.db1b_command_timeout,
            )
            db1b_client.pool = db1b_pool
            app.state.db1b_pool = db1b_pool
            logger.info("DB1B asyncpg pool created")
        except Exception as e:
            logger.warning(f"DB1B pool creation failed (search will use Amadeus fallback): {e}")
            app.state.db1b_pool = None

    yield

    # Shutdown
    if db1b_pool:
        await db1b_pool.close()
        logger.info("DB1B asyncpg pool closed")
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
    allow_origin_regex=r"https://.*\.ngrok-free\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(trips_calendar.router, prefix="/api/trips", tags=["trips-calendar"])
app.include_router(trip_analysis.router, prefix="/api/trips", tags=["trip-analysis"])
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
app.include_router(analytics.router, prefix="/api/analytics", tags=["analytics"])
app.include_router(collaboration.router, prefix="/api", tags=["collaboration"])
app.include_router(reports.router, prefix="/api/reports", tags=["reports"])


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "farewise"}


# Serve built frontend (for ngrok / production)
import os
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

_frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _frontend_dist.is_dir():
    app.mount("/assets", StaticFiles(directory=str(_frontend_dist / "assets")), name="static-assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve the SPA index.html for all non-API routes."""
        file_path = _frontend_dist / full_path
        if file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(_frontend_dist / "index.html"))
