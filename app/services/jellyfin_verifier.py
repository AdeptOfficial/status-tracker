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
import json
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
from app.config import settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def parse_alternate_titles(request: MediaRequest) -> list[str]:
    """Parse alternate_titles JSON string into list.

    Alternate titles are stored as JSON array string in the database.
    Used for Japanese/romaji titles that Shokofin may use instead of English.
    """
    if not request.alternate_titles:
        return []
    try:
        titles = json.loads(request.alternate_titles)
        return titles if isinstance(titles, list) else []
    except (json.JSONDecodeError, TypeError):
        logger.warning(f"Failed to parse alternate_titles for request {request.id}")
        return []


# Verification timing constants
INITIAL_DELAY_SECONDS = 10  # Wait for Jellyfin scan to process
RETRY_DELAY_SECONDS = 15    # Delay between retries
MAX_RETRIES = 3             # Number of retry attempts

# Fallback check threshold - requests stuck longer than this get checked
STUCK_THRESHOLD_MINUTES = 2

# VFS regeneration delay - time to wait for Shokofin to process SignalR events
# Immediate verification waits for normal Shokofin discovery. The durable refresh
# coordinator provides delayed, coalesced recovery when discovery is missed.
VFS_REGENERATION_DELAY = 10  # seconds


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

    # Try 5: Alternate titles (for Japanese/romaji titles in Shokofin)
    alternate_titles = parse_alternate_titles(request)
    for alt_title in alternate_titles:
        item = await jellyfin_client.search_by_title(alt_title, request.year)
        if item and is_playable(item):
            logger.info(f"Anime movie '{request.title}' found by alternate title '{alt_title}'")
            return await _mark_movie_available(request, item, db, f"anime-alt-title:{alt_title}")

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

    # Try 5: Alternate titles (for Japanese/romaji titles in Shokofin)
    alternate_titles = parse_alternate_titles(request)
    for alt_title in alternate_titles:
        item = await jellyfin_client.search_by_title(alt_title)
        if item and is_playable(item):
            logger.info(f"Anime TV '{request.title}' found by alternate title '{alt_title}'")
            return await _mark_tv_available(request, item, db, f"anime-alt-title:{alt_title}")

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
    """Require individual playable episodes, not merely a series directory."""
    from app.models import EpisodeState
    # Display helpers may fall back to other seasons; availability must not.
    episodes = [ep for ep in request.episodes
                if request.season is None or ep.season_number == request.season]
    if not episodes or not item.get("Id"):
        return False
    found = await jellyfin_client.get_series_episodes(item["Id"])
    if found is None:
        return False
    playable = {}
    for entry in found:
        if is_playable(entry) and entry.get("Id"):
            season, number = entry.get("ParentIndexNumber"), entry.get("IndexNumber")
            if isinstance(season, int) and isinstance(number, int):
                end = entry.get("IndexNumberEnd") or number
                if not isinstance(end, int) or end < number or end - number > 100:
                    continue
                for n in range(number, end + 1):
                    playable[(season, n)] = entry
    changed = False
    for episode in episodes:
        entry = playable.get((episode.season_number, episode.episode_number))
        if entry:
            changed |= episode.state != EpisodeState.AVAILABLE
            episode.state = EpisodeState.AVAILABLE
            episode.jellyfin_id = entry["Id"]
    request.jellyfin_id = item["Id"]
    if len(episodes) < (request.total_episodes or 0) or not all(ep.state == EpisodeState.AVAILABLE for ep in episodes):
        if changed:
            await db.commit()
            await broadcaster.broadcast_update(request)
        return False
    request.available_at = datetime.utcnow()
    await state_machine.transition(
        request, RequestState.AVAILABLE, db, service="jellyfin", event_type="Verified",
        details=f"Episodes verified in Jellyfin ({verification_type})",
        raw_data={"jellyfin_item_id": item["Id"], "episodes_marked": len(episodes)},
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


async def verify_movie_by_tmdb(tmdb_id: int) -> bool:
    """
    Verify a movie in Jellyfin by TMDB ID.

    Called when Shoko sends MovieUpdated with Reason: 'Added'.
    Finds the matching request and triggers verification.

    This is faster than waiting for the fallback loop since it's triggered
    immediately when Shoko finishes processing.

    Args:
        tmdb_id: The TMDB ID from Shoko's MovieUpdated event

    Returns:
        True if verification succeeded, False otherwise
    """
    logger.info(f"[MOVIE UPDATED] Starting verification for TMDB {tmdb_id}")

    # Wait a moment for Shokofin to process the SignalR event and regenerate VFS
    # We do NOT trigger library scans here - that interferes with Shokofin's
    # SignalR event processing and can cause VFS regeneration to fail.
    await asyncio.sleep(VFS_REGENERATION_DELAY)

    async with async_session() as db:
        # Find request by TMDB ID in verifiable states
        stmt = (
            select(MediaRequest)
            .options(selectinload(MediaRequest.episodes))
            .where(
                MediaRequest.tmdb_id == tmdb_id,
                MediaRequest.state.in_([
                    RequestState.IMPORTING,
                    RequestState.ANIME_MATCHING,
                ]),
            )
        )
        result = await db.execute(stmt)
        request = result.scalar_one_or_none()

        if not request:
            logger.debug(
                f"[MOVIE UPDATED] No matching request found for TMDB {tmdb_id} "
                f"in verifiable state"
            )
            return False

        logger.info(
            f"[MOVIE UPDATED] Found request '{request.title}' (ID: {request.id}) "
            f"for TMDB {tmdb_id}, verifying in Jellyfin..."
        )

        # Use unified verification router
        verified = await verify_request(request, db)

        if verified:
            await db.commit()
            await broadcaster.broadcast_update(request)
            logger.info(
                f"[MOVIE UPDATED] Verified: {request.title} → AVAILABLE "
                f"(TMDB {tmdb_id})"
            )
            return True

        logger.debug(
            f"[MOVIE UPDATED] {request.title} not yet in Jellyfin, "
            f"fallback will continue checking"
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
    - Missed Shoko match events (queues a non-destructive API refresh after confirmation)

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


    # Log SignalR state for debugging
    if settings.ENABLE_SHOKO and settings.SHOKO_API_KEY:
        try:
            from app.clients.shoko import get_shoko_client, ConnectionState
            shoko_client = get_shoko_client()
            if shoko_client.state != ConnectionState.CONNECTED:
                logger.warning(
                    f"[FALLBACK] Shoko SignalR disconnected (state: {shoko_client.state.value}). "
                    f"VFS regeneration may be delayed until reconnection."
                )
        except Exception as e:
            logger.error(f"[FALLBACK] Error checking Shoko SignalR state: {e}")

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
                from app.services.library_refresh import recover_matched_files
                await recover_matched_files(request, db)
                # A timeout is not evidence of import or Shoko matching.
                # Keep the observed stage; future verification still recovers
                # missed webhooks by confirming actual Jellyfin availability.
                logger.debug("[FALLBACK] Request %s not verified; retaining %s",
                             request.id, request.state.value)

        except Exception as e:
            logger.error(
                f"[FALLBACK] Error checking request {request.id}: {e}"
            )

    await db.commit()  # Persist recovered refresh intents even without a state change.
    if transitioned:
        # Broadcast AFTER commit so frontend fetches committed data
        for request in transitioned:
            await broadcaster.broadcast_update(request)
        logger.info(
            f"Jellyfin fallback transitioned {len(transitioned)} requests"
        )

    return transitioned


# Keep the old name as an alias for backwards compatibility
check_anime_matching_fallback = check_stuck_requests_fallback
