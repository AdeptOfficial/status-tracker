"""Jellyfin plugin - confirms availability and provides deep links.

Jellyfin sends webhooks when items are added to the library. This plugin
marks requests as AVAILABLE and stores the Jellyfin ID for "Watch Now" links.

Webhook setup in Jellyfin:
  1. Install the Webhook plugin from Plugin Catalog
  2. Dashboard → Plugins → Webhook → Add Generic Destination
  3. Webhook URL: http://status-tracker:8000/hooks/jellyfin
  4. Enable: Item Added
  5. Item Type: Movie, Episode

Webhook payload includes provider IDs (TMDB, TVDB) which we use to correlate
with existing requests.
"""

import logging
from typing import TYPE_CHECKING, Optional

from app.core.plugin_base import ServicePlugin
from app.core.correlator import correlator
from app.core.state_machine import state_machine
from app.models import MediaRequest, MediaType, RequestState

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class JellyfinPlugin(ServicePlugin):
    """Handles Jellyfin webhook events for library additions."""

    @property
    def name(self) -> str:
        return "jellyfin"

    @property
    def display_name(self) -> str:
        return "Jellyfin"

    @property
    def states_provided(self) -> list[RequestState]:
        return [RequestState.AVAILABLE]

    @property
    def correlation_fields(self) -> list[str]:
        return ["tmdb_id", "tvdb_id", "jellyfin_id"]

    async def handle_webhook(
        self, payload: dict, db: "AsyncSession"
    ) -> Optional[MediaRequest]:
        """
        Process Jellyfin webhook.

        Jellyfin Webhook plugin payload structure:
        {
            "NotificationType": "ItemAdded",
            "Timestamp": "2024-01-15T12:00:00Z",
            "UtcTimestamp": "2024-01-15T12:00:00Z",
            "Name": "Movie Name",
            "Overview": "Description...",
            "ItemId": "abc123...",
            "ItemType": "Movie" | "Episode" | "Series",
            "Year": 2024,
            "SeriesName": "Series Name",  # For episodes
            "SeasonNumber": 1,            # For episodes
            "EpisodeNumber": 1,           # For episodes
            "Provider_tmdb": "12345",
            "Provider_tvdb": "67890",
            "Provider_imdb": "tt1234567",
            ...
        }
        """
        notification_type = payload.get("NotificationType", "")
        item_type = payload.get("ItemType", "")
        item_name = payload.get("Name", "Unknown")

        logger.info(f"Jellyfin webhook: {notification_type} - {item_type} - {item_name}")

        # Only process ItemAdded notifications
        if notification_type != "ItemAdded":
            logger.debug(f"Ignoring Jellyfin notification type: {notification_type}")
            return None

        # Only process Movies and Episodes
        if item_type not in ("Movie", "Episode"):
            logger.debug(f"Ignoring Jellyfin item type: {item_type}")
            return None

        # Extract provider IDs
        tmdb_id = self._parse_provider_id(payload.get("Provider_tmdb"))
        tvdb_id = self._parse_provider_id(payload.get("Provider_tvdb"))
        jellyfin_id = payload.get("ItemId", "")

        if not tmdb_id and not tvdb_id:
            logger.debug(f"No provider IDs in Jellyfin webhook for: {item_name}")
            return None

        # Find matching request
        request = await correlator.find_by_any(
            db,
            tmdb_id=tmdb_id,
            tvdb_id=tvdb_id,
        )

        if not request:
            logger.debug(
                f"No matching request found for Jellyfin item: {item_name} "
                f"(tmdb={tmdb_id}, tvdb={tvdb_id})"
            )
            return None

        # Skip if already available
        if request.state == RequestState.AVAILABLE:
            logger.debug(f"Request already available: {request.title}")
            # Still update Jellyfin ID if missing
            if not request.jellyfin_id and jellyfin_id:
                request.jellyfin_id = jellyfin_id
            return request

        # Store Jellyfin ID for deep links
        if jellyfin_id:
            request.jellyfin_id = jellyfin_id

        # Update year if not set (for movies)
        if not request.year and payload.get("Year"):
            request.year = payload.get("Year")

        # Build details string
        details = f"Added to library: {item_name}"
        if item_type == "Episode":
            series = payload.get("SeriesName", "")
            season = payload.get("SeasonNumber", 0)
            episode = payload.get("EpisodeNumber", 0)
            if series:
                details = f"Added: {series} S{season:02d}E{episode:02d}"

        # Transition to AVAILABLE
        await state_machine.transition(
            request,
            RequestState.AVAILABLE,
            db,
            service=self.name,
            event_type="Added",
            details=details,
            raw_data=payload,
        )

        logger.info(f"Jellyfin added: {request.title} → AVAILABLE")
        return request

    def _parse_provider_id(self, value: Optional[str]) -> Optional[int]:
        """Parse provider ID string to int, handling None and empty strings."""
        if not value:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None

    def get_timeline_details(self, event_data: dict) -> str:
        """Format event for timeline display."""
        item_name = event_data.get("Name", "")
        item_type = event_data.get("ItemType", "")

        if item_type == "Episode":
            series = event_data.get("SeriesName", "")
            season = event_data.get("SeasonNumber", 0)
            episode = event_data.get("EpisodeNumber", 0)
            return f"Added: {series} S{season:02d}E{episode:02d}" if series else f"Added: {item_name}"

        return f"Added to library" if not item_name else f"Added: {item_name}"
