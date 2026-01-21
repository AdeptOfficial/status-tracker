"""Shoko plugin - tracks anime metadata matching via SignalR.

Shoko matches imported anime files to AniDB metadata. This plugin listens
for FileMatched events via SignalR and transitions requests accordingly.

Unlike other plugins, Shoko doesn't use webhooks - it uses SignalR for
real-time push notifications. The ShokoClient handles the connection.

State transitions:
- IMPORTING → ANIME_MATCHING: File detected by Shoko
- ANIME_MATCHING → AVAILABLE: File matched with cross-references

Path correlation:
- Sonarr stores final_path: /data/anime/shows/Show/Season 1/episode.mkv
- Shoko sends RelativePath: anime/shows/Show/Season 1/episode.mkv
- We prepend /data/ to Shoko's path to match Sonarr's final_path
"""

import logging
from typing import TYPE_CHECKING, Optional

from sqlalchemy import select

from app.config import settings
from app.core.plugin_base import ServicePlugin
from app.core.state_machine import state_machine
from app.core.broadcaster import broadcaster
from app.models import MediaRequest, RequestState

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

    Args:
        event: Parsed FileEvent from SignalR
        db: Database session
    """
    if not settings.ENABLE_SHOKO:
        return

    # Build the full path as Sonarr would see it
    # Shoko's RelativePath: anime/shows/Show/Season 1/episode.mkv
    # Sonarr's final_path: /data/anime/shows/Show/Season 1/episode.mkv
    full_path = f"/data/{event.relative_path}"

    logger.debug(f"Looking for request with path: {full_path}")

    # Find request by file path
    request = await find_request_by_path(db, full_path)

    if not request:
        # Try matching by parent directory + filename pattern
        request = await find_request_by_path_pattern(db, event.relative_path)

    if not request:
        logger.debug(f"No matching request found for path: {event.relative_path}")
        return

    # Skip if not an anime request (check if path contains /anime/)
    if request.final_path and "/anime/" not in request.final_path:
        logger.debug(f"Skipping non-anime request: {request.title}")
        return

    # Determine target state based on cross-references
    if event.has_cross_references:
        # File is fully matched to AniDB
        if request.state in (RequestState.IMPORTING, RequestState.ANIME_MATCHING):
            await state_machine.transition(
                request,
                RequestState.AVAILABLE,
                db,
                service="shoko",
                event_type="Matched",
                details="Matched to AniDB metadata",
                raw_data={
                    "file_id": event.file_id,
                    "relative_path": event.relative_path,
                    "has_cross_references": event.has_cross_references,
                },
            )
            await db.commit()
            await broadcaster.broadcast_update(request)
            logger.info(f"Shoko matched: {request.title} → AVAILABLE")
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


async def find_request_by_path(
    db: "AsyncSession", path: str
) -> Optional[MediaRequest]:
    """Find request where final_path matches the given path."""
    stmt = select(MediaRequest).where(
        MediaRequest.final_path == path,
        MediaRequest.state.in_([
            RequestState.IMPORTING,
            RequestState.ANIME_MATCHING,
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
