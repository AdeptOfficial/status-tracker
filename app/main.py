"""Status Tracker - FastAPI Application Entry Point.

Media request lifecycle tracker for Jellyseerr -> Jellyfin pipeline.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db, async_session
from app.plugins import load_plugins, get_all_plugins
from app.routers import webhooks_router, api_router, pages_router, sse_router
from app.core.broadcaster import broadcaster

# Configure logging from environment
log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
logging.basicConfig(
    level=log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Enable DEBUG logging for specific modules when needed
if log_level == logging.DEBUG:
    # These modules benefit from DEBUG logging during troubleshooting
    logging.getLogger("app.clients.shoko").setLevel(logging.DEBUG)
    logging.getLogger("app.clients.jellyseerr").setLevel(logging.DEBUG)
    logging.getLogger("app.plugins.jellyseerr").setLevel(logging.DEBUG)
    logging.getLogger("app.plugins.sonarr").setLevel(logging.DEBUG)
else:
    # Shoko always at DEBUG for event visibility (high volume but useful)
    logging.getLogger("app.clients.shoko").setLevel(logging.DEBUG)

# Shoko SignalR imports (conditional)
if settings.ENABLE_SHOKO:
    from app.clients.shoko import get_shoko_client
    from app.plugins.shoko import handle_shoko_file_matched

# Timeout checker imports (conditional)
if settings.ENABLE_TIMEOUT_CHECKER:
    from app.services.timeout_checker import check_timeouts

# Jellyfin fallback checker
from app.services.jellyfin_verifier import check_anime_matching_fallback

# Background task handles
_polling_task: Optional[asyncio.Task] = None
_shoko_task: Optional[asyncio.Task] = None
_timeout_task: Optional[asyncio.Task] = None
_fallback_task: Optional[asyncio.Task] = None


async def shoko_signalr_loop():
    """
    Background task for Shoko SignalR connection.

    Wraps the ShokoClient to handle file matched events with database access.
    """
    if not settings.ENABLE_SHOKO or not settings.SHOKO_API_KEY:
        logger.info("Shoko SignalR disabled (no API key configured)")
        return

    logger.info("Starting Shoko SignalR client...")

    client = get_shoko_client()

    # Register callback that wraps database access
    async def on_file_matched(event):
        async with async_session() as db:
            try:
                await handle_shoko_file_matched(event, db)
                await db.commit()
            except Exception as e:
                logger.error(f"Error handling Shoko event: {e}")
                await db.rollback()

    client.on_file_matched(on_file_matched)

    # Run the client (handles reconnection internally)
    await client.start()


async def polling_loop():
    """
    Background task that polls plugins for updates.

    Runs continuously, calling poll() on each plugin that requires it.

    Uses adaptive polling:
    - 5 seconds when there are active downloads
    - 30 seconds when idle (no active downloads)
    """
    logger.info("Starting polling loop...")

    while True:
        interval = 30  # Default to slow polling

        try:
            # Get plugins that need polling
            plugins = [p for p in get_all_plugins() if p.requires_polling]

            if plugins:
                async with async_session() as db:
                    for plugin in plugins:
                        try:
                            updated_requests = await plugin.poll(db)

                            await db.commit()

                            # Broadcast AFTER commit so frontend fetches committed data
                            for request in updated_requests:
                                await broadcaster.broadcast_update(request)

                        except Exception as e:
                            logger.error(f"Error polling {plugin.name}: {e}")
                            await db.rollback()

                    # Get adaptive interval after polling (while we still have db session)
                    # Check if any plugin supports adaptive polling
                    for plugin in plugins:
                        if hasattr(plugin, "get_adaptive_poll_interval"):
                            interval = await plugin.get_adaptive_poll_interval(db)
                            break

        except Exception as e:
            logger.error(f"Polling loop error: {e}")

        await asyncio.sleep(interval)


async def timeout_checker_loop():
    """
    Background task that periodically checks for stuck requests.

    Runs every 5 minutes to mark requests that have been in certain
    states too long as TIMEOUT.
    """
    logger.info("Starting timeout checker loop...")

    # Check interval: 5 minutes
    # WHY 5 minutes? Timeouts are measured in hours, so checking more frequently
    # wastes resources. Less frequently means slower detection.
    check_interval = 300

    while True:
        try:
            async with async_session() as db:
                timed_out = await check_timeouts(db)
                if timed_out:
                    await db.commit()
                    logger.info(f"Timeout checker marked {len(timed_out)} requests")

        except Exception as e:
            logger.error(f"Timeout checker error: {e}")

        await asyncio.sleep(check_interval)


async def jellyfin_fallback_loop():
    """
    Background task that checks for anime movies stuck in ANIME_MATCHING.

    Polls Jellyfin every 30 seconds to detect movies that Shoko matched
    but didn't trigger a webhook for.
    """
    logger.info("Starting Jellyfin fallback checker loop...")

    check_interval = 30  # Check every 30 seconds

    while True:
        try:
            async with async_session() as db:
                transitioned = await check_anime_matching_fallback(db)
                if transitioned:
                    await db.commit()
                    logger.info(f"Fallback checker transitioned {len(transitioned)} requests")

        except Exception as e:
            logger.error(f"Jellyfin fallback checker error: {e}")

        await asyncio.sleep(check_interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler.

    Startup:
    - Initialize database tables
    - Load plugins
    - Start background polling task
    - Start Shoko SignalR connection (if enabled)
    - Start timeout checker (if enabled)

    Shutdown:
    - Cancel timeout checker task
    - Cancel polling task
    - Stop Shoko SignalR connection
    - Clean up resources
    """
    global _polling_task, _shoko_task, _timeout_task

    # Startup
    logger.info("Starting Status Tracker...")

    # Initialize database
    logger.info("Initializing database...")
    await init_db()
    logger.info("Database initialized")

    # Load plugins
    logger.info("Loading plugins...")
    load_plugins()
    plugins = get_all_plugins()
    logger.info(f"Loaded {len(plugins)} plugins: {[p.name for p in plugins]}")

    # Start polling task
    polling_plugins = [p for p in plugins if p.requires_polling]
    if polling_plugins:
        logger.info(f"Starting polling for: {[p.name for p in polling_plugins]}")
        _polling_task = asyncio.create_task(polling_loop())
    else:
        logger.info("No plugins require polling")

    # Start Shoko SignalR task
    if settings.ENABLE_SHOKO:
        logger.info("Starting Shoko SignalR connection...")
        _shoko_task = asyncio.create_task(shoko_signalr_loop())
    else:
        logger.info("Shoko integration disabled")

    # Start timeout checker task
    if settings.ENABLE_TIMEOUT_CHECKER:
        logger.info("Starting timeout checker...")
        _timeout_task = asyncio.create_task(timeout_checker_loop())
    else:
        logger.info("Timeout checker disabled")

    # Start Jellyfin fallback checker
    logger.info("Starting Jellyfin fallback checker...")
    _fallback_task = asyncio.create_task(jellyfin_fallback_loop())

    logger.info("Status Tracker ready")

    yield  # Application runs here

    # Shutdown
    logger.info("Shutting down Status Tracker...")

    # Stop fallback checker
    if _fallback_task:
        _fallback_task.cancel()
        try:
            await _fallback_task
        except asyncio.CancelledError:
            pass
        logger.info("Jellyfin fallback checker stopped")

    # Stop timeout checker
    if _timeout_task:
        _timeout_task.cancel()
        try:
            await _timeout_task
        except asyncio.CancelledError:
            pass
        logger.info("Timeout checker stopped")

    # Stop Shoko SignalR connection
    if _shoko_task:
        if settings.ENABLE_SHOKO:
            client = get_shoko_client()
            await client.stop()
        _shoko_task.cancel()
        try:
            await _shoko_task
        except asyncio.CancelledError:
            pass
        logger.info("Shoko SignalR task stopped")

    # Cancel polling task
    if _polling_task:
        _polling_task.cancel()
        try:
            await _polling_task
        except asyncio.CancelledError:
            pass
        logger.info("Polling task stopped")


# Create FastAPI app
app = FastAPI(
    title="Status Tracker",
    description="Media request lifecycle tracker for Jellyseerr -> Jellyfin",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware (for dashboard access from different origins)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production if needed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(webhooks_router)
app.include_router(api_router)
app.include_router(sse_router)
app.include_router(pages_router)


# Note: Root "/" is now served by pages_router (dashboard)
# For API info, use /api/health
