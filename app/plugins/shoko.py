"""Shoko plugin - tracks anime metadata matching via SignalR.

Shoko matches imported anime files to AniDB metadata. This plugin listens
for FileMatched events via SignalR and transitions requests accordingly.

Unlike other plugins, Shoko doesn't use webhooks - it uses SignalR for
real-time push notifications. The ShokoClient handles the connection.

State transitions:
- IMPORTING → ANIME_MATCHING: File detected by Shoko
- ANIME_MATCHING → AVAILABLE: File matched with cross-references (via Jellyfin verification)

Path correlation:
- Sonarr/Radarr stores final_path: /data/anime/shows/Show/Season 1/episode.mkv
- Shoko sends RelativePath: anime/shows/Show/Season 1/episode.mkv
- We prepend /data/ to Shoko's path to match final_path

Flow for anime movies:
1. Shoko FileMatched with cross-refs → store shoko_file_id
2. Trigger verify_jellyfin_availability() background task
3. Jellyfin verification uses multi-type fallback (Movie → Series → Any → Title)
4. Verification success → AVAILABLE

Flow for anime TV:
1. Shoko FileMatched for each episode → update Episode.shoko_file_id
2. Episode state → AVAILABLE
3. When all episodes AVAILABLE → request AVAILABLE (via aggregation)
"""

import asyncio
import logging
from typing import TYPE_CHECKING, Optional

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.core.plugin_base import ServicePlugin
from app.core.state_machine import state_machine
from app.core.broadcaster import broadcaster
from app.models import MediaRequest, MediaType, RequestState, Episode, EpisodeState
from app.services.state_calculator import calculate_aggregate_state

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.clients.shoko import FileEvent

logger = logging.getLogger(__name__)


class ShokoPlugin(ServicePlugin):
    """
    Handles Shoko anime metadata matching events.

    This plugin is different from others - it doesn't use webhooks.
    Instead, it registers callbacks with the ShokoClient which receives
    events via SignalR.
    """

    @property
    def name(self) -> str:
        return "shoko"

    @property
    def display_name(self) -> str:
        return "Shoko"

    @property
    def states_provided(self) -> list[RequestState]:
        return [RequestState.ANIME_MATCHING, RequestState.AVAILABLE]

    @property
    def correlation_fields(self) -> list[str]:
        return ["final_path"]

    @property
    def requires_polling(self) -> bool:
        # Shoko uses SignalR push, not polling
        return False

    async def handle_webhook(
        self, payload: dict, db: "AsyncSession"
    ) -> Optional[MediaRequest]:
        """
        Shoko doesn't use traditional webhooks.
        This is here for completeness but won't be called.
        """
        logger.warning("Shoko webhook endpoint called - use SignalR instead")
        return None

    def get_timeline_details(self, event_data: dict) -> str:
        """Format event for timeline display."""
        has_refs = event_data.get("has_cross_references", False)
        if has_refs:
            return "Matched to AniDB"
        return "File detected, matching..."


async def handle_shoko_file_matched(event: "FileEvent", db: "AsyncSession") -> None:
    """
    Process a Shoko FileMatched event.

    Called by the ShokoClient when a file is matched.

    For movies: Triggers Jellyfin verification after Shoko match.
    For TV: Updates individual episode state, recalculates aggregate.

    Args:
        event: Parsed FileEvent from SignalR
        db: Database session
    """
    if not settings.ENABLE_SHOKO:
        return

    # Build the full path as Radarr/Sonarr would see it
    # Shoko's RelativePath: anime/movies/Title/file.mkv
    # Radarr's final_path: /data/anime/movies/Title/file.mkv
    # Path prefix is configurable via MEDIA_PATH_PREFIX env var
    media_prefix = settings.MEDIA_PATH_PREFIX.rstrip("/")
    full_path = f"{media_prefix}/{event.relative_path}"

    logger.debug(f"Looking for request/episode with path: {full_path}")

    # First, try to find a TV episode by path
    episode = await find_episode_by_path(db, full_path, event.relative_path)
    if episode:
        await _handle_tv_episode_matched(episode, event, db)
        return

    # If not an episode, try to find a movie request
    request = await find_request_by_path(db, full_path)
    if not request:
        request = await find_request_by_path_pattern(db, event.relative_path)

    if not request:
        logger.debug(f"No matching request/episode found for path: {event.relative_path}")
        return

    # Skip if not an anime request (check if path contains /anime/)
    if request.final_path and "/anime/" not in request.final_path:
        logger.debug(f"Skipping non-anime request: {request.title}")
        return

    # Handle movie
    await _handle_movie_matched(request, event, db)


async def _handle_movie_matched(
    request: MediaRequest, event: "FileEvent", db: "AsyncSession"
) -> None:
    """Handle Shoko FileMatched for anime movie.

    Instead of transitioning directly to AVAILABLE, we trigger Jellyfin
    verification which handles multi-type fallback (Movie → Series → Any → Title).
    """
    from app.services.jellyfin_verifier import verify_jellyfin_availability

    # Store Shoko file ID (as series ID since that's what the model has)
    # In practice, for movies this is the file ID, but we store it for correlation
    if event.file_id and not request.shoko_series_id:
        request.shoko_series_id = event.file_id

    if event.has_cross_references:
        # File is fully matched to AniDB - trigger Jellyfin verification
        if request.state in (RequestState.IMPORTING, RequestState.ANIME_MATCHING, RequestState.MATCH_FAILED):
            # Transition to ANIME_MATCHING to indicate Shoko has processed
            if request.state in (RequestState.IMPORTING, RequestState.MATCH_FAILED):
                # Clear match failure reason if recovering from MATCH_FAILED
                if request.state == RequestState.MATCH_FAILED:
                    request.match_failure_reason = None
                await state_machine.transition(
                    request,
                    RequestState.ANIME_MATCHING,
                    db,
                    service="shoko",
                    event_type="Matched",
                    details="Matched to AniDB, verifying in Jellyfin...",
                    raw_data={
                        "file_id": event.file_id,
                        "relative_path": event.relative_path,
                        "has_cross_references": event.has_cross_references,
                    },
                )

            await db.commit()
            await broadcaster.broadcast_update(request)

            # Spawn background task to verify in Jellyfin
            # This handles multi-type fallback for recategorized anime
            asyncio.create_task(
                verify_jellyfin_availability(request.id, request.tmdb_id or 0)
            )

            logger.info(
                f"Shoko matched: {request.title} → ANIME_MATCHING "
                f"(Jellyfin verification triggered)"
            )
    else:
        # File detected but not yet matched
        if request.state == RequestState.IMPORTING:
            await state_machine.transition(
                request,
                RequestState.ANIME_MATCHING,
                db,
                service="shoko",
                event_type="Detected",
                details="File detected, matching to AniDB...",
                raw_data={
                    "file_id": event.file_id,
                    "relative_path": event.relative_path,
                    "has_cross_references": event.has_cross_references,
                },
            )
            await db.commit()
            await broadcaster.broadcast_update(request)
            logger.info(f"Shoko detected: {request.title} → ANIME_MATCHING")


async def _handle_tv_episode_matched(
    episode: Episode, event: "FileEvent", db: "AsyncSession"
) -> None:
    """Handle Shoko FileMatched for anime TV episode.

    Updates individual episode state and triggers Jellyfin verification.
    Episode only becomes AVAILABLE after Jellyfin confirms it exists.
    """
    from app.services.jellyfin_verifier import verify_jellyfin_availability

    # Store Shoko file ID on episode
    if event.file_id:
        episode.shoko_file_id = str(event.file_id)

    if event.has_cross_references:
        # Episode matched to AniDB - trigger Jellyfin verification
        if episode.state in (EpisodeState.IMPORTING, EpisodeState.ANIME_MATCHING, EpisodeState.MATCH_FAILED):
            # Keep episode in ANIME_MATCHING until Jellyfin verifies
            if episode.state != EpisodeState.ANIME_MATCHING:
                episode.state = EpisodeState.ANIME_MATCHING

            # Recalculate parent request state
            request = episode.request
            if request:
                # Reload request with all episodes for accurate aggregation
                stmt = (
                    select(MediaRequest)
                    .options(selectinload(MediaRequest.episodes))
                    .where(MediaRequest.id == request.id)
                )
                result = await db.execute(stmt)
                request = result.scalar_one()

                # Ensure request is in ANIME_MATCHING
                if request.state not in (RequestState.ANIME_MATCHING, RequestState.AVAILABLE):
                    await state_machine.transition(
                        request,
                        RequestState.ANIME_MATCHING,
                        db,
                        service="shoko",
                        event_type="EpisodeMatched",
                        details=f"Episode S{episode.season_number}E{episode.episode_number} matched, verifying in Jellyfin...",
                        raw_data={
                            "file_id": event.file_id,
                            "episode_id": episode.id,
                            "relative_path": event.relative_path,
                        },
                    )

                await db.commit()
                await broadcaster.broadcast_update(request)

                # Trigger Jellyfin verification for the show
                # This will check if episodes are available and set AVAILABLE accordingly
                asyncio.create_task(
                    verify_jellyfin_availability(request.id, request.tmdb_id or 0)
                )

                logger.info(
                    f"Shoko episode matched: {request.title} "
                    f"S{episode.season_number}E{episode.episode_number} → ANIME_MATCHING "
                    f"(Jellyfin verification triggered)"
                )
    else:
        # Episode detected but not yet matched
        if episode.state == EpisodeState.IMPORTING:
            episode.state = EpisodeState.ANIME_MATCHING
            await db.commit()

            if episode.request:
                await broadcaster.broadcast_update(episode.request)

            logger.info(
                f"Shoko episode detected: S{episode.season_number}E{episode.episode_number} "
                f"→ ANIME_MATCHING"
            )


async def find_request_by_path(
    db: "AsyncSession", path: str
) -> Optional[MediaRequest]:
    """Find request where final_path matches the given path."""
    stmt = select(MediaRequest).where(
        MediaRequest.final_path == path,
        MediaRequest.state.in_([
            RequestState.IMPORTING,
            RequestState.ANIME_MATCHING,
            RequestState.MATCH_FAILED,  # Include for FileMatched after manual linking
        ]),
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def find_request_by_path_pattern(
    db: "AsyncSession", relative_path: str
) -> Optional[MediaRequest]:
    """
    Find request by matching path pattern.

    Fallback for when exact path match fails. Tries:
    1. Match by filename
    2. Match by parent directory + filename
    """
    # Extract filename from path
    parts = relative_path.split("/")
    if not parts:
        return None

    filename = parts[-1]

    # Try matching by filename ending
    stmt = select(MediaRequest).where(
        MediaRequest.final_path.endswith(filename),
        MediaRequest.state.in_([
            RequestState.IMPORTING,
            RequestState.ANIME_MATCHING,
            RequestState.MATCH_FAILED,  # Include for FileMatched after manual linking
        ]),
    )
    result = await db.execute(stmt)
    requests = list(result.scalars().all())

    if len(requests) == 1:
        return requests[0]

    # If multiple matches, try to narrow by parent directory
    if len(requests) > 1 and len(parts) >= 2:
        parent_dir = parts[-2]
        for request in requests:
            if request.final_path and parent_dir in request.final_path:
                return request

    # Last resort: return first match if any
    return requests[0] if requests else None


async def handle_shoko_file_not_matched(event: "FileEvent", db: "AsyncSession") -> None:
    """
    Process a Shoko FileNotMatched event.

    Handles both:
    - Movies: Find request, auto-link to episode 1
    - TV Episodes: Find episode record, auto-link to specific episode number

    Falls back to MATCH_FAILED state if auto-linking fails.
    """
    from app.services.shoko_auto_linker import attempt_auto_link, attempt_episode_auto_link

    if not settings.ENABLE_SHOKO:
        return

    # Build full path for lookup
    media_prefix = settings.MEDIA_PATH_PREFIX.rstrip("/")
    full_path = f"{media_prefix}/{event.relative_path}"

    # First, try to find a TV episode by path
    episode = await find_episode_by_path(db, full_path, event.relative_path)
    if episode:
        await _handle_tv_episode_not_matched(episode, event, db)
        return

    # If not an episode, try to find a movie request
    request = await find_request_by_path(db, full_path)
    if not request:
        request = await find_request_by_path_pattern(db, event.relative_path)

    if not request:
        logger.debug(f"[FILE-NOT-MATCHED] No request/episode found for: {event.relative_path}")
        return

    # Only process anime requests in IMPORTING or ANIME_MATCHING state
    if request.state not in (RequestState.IMPORTING, RequestState.ANIME_MATCHING):
        return

    logger.info(f"[FILE-NOT-MATCHED] Attempting auto-link for movie: {request.title}")

    # Attempt auto-linking (movie flow)
    success, message = await attempt_auto_link(request, event.file_id, db)

    if success:
        await state_machine.transition(
            request,
            RequestState.ANIME_MATCHING,
            db,
            service="shoko",
            event_type="AutoLinked",
            details=message,
            raw_data={"file_id": event.file_id, "auto_linked": True},
        )
        await db.commit()
        await broadcaster.broadcast_update(request)
    else:
        request.match_failure_reason = message
        await state_machine.transition(
            request,
            RequestState.MATCH_FAILED,
            db,
            service="shoko",
            event_type="MatchFailed",
            details=f"Auto-link failed: {message}",
            raw_data={"file_id": event.file_id, "relative_path": event.relative_path},
        )
        await db.commit()
        await broadcaster.broadcast_update(request)
        logger.warning(f"[FILE-NOT-MATCHED] {request.title} -> MATCH_FAILED: {message}")


async def _handle_tv_episode_not_matched(
    episode: Episode, event: "FileEvent", db: "AsyncSession"
) -> None:
    """Handle FileNotMatched for a TV episode.

    Attempts to auto-link the specific episode.
    """
    from app.services.shoko_auto_linker import attempt_episode_auto_link

    request = episode.request
    if not request:
        return

    logger.info(
        f"[FILE-NOT-MATCHED] Attempting auto-link for TV episode: "
        f"{request.title} S{episode.season_number}E{episode.episode_number}"
    )

    # Attempt auto-linking with specific episode number
    success, message = await attempt_episode_auto_link(
        request=request,
        episode=episode,
        file_id=event.file_id,
        db=db,
    )

    if success:
        # Episode stays in ANIME_MATCHING, will get FileMatched event
        logger.info(f"[FILE-NOT-MATCHED] Episode auto-linked: {message}")
    else:
        # Mark episode as MATCH_FAILED
        episode.state = EpisodeState.MATCH_FAILED
        await db.commit()

        # Recalculate parent request state
        # Reload request with all episodes for accurate aggregation
        stmt = (
            select(MediaRequest)
            .options(selectinload(MediaRequest.episodes))
            .where(MediaRequest.id == request.id)
        )
        result = await db.execute(stmt)
        request = result.scalar_one()

        new_state = calculate_aggregate_state(request)
        if new_state != request.state:
            request.match_failure_reason = f"Episode S{episode.season_number}E{episode.episode_number}: {message}"
            await state_machine.transition(
                request,
                new_state,  # Could be MATCH_FAILED if all eps failed
                db,
                service="shoko",
                event_type="EpisodeMatchFailed",
                details=f"Episode S{episode.season_number}E{episode.episode_number} auto-link failed",
                raw_data={"file_id": event.file_id, "episode_id": episode.id},
            )
            await db.commit()

        await broadcaster.broadcast_update(request)
        logger.warning(
            f"[FILE-NOT-MATCHED] {request.title} S{episode.season_number}E{episode.episode_number} "
            f"-> MATCH_FAILED: {message}"
        )


async def find_episode_by_path(
    db: "AsyncSession", full_path: str, relative_path: str
) -> Optional[Episode]:
    """
    Find TV episode by file path.

    Used for anime TV shows where Shoko sends per-episode events.

    Args:
        db: Database session
        full_path: Full path with /data/ prefix
        relative_path: Shoko's relative path

    Returns:
        Episode if found, None otherwise
    """
    # Try exact path match first
    stmt = (
        select(Episode)
        .options(selectinload(Episode.request))
        .where(
            Episode.final_path == full_path,
            Episode.state.in_([
                EpisodeState.IMPORTING,
                EpisodeState.ANIME_MATCHING,
                EpisodeState.MATCH_FAILED,  # Include for FileMatched after manual linking
            ]),
        )
    )
    result = await db.execute(stmt)
    episode = result.scalar_one_or_none()

    if episode:
        return episode

    # Try matching by filename
    parts = relative_path.split("/")
    if not parts:
        return None

    filename = parts[-1]

    stmt = (
        select(Episode)
        .options(selectinload(Episode.request))
        .where(
            Episode.final_path.endswith(filename),
            Episode.state.in_([
                EpisodeState.IMPORTING,
                EpisodeState.ANIME_MATCHING,
                EpisodeState.MATCH_FAILED,  # Include for FileMatched after manual linking
            ]),
        )
    )
    result = await db.execute(stmt)
    episodes = list(result.scalars().all())

    if len(episodes) == 1:
        return episodes[0]

    # If multiple matches, try to narrow by parent directory
    if len(episodes) > 1 and len(parts) >= 2:
        parent_dir = parts[-2]
        for ep in episodes:
            if ep.final_path and parent_dir in ep.final_path:
                return ep

    # Return first match if any
    return episodes[0] if episodes else None
