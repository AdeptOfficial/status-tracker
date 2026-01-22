"""Jellyfin Verification Service.

Verifies that media is available in Jellyfin and transitions to AVAILABLE state.

Handles 4 verification paths:
- verify_regular_movie(): Non-anime movie - simple TMDB lookup
- verify_regular_tv(): Non-anime TV - TVDB/TMDB lookup
- verify_anime_movie(): Anime movie - multi-type fallback (may be recategorized)
- verify_anime_tv(): Anime TV - TVDB/TMDB + fallback

Each path is called via the unified verify_request() router.

For anime content, there's a two-pronged verification approach:
1. verify_jellyfin_availability() - Immediate background task after Shoko match
2. check_stuck_requests_fallback() - Periodic loop (every 30s) for stuck requests

WHY: Jellyfin's ItemAdded webhook doesn't fire reliably for Shokofin content.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Optional

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import async_session
from app.models import MediaRequest, MediaType, RequestState
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

# Fallback check threshold - requests stuck longer than this get checked
STUCK_THRESHOLD_MINUTES = 5


def is_playable(item: dict) -> bool:
    """Check if Jellyfin item is actually playable (not metadata-only).

    Jellyfin items without files have no MediaSources or Path.
    """
    return bool(item.get("MediaSources") or item.get("Path"))


# =============================================================================
# Unified Verification Router
# =============================================================================


async def verify_request(request: MediaRequest, db: "AsyncSession") -> bool:
    """Route to appropriate verification path based on is_anime and media_type.

    Paths:
    - Regular movie: TMDB lookup
    - Regular TV: TVDB/TMDB lookup
    - Anime movie: Multi-type fallback (may be recategorized by Shoko)
    - Anime TV: TVDB/TMDB + fallback
    """
    if request.is_anime:
        if request.media_type == MediaType.MOVIE:
            return await verify_anime_movie(request, db)
        else:
            return await verify_anime_tv(request, db)
    else:
        if request.media_type == MediaType.MOVIE:
            return await verify_regular_movie(request, db)
        else:
            return await verify_regular_tv(request, db)


# =============================================================================
# Regular Movie Verification (Path 5a)
# =============================================================================


async def verify_regular_movie(request: MediaRequest, db: "AsyncSession") -> bool:
    """Verify non-anime movie in Jellyfin by TMDB ID.

    Simple flow: Just check for Movie by TMDB ID.
    """
    if not request.tmdb_id:
        logger.debug(f"Cannot verify {request.title}: no TMDB ID")
        return False

    item = await jellyfin_client.find_item_by_tmdb(request.tmdb_id, "Movie")

    if item and is_playable(item):
        return await _mark_movie_available(request, item, db, "regular")

    return False


# =============================================================================
# Regular TV Verification (Path 5b)
# =============================================================================


async def verify_regular_tv(request: MediaRequest, db: "AsyncSession") -> bool:
    """Verify non-anime TV series in Jellyfin.

    Try TVDB first (preferred for TV), then fallback to TMDB.
    """
    # Try TVDB first (preferred for TV)
    if request.tvdb_id:
        item = await jellyfin_client.find_item_by_tvdb(request.tvdb_id, "Series")
        if item and is_playable(item):
            return await _mark_tv_available(request, item, db, "regular")

    # Fallback to TMDB
    if request.tmdb_id:
        item = await jellyfin_client.find_item_by_tmdb(request.tmdb_id, "Series")
        if item and is_playable(item):
            return await _mark_tv_available(request, item, db, "regular")

    return False


# =============================================================================
# Anime Movie Verification (Path 5c)
# =============================================================================


async def verify_anime_movie(request: MediaRequest, db: "AsyncSession") -> bool:
    """Verify anime movie - may be recategorized by Shoko.

    Problem: Jellyseerr requests as Movie (TMDB), but Shoko/AniDB may
    categorize it as TV Special. Shokofin then presents as TV episode.

    Solution: Try multiple item types in order:
    1. Movie by TMDB (expected type)
    2. Series by TMDB (Shoko may categorize as TV)
    3. Any type by TMDB (no type filter)
    4. Title search (last resort)
    """
    # Try 1: Movie by TMDB (expected type)
    if request.tmdb_id:
        item = await jellyfin_client.find_item_by_tmdb(request.tmdb_id, "Movie")
        if item and is_playable(item):
            return await _mark_movie_available(request, item, db, "anime")

    # Try 2: Series by TMDB (Shoko may categorize as TV)
    if request.tmdb_id:
        item = await jellyfin_client.find_item_by_tmdb(request.tmdb_id, "Series")
        if item and is_playable(item):
            logger.info(
                f"Anime movie '{request.title}' found as Series in Jellyfin "
                f"(TMDB {request.tmdb_id} - likely recategorized by Shoko)"
            )
            return await _mark_movie_available(request, item, db, "anime-as-series")

    # Try 3: Any type by TMDB (no type filter)
    if request.tmdb_id:
        item = await jellyfin_client.find_item_by_tmdb(request.tmdb_id)
        if item and is_playable(item):
            item_type = item.get("Type", "Unknown")
            logger.info(
                f"Anime movie '{request.title}' found as {item_type} in Jellyfin"
            )
            return await _mark_movie_available(request, item, db, f"anime-as-{item_type.lower()}")

    # Try 4: Title search (last resort)
    item = await jellyfin_client.search_by_title(request.title, request.year)
    if item and is_playable(item):
        logger.info(f"Anime movie '{request.title}' found by title search")
        return await _mark_movie_available(request, item, db, "anime-title-search")

    return False


# =============================================================================
# Anime TV Verification (Path 5d)
# =============================================================================


async def verify_anime_tv(request: MediaRequest, db: "AsyncSession") -> bool:
    """Verify anime TV series - may be recategorized.

    Similar to anime movie, but for TV series.
    """
    # Try 1: Series by TVDB (preferred)
    if request.tvdb_id:
        item = await jellyfin_client.find_item_by_tvdb(request.tvdb_id, "Series")
        if item and is_playable(item):
            return await _mark_tv_available(request, item, db, "anime")

    # Try 2: Series by TMDB
    if request.tmdb_id:
        item = await jellyfin_client.find_item_by_tmdb(request.tmdb_id, "Series")
        if item and is_playable(item):
            return await _mark_tv_available(request, item, db, "anime")

    # Try 3: Any type by TMDB
    if request.tmdb_id:
        item = await jellyfin_client.find_item_by_tmdb(request.tmdb_id)
        if item and is_playable(item):
            return await _mark_tv_available(request, item, db, "anime")

    # Try 4: Title search
    item = await jellyfin_client.search_by_title(request.title)
    if item and is_playable(item):
        return await _mark_tv_available(request, item, db, "anime-title-search")

    return False


# =============================================================================
# Helper Functions
# =============================================================================


async def _mark_movie_available(
    request: MediaRequest, item: dict, db: "AsyncSession", verification_type: str
) -> bool:
    """Mark movie request as available."""
    request.jellyfin_id = item.get("Id")
    request.available_at = datetime.utcnow()

    await state_machine.transition(
        request,
        RequestState.AVAILABLE,
        db,
        service="jellyfin",
        event_type="Verified",
        details=f"Found in Jellyfin ({verification_type})",
        raw_data={
            "jellyfin_item_id": item.get("Id"),
            "jellyfin_item_type": item.get("Type"),
            "verification_type": verification_type,
        },
    )

    logger.info(
        f"Movie verified: {request.title} → AVAILABLE "
        f"(Jellyfin ID: {item.get('Id')}, type: {verification_type})"
    )
    return True


async def _mark_tv_available(
    request: MediaRequest, item: dict, db: "AsyncSession", verification_type: str
) -> bool:
    """Mark TV request and all episodes as available.

    For MVP, we verify at series level. Individual episode verification
    can be added later if needed.
    """
    from app.models import EpisodeState

    request.jellyfin_id = item.get("Id")
    request.available_at = datetime.utcnow()

    # Mark all episodes as available (series-level verification for MVP)
    for episode in request.episodes:
        episode.state = EpisodeState.AVAILABLE

    await state_machine.transition(
        request,
        RequestState.AVAILABLE,
        db,
        service="jellyfin",
        event_type="Verified",
        details=f"Series found in Jellyfin ({verification_type})",
        raw_data={
            "jellyfin_item_id": item.get("Id"),
            "jellyfin_item_type": item.get("Type"),
            "verification_type": verification_type,
            "episodes_marked": len(request.episodes),
        },
    )

    logger.info(
        f"TV verified: {request.title} → AVAILABLE "
        f"({len(request.episodes)} episodes, Jellyfin ID: {item.get('Id')})"
    )
    return True


# =============================================================================
# Background Task: Immediate Verification After Shoko Match
# =============================================================================


async def verify_jellyfin_availability(request_id: int, tmdb_id: int) -> bool:
    """
    Background task to verify media is available in Jellyfin.

    Spawned after Shoko matches anime content. Polls Jellyfin to check
    if the item exists, then transitions the request to AVAILABLE.

    Creates its own database sessions (background task pattern) rather
    than sharing a session with the caller.

    Args:
        request_id: The MediaRequest ID to verify
        tmdb_id: The TMDB ID (used for logging, actual verification uses unified router)

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
            async with async_session() as db:
                # Re-fetch the request with eager loading for episodes
                stmt = (
                    select(MediaRequest)
                    .options(selectinload(MediaRequest.episodes))
                    .where(MediaRequest.id == request_id)
                )
                result = await db.execute(stmt)
                request = result.scalar_one_or_none()

                if not request:
                    logger.warning(
                        f"Jellyfin verification: request {request_id} not found"
                    )
                    return False

                # Check request is still in a verifiable state
                if request.state not in (RequestState.ANIME_MATCHING, RequestState.IMPORTING):
                    logger.debug(
                        f"Request {request_id} already transitioned to "
                        f"{request.state.value}, skipping verification"
                    )
                    return True  # Not an error, just already handled

                # Use unified verification router
                verified = await verify_request(request, db)

                if verified:
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
                    f"for request {request_id}: not found, retrying..."
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


async def check_stuck_requests_fallback(db: "AsyncSession") -> list[MediaRequest]:
    """
    Periodic fallback check for requests stuck in DOWNLOADED, IMPORTING, or ANIME_MATCHING.

    Called by the fallback loop in main.py every 30 seconds. Checks Jellyfin
    for any media that may have slipped through:
    - Sonarr Import webhook never arrived (stuck at DOWNLOADED)
    - Shoko event not received (e.g., file already in Shoko's database)
    - Verification task failed
    - SignalR connection dropped during processing
    - Regular TV/movies waiting for library scan

    WHY check DOWNLOADED? If Sonarr's Import webhook never fires (manual import,
    webhook config issue), the request stays stuck at DOWNLOADED forever.

    WHY check IMPORTING? When Shoko already knows a file (re-import after
    deletion), it skips FileMatched/MovieUpdated events. The request stays at
    IMPORTING and never reaches ANIME_MATCHING.

    Args:
        db: Database session from the loop caller

    Returns:
        List of requests that were transitioned to AVAILABLE
    """
    # Find requests stuck in ANIME_MATCHING, IMPORTING, or DOWNLOADED
    # DOWNLOADED: qBit done but Sonarr Import webhook never arrived
    # IMPORTING: Files imported but not yet verified in Jellyfin
    # ANIME_MATCHING: Shoko matching in progress
    # NO media_type filter - check BOTH movies AND TV (Bug #2 fix)
    stmt = (
        select(MediaRequest)
        .options(selectinload(MediaRequest.episodes))  # Eager load for TV
        .where(
            MediaRequest.state.in_([
                RequestState.DOWNLOADED,
                RequestState.IMPORTING,
                RequestState.ANIME_MATCHING,
            ]),
            MediaRequest.updated_at < datetime.utcnow() - timedelta(minutes=STUCK_THRESHOLD_MINUTES),
        )
    )
    result = await db.execute(stmt)
    stuck_requests = list(result.scalars().all())

    if not stuck_requests:
        return []

    # Group by type for logging
    movies = [r for r in stuck_requests if r.media_type == MediaType.MOVIE]
    tv_shows = [r for r in stuck_requests if r.media_type == MediaType.TV]

    logger.info(
        f"[FALLBACK] Checking {len(stuck_requests)} stuck requests: "
        f"{len(movies)} movies, {len(tv_shows)} TV shows"
    )

    transitioned = []

    # Track if we need to trigger a scan (for IMPORTING requests that haven't been scanned)
    needs_scan = any(r.state == RequestState.IMPORTING for r in stuck_requests)
    if needs_scan:
        logger.info(
            "[FALLBACK] Found request(s) in IMPORTING state - triggering Jellyfin scan"
        )
        await jellyfin_client.trigger_library_scan()

    for request in stuck_requests:
        try:
            logger.debug(
                f"[FALLBACK] Checking '{request.title}' (ID:{request.id}, "
                f"type:{request.media_type.value}, state:{request.state.value})"
            )

            # Use unified verification router
            previous_state = request.state.value
            verified = await verify_request(request, db)

            if verified:
                transitioned.append(request)
                # Broadcast moved to after commit

                logger.info(
                    f"[FALLBACK] Verified: {request.title} ({previous_state} → AVAILABLE)"
                )
            else:
                # Not in Jellyfin yet - apply state-specific transitions
                if request.state == RequestState.DOWNLOADED:
                    # DOWNLOADED → IMPORTING/ANIME_MATCHING: Sonarr Import webhook may have been missed
                    target_state = RequestState.ANIME_MATCHING if request.is_anime else RequestState.IMPORTING
                    await state_machine.transition(
                        request,
                        target_state,
                        db,
                        service="fallback",
                        event_type="Stuck Recovery",
                        details="Download complete, assuming import in progress...",
                        raw_data={
                            "fallback_reason": "DOWNLOADED stuck, transitioning to continue flow",
                        },
                    )
                    transitioned.append(request)  # Mark for commit
                    # Broadcast moved to after commit
                    logger.info(
                        f"[FALLBACK] '{request.title}' stuck at DOWNLOADED, "
                        f"transitioned to {target_state.value}"
                    )
                elif request.is_anime and request.state == RequestState.IMPORTING:
                    # IMPORTING → ANIME_MATCHING: Show progress for anime
                    await state_machine.transition(
                        request,
                        RequestState.ANIME_MATCHING,
                        db,
                        service="jellyfin",
                        event_type="Detected",
                        details="Detected in library scan, waiting for Shokofin sync...",
                        raw_data={
                            "tmdb_id": request.tmdb_id,
                            "fallback_reason": "IMPORTING anime detected, awaiting Jellyfin sync",
                        },
                    )
                    transitioned.append(request)  # Mark for commit
                    # Broadcast moved to after commit
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
        # Broadcast AFTER commit so frontend fetches committed data
        for request in transitioned:
            await broadcaster.broadcast_update(request)
        logger.info(
            f"Jellyfin fallback transitioned {len(transitioned)} requests"
        )

    return transitioned


# Keep the old name as an alias for backwards compatibility
check_anime_matching_fallback = check_stuck_requests_fallback
