"""Jellyseerr plugin - handles media request webhooks.

Jellyseerr is the entry point for most requests. It sends webhooks for:
- Request created (PENDING/REQUESTED)
- Request approved (APPROVED)
- Request available (already in library)
- Request failed

Webhook setup in Jellyseerr:
  Settings -> Notifications -> Webhook
  URL: http://status-tracker:8000/hooks/jellyseerr
  Enable: Request Pending, Request Approved, Media Available, Media Failed
"""

import asyncio
import logging
import re
from typing import TYPE_CHECKING, Optional

from datetime import datetime

from app.core.plugin_base import ServicePlugin
from app.core.correlator import correlator
from app.core.state_machine import state_machine
from app.models import MediaRequest, MediaType, RequestState, EpisodeState
from app.clients.jellyfin import jellyfin_client
from app.clients.jellyseerr import jellyseerr_client
from app.database import async_session_maker
from app.services.anime_title_sync import sync_anime_titles_background

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def parse_year_from_subject(subject: str) -> Optional[int]:
    """Extract year from title like 'Movie Name (2020)'."""
    match = re.search(r"\((\d{4})\)$", subject.strip())
    if match:
        return int(match.group(1))
    return None


def parse_title_from_subject(subject: str) -> str:
    """Extract title without year from 'Movie Name (2020)'."""
    # Remove trailing (YYYY) if present
    return re.sub(r"\s*\(\d{4}\)$", "", subject.strip())


class JellyseerrPlugin(ServicePlugin):
    """Handles Jellyseerr webhook events."""

    @property
    def name(self) -> str:
        return "jellyseerr"

    @property
    def display_name(self) -> str:
        return "Jellyseerr"

    @property
    def states_provided(self) -> list[RequestState]:
        return [RequestState.REQUESTED, RequestState.APPROVED, RequestState.FAILED]

    @property
    def correlation_fields(self) -> list[str]:
        return ["jellyseerr_id", "tmdb_id", "tvdb_id"]

    async def handle_webhook(
        self, payload: dict, db: "AsyncSession"
    ) -> Optional[MediaRequest]:
        """
        Process Jellyseerr webhook.

        Payload structure (Jellyseerr notification webhook):
        {
            "notification_type": "MEDIA_PENDING" | "MEDIA_APPROVED" | etc,
            "subject": "Movie/Show Title",
            "message": "Description",
            "media": {
                "media_type": "movie" | "tv",
                "tmdbId": 12345,
                "tvdbId": 67890,  # For TV
                "status": "PENDING" | "APPROVED" | etc,
                "externalUrl": "https://www.themoviedb.org/...",
            },
            "request": {
                "request_id": 1,
                "requestedBy_username": "user",
                ...
            },
            "extra": [...]  # Additional info
        }
        """
        notification_type = payload.get("notification_type", "")
        media = payload.get("media", {})
        request_info = payload.get("request", {})

        logger.info(f"Jellyseerr webhook: {notification_type}")

        # Handle test notification early - acknowledge without creating data
        if notification_type == "TEST_NOTIFICATION":
            logger.info("Jellyseerr test notification received - connection verified")
            return None

        # Extract IDs
        jellyseerr_id = request_info.get("request_id")
        tmdb_id = media.get("tmdbId")
        tvdb_id = media.get("tvdbId")

        # Try to find existing request
        request = await correlator.find_by_any(
            db,
            jellyseerr_id=jellyseerr_id,
            tmdb_id=tmdb_id,
            tvdb_id=tvdb_id,
        )

        if notification_type == "MEDIA_PENDING":
            # New request - create if doesn't exist
            if not request:
                request = await self._create_request(payload, db)
            return request

        if notification_type == "MEDIA_AUTO_APPROVED":
            # Auto-approved request - create and immediately mark as approved
            if not request:
                request = await self._create_request(payload, db, auto_approved=True)
            return request

        if notification_type == "MEDIA_APPROVED":
            if request:
                await state_machine.transition(
                    request,
                    RequestState.APPROVED,
                    db,
                    service=self.name,
                    event_type="Approved",
                    details=f"Approved by {request_info.get('requestedBy_username', 'unknown')}",
                    raw_data=payload,
                )
            return request

        if notification_type == "MEDIA_AVAILABLE":
            # Jellyseerr detected media is available in Jellyfin
            if request:
                # Mark all episodes as available (for TV shows)
                for episode in request.episodes:
                    episode.state = EpisodeState.AVAILABLE

                # Try to find Jellyfin item ID for Watch button
                jellyfin_item = None
                item_type = "Series" if request.media_type == MediaType.TV else "Movie"

                if request.tvdb_id:
                    jellyfin_item = await jellyfin_client.find_item_by_tvdb(
                        request.tvdb_id, item_type
                    )
                if not jellyfin_item and request.tmdb_id:
                    jellyfin_item = await jellyfin_client.find_item_by_tmdb(
                        request.tmdb_id, item_type
                    )

                if jellyfin_item:
                    request.jellyfin_id = jellyfin_item.get("Id")
                    request.available_at = datetime.utcnow()
                    logger.info(
                        f"Found Jellyfin ID {request.jellyfin_id} for {request.title}"
                    )

                await state_machine.transition(
                    request,
                    RequestState.AVAILABLE,
                    db,
                    service=self.name,
                    event_type="Available",
                    details="Media available in library",
                    raw_data=payload,
                )
            return request

        if notification_type == "MEDIA_FAILED":
            if request:
                await state_machine.transition(
                    request,
                    RequestState.FAILED,
                    db,
                    service=self.name,
                    event_type="Failed",
                    details=payload.get("message", "Request failed"),
                    raw_data=payload,
                )
            return request

        # Unknown notification type
        logger.debug(f"Unhandled Jellyseerr notification: {notification_type}")
        return None

    async def _create_request(
        self, payload: dict, db: "AsyncSession", auto_approved: bool = False
    ) -> MediaRequest:
        """Create a new MediaRequest from Jellyseerr webhook."""
        media = payload.get("media", {})
        request_info = payload.get("request", {})
        extra = payload.get("extra", [])

        # Determine media type
        media_type_str = media.get("media_type", "movie")
        media_type = MediaType.TV if media_type_str == "tv" else MediaType.MOVIE

        # Extract poster URL - it's at top level as "image"
        poster_url = payload.get("image")

        # Extract overview from "message"
        overview = payload.get("message")

        # Parse year from subject like "Movie Name (2020)"
        subject = payload.get("subject", "Unknown Title")
        year = parse_year_from_subject(subject)
        title = parse_title_from_subject(subject) if year else subject

        # Parse IDs - they come as strings from Jellyseerr
        tmdb_id_str = media.get("tmdbId", "")
        tvdb_id_str = media.get("tvdbId", "")
        tmdb_id = int(tmdb_id_str) if tmdb_id_str and tmdb_id_str.isdigit() else None
        tvdb_id = int(tvdb_id_str) if tvdb_id_str and tvdb_id_str.isdigit() else None

        # Parse jellyseerr_id - also comes as string
        jellyseerr_id_str = request_info.get("request_id", "")
        jellyseerr_id = int(jellyseerr_id_str) if jellyseerr_id_str and str(jellyseerr_id_str).isdigit() else None

        # Extract requested seasons for TV (from extra array)
        requested_seasons = None
        logger.debug(f"Jellyseerr extra data: {extra}")
        for item in extra:
            if item.get("name") == "Requested Seasons":
                requested_seasons = item.get("value")
                logger.debug(f"Found requested_seasons: {requested_seasons}")
                break

        if media_type == MediaType.TV and not requested_seasons:
            logger.warning(f"TV request but no requested_seasons found in extra: {extra}")

        # Set initial state based on auto-approval
        initial_state = RequestState.APPROVED if auto_approved else RequestState.REQUESTED

        # Create the request
        request = MediaRequest(
            title=title,
            media_type=media_type,
            state=initial_state,
            jellyseerr_id=jellyseerr_id,
            tmdb_id=tmdb_id,
            tvdb_id=tvdb_id,
            requested_by=request_info.get("requestedBy_username"),
            poster_url=poster_url,
            year=year,
            overview=overview,
            requested_seasons=requested_seasons,
        )

        db.add(request)
        await db.flush()  # Get the ID

        # Add initial timeline event
        event_type = "Auto-Approved" if auto_approved else "Requested"
        details = f"Requested by {request.requested_by or 'unknown'}"
        if auto_approved:
            details += " (auto-approved)"

        await state_machine.add_event(
            request,
            db,
            service=self.name,
            event_type=event_type,
            details=details,
            raw_data=payload,
        )

        logger.info(f"Created new request: {request.title} (ID: {request.id}, auto_approved={auto_approved})")

        # Mark as new for SSE broadcast (transient flag, not stored in DB)
        request._is_new = True

        # For TV shows, query Jellyseerr for episode count at request creation
        # This enables "Searching 0/12 eps" display while Sonarr searches indexers
        # Why Jellyseerr? The webhook fires BEFORE Sonarr has the series, but
        # Jellyseerr already has TMDB data with episode counts cached
        if media_type == MediaType.TV and tmdb_id and requested_seasons:
            try:
                # Parse first season from "1" or "1,2,3" format
                first_season = int(requested_seasons.split(",")[0].strip())
                request.season = first_season

                # Query Jellyseerr for episode count (uses TMDB data)
                episode_count = await jellyseerr_client.get_tv_season_episode_count(tmdb_id, first_season)
                if episode_count:
                    request.total_episodes = episode_count
                    logger.info(f"Set total_episodes={episode_count} for {title} S{first_season:02d}")
                else:
                    logger.debug(f"Could not get episode count for {title} (TMDB {tmdb_id})")
            except (ValueError, AttributeError) as e:
                logger.warning(f"Failed to parse requested_seasons '{requested_seasons}': {e}")

        # For movies, sync alternate titles from TMDB for anime release matching
        # This runs in background to not block the webhook response
        # Uses its own database session to avoid detached instance issues
        if media_type == MediaType.MOVIE and request.tmdb_id:
            asyncio.create_task(
                sync_anime_titles_background(
                    async_session_maker,
                    request.id,
                    request.tmdb_id,
                )
            )

        return request

    def get_timeline_details(self, event_data: dict) -> str:
        """Format event for timeline display."""
        notification_type = event_data.get("notification_type", "")
        request_info = event_data.get("request", {})
        username = request_info.get("requestedBy_username", "")

        if notification_type == "MEDIA_PENDING":
            return f"Requested by {username}" if username else "New request"
        if notification_type == "MEDIA_APPROVED":
            return f"Approved by {username}" if username else "Request approved"
        if notification_type == "MEDIA_AVAILABLE":
            return "Already available in library"
        if notification_type == "MEDIA_FAILED":
            return event_data.get("message", "Request failed")

        return ""
