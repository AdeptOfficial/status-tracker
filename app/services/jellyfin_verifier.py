"""Jellyfin Verification Service.

Verifies that anime movies are available in Jellyfin after Shoko matching.

WHY: Jellyfin's ItemAdded webhook doesn't fire reliably for Shokofin content.
This causes requests to get stuck in ANIME_MATCHING even though Shoko has
matched the file and triggered a library scan.

SOLUTION: Two-pronged approach:
1. verify_jellyfin_availability() - Immediate background task spawned after
   Shoko match. Polls Jellyfin 3 times with delays to catch the item quickly.
2. check_anime_matching_fallback() - Periodic loop (every 30s) that catches
   any missed cases (Shoko event not received, verification task failed, etc.)

ALTERNATIVES CONSIDERED:
- Blocking poll in SignalR handler: Blocks other events, not scalable
- Jellyfin webhook only: Doesn't fire reliably for Shokofin content
- Longer poll interval: Adds latency to "Ready to Watch" status
"""

import asyncio
import logging
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.database import async_session
from app.models import MediaRequest, RequestState
from app.core.state_machine import state_machine
from app.core.broadcaster import broadcaster
from app.clients.jellyfin import jellyfin_client

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Verification timing constants
INITIAL_DELAY_SECONDS = 10  # Wait for Jellyfin scan to process
RETRY_DELAY_SECONDS = 15    # Delay between retries
MAX_RETRIES = 3             # Number of retry attempts


async def verify_jellyfin_availability(request_id: int, tmdb_id: int) -> bool:
    """
    Background task to verify a movie is available in Jellyfin.

    Spawned after Shoko matches an anime movie. Polls Jellyfin to check
    if the item exists, then transitions the request to AVAILABLE.

    Creates its own database sessions (background task pattern) rather
    than sharing a session with the caller.

    Args:
        request_id: The MediaRequest ID to verify
        tmdb_id: The TMDB ID to search for in Jellyfin

    Returns:
        True if verification succeeded, False otherwise
    """
    logger.info(
        f"Starting Jellyfin verification for request {request_id} (TMDB {tmdb_id})"
    )

    # Initial delay - give Jellyfin time to scan
    await asyncio.sleep(INITIAL_DELAY_SECONDS)

    for attempt in range(MAX_RETRIES):
        try:
            # Check Jellyfin for the item
            jellyfin_item = await jellyfin_client.find_item_by_tmdb(tmdb_id, "Movie")

            if jellyfin_item:
                # Found! Transition to AVAILABLE
                async with async_session() as db:
                    # Re-fetch the request (fresh session)
                    stmt = select(MediaRequest).where(MediaRequest.id == request_id)
                    result = await db.execute(stmt)
                    request = result.scalar_one_or_none()

                    if not request:
                        logger.warning(
                            f"Jellyfin verification: request {request_id} not found"
                        )
                        return False

                    # Check request is still in ANIME_MATCHING (another service
                    # may have already transitioned it)
                    if request.state != RequestState.ANIME_MATCHING:
                        logger.debug(
                            f"Request {request_id} already transitioned to "
                            f"{request.state.value}, skipping verification"
                        )
                        return True  # Not an error, just already handled

                    # Populate jellyfin_id
                    request.jellyfin_id = jellyfin_item.get("Id")

                    # Transition to AVAILABLE
                    await state_machine.transition(
                        request,
                        RequestState.AVAILABLE,
                        db,
                        service="jellyfin-verifier",
                        event_type="Verified",
                        details=f"Verified in Jellyfin (TMDB {tmdb_id})",
                        raw_data={
                            "jellyfin_item_id": jellyfin_item.get("Id"),
                            "tmdb_id": tmdb_id,
                            "verification_attempt": attempt + 1,
                        },
                    )

                    await db.commit()
                    await broadcaster.broadcast_update(request)

                    logger.info(
                        f"Jellyfin verified: {request.title} → AVAILABLE "
                        f"(attempt {attempt + 1})"
                    )
                    return True

            # Not found yet, retry if attempts remain
            if attempt < MAX_RETRIES - 1:
                logger.debug(
                    f"Jellyfin verification attempt {attempt + 1}/{MAX_RETRIES} "
                    f"for TMDB {tmdb_id}: not found, retrying..."
                )
                await asyncio.sleep(RETRY_DELAY_SECONDS)

        except Exception as e:
            logger.error(
                f"Jellyfin verification error for request {request_id}: {e}"
            )
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY_SECONDS)

    # All retries exhausted - let fallback loop handle it
    logger.info(
        f"Jellyfin verification exhausted for request {request_id} (TMDB {tmdb_id}). "
        f"Fallback loop will continue checking."
    )
    return False


async def check_anime_matching_fallback(db: "AsyncSession") -> list[MediaRequest]:
    """
    Periodic fallback check for anime movies stuck in ANIME_MATCHING or IMPORTING.

    Called by the fallback loop in main.py every 30 seconds. Checks Jellyfin
    for any movies that may have slipped through:
    - Shoko event not received (e.g., file already in Shoko's database)
    - Verification task failed
    - SignalR connection dropped during processing

    WHY check IMPORTING too? When Shoko already knows a file (re-import after
    deletion), it skips FileMatched/MovieUpdated events. The request stays at
    IMPORTING and never reaches ANIME_MATCHING.

    Args:
        db: Database session from the loop caller

    Returns:
        List of requests that were transitioned to AVAILABLE
    """
    # Find movies stuck in ANIME_MATCHING or IMPORTING with tmdb_id
    # WHY both states? IMPORTING catches cases where Shoko events were never
    # received (already-known files, SignalR drops). ANIME_MATCHING catches
    # normal flow where verification task failed.
    stmt = select(MediaRequest).where(
        MediaRequest.state.in_([RequestState.ANIME_MATCHING, RequestState.IMPORTING]),
        MediaRequest.media_type == "movie",
        MediaRequest.tmdb_id.isnot(None),
    )
    result = await db.execute(stmt)
    stuck_requests = list(result.scalars().all())

    if not stuck_requests:
        return []

    logger.info(
        f"[FALLBACK] Checking {len(stuck_requests)} anime movies "
        f"(states: {[r.state.value for r in stuck_requests]})"
    )

    transitioned = []

    # Track if we need to trigger a scan (for IMPORTING movies that haven't been scanned)
    needs_scan = any(r.state == RequestState.IMPORTING for r in stuck_requests)
    if needs_scan:
        logger.info(
            "[FALLBACK] Found movie(s) in IMPORTING state - triggering Jellyfin scan"
        )
        await jellyfin_client.trigger_library_scan()

    for request in stuck_requests:
        try:
            logger.debug(
                f"[FALLBACK] Checking '{request.title}' (ID:{request.id}, "
                f"state:{request.state.value}, TMDB:{request.tmdb_id})"
            )

            # Check Jellyfin for this specific movie (only returns playable items)
            jellyfin_item = await jellyfin_client.find_item_by_tmdb(
                request.tmdb_id, "Movie"
            )

            if jellyfin_item:
                # Populate jellyfin_id
                request.jellyfin_id = jellyfin_item.get("Id")
                previous_state = request.state.value

                # Transition to AVAILABLE
                await state_machine.transition(
                    request,
                    RequestState.AVAILABLE,
                    db,
                    service="jellyfin",
                    event_type="FallbackVerified",
                    details=f"Found in Jellyfin (fallback from {previous_state})",
                    raw_data={
                        "jellyfin_item_id": jellyfin_item.get("Id"),
                        "tmdb_id": request.tmdb_id,
                        "previous_state": previous_state,
                        "fallback_reason": "Periodic check detected item",
                    },
                )

                transitioned.append(request)
                await broadcaster.broadcast_update(request)

                logger.info(
                    f"[FALLBACK] Verified: {request.title} ({previous_state} → AVAILABLE) "
                    f"(Jellyfin ID: {jellyfin_item.get('Id')})"
                )
            else:
                # Not in Jellyfin yet - if still IMPORTING, transition to ANIME_MATCHING
                # to show progress while we wait for Shokofin to sync
                if request.state == RequestState.IMPORTING:
                    await state_machine.transition(
                        request,
                        RequestState.ANIME_MATCHING,
                        db,
                        service="jellyfin",
                        event_type="Detected",
                        details="Detected in library scan, waiting for Shokofin sync...",
                        raw_data={
                            "tmdb_id": request.tmdb_id,
                            "fallback_reason": "IMPORTING movie detected, awaiting Jellyfin sync",
                        },
                    )
                    await broadcaster.broadcast_update(request)
                    logger.info(
                        f"[FALLBACK] '{request.title}' not yet in Jellyfin, "
                        f"transitioned IMPORTING → ANIME_MATCHING"
                    )
                else:
                    logger.debug(
                        f"[FALLBACK] '{request.title}' not yet in Jellyfin"
                    )

        except Exception as e:
            logger.error(
                f"[FALLBACK] Error checking request {request.id}: {e}"
            )

    if transitioned:
        await db.commit()
        logger.info(
            f"Jellyfin fallback transitioned {len(transitioned)} requests to AVAILABLE"
        )

    return transitioned
