"""Base class for service plugins.

Each plugin handles webhooks from a specific service (Jellyseerr, Sonarr, etc.)
and defines what states it can transition requests to.

To add a new service:
1. Create a new file in app/plugins/ (e.g., lidarr.py)
2. Subclass ServicePlugin
3. Implement handle_webhook() at minimum
4. The plugin loader will auto-discover it
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

from app.models import RequestState

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.models import MediaRequest


class ServicePlugin(ABC):
    """
    Base class for service integrations.

    Each plugin should:
    - Define a unique name (used in webhook URL: /hooks/{name})
    - List states it can transition to
    - List correlation fields it uses to match requests
    - Implement handle_webhook() to process incoming events
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Unique plugin identifier.
        Used in webhook URL: POST /hooks/{name}
        Examples: 'jellyseerr', 'sonarr', 'qbittorrent'
        """
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name for UI display."""
        pass

    @property
    def states_provided(self) -> list[RequestState]:
        """
        States this plugin can transition requests to.
        Used for documentation and validation.
        """
        return []

    @property
    def correlation_fields(self) -> list[str]:
        """
        Fields used to match incoming events to existing requests.
        Examples: 'tmdb_id', 'tvdb_id', 'qbit_hash', 'jellyseerr_id'
        """
        return []

    @property
    def requires_polling(self) -> bool:
        """
        Whether this plugin needs background polling.
        True for services without webhooks (e.g., qBittorrent progress).
        """
        return False

    @property
    def poll_interval(self) -> int:
        """Polling interval in seconds (if requires_polling is True)."""
        return 5

    async def handle_webhook(
        self, payload: dict, db: "AsyncSession"
    ) -> Optional["MediaRequest"]:
        """
        Process incoming webhook from this service.

        Args:
            payload: Parsed JSON webhook body
            db: Database session for queries and updates

        Returns:
            The affected MediaRequest if one was found/created, None otherwise.
            Returning a request triggers SSE broadcast to connected clients.
        """
        return None

    async def poll(self, db: "AsyncSession") -> list["MediaRequest"]:
        """
        Background polling task (if requires_polling is True).

        Called every poll_interval seconds.
        Returns list of requests that were updated (triggers SSE broadcast).
        """
        return []

    def get_timeline_details(self, event_data: dict) -> str:
        """
        Format event data for human-readable timeline display.

        Args:
            event_data: Data from the webhook/poll event

        Returns:
            Human-readable string like "WEBDL-1080p from 1337x"
        """
        return ""
