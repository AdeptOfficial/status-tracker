"""Shoko SignalR client for real-time file matching events.

Shoko uses SignalR (Microsoft's WebSocket-based protocol) for push notifications
instead of traditional webhooks. This client maintains a persistent connection
to receive FileMatched events when anime files are identified.

SignalR Hub: http://shoko:8111/signalr/aggregate?feeds=shoko,file
Events: file:matched, file:deleted, file:relocated (Shoko 5.x+)

Connection states:
- DISCONNECTED: Not connected
- CONNECTING: Connection in progress
- CONNECTED: Connected and receiving events
- RECONNECTING: Lost connection, attempting to reconnect

HTTP API:
- POST /api/v3/Action/RemoveMissingFiles/{removeFromMyList} - Remove entries for missing files
"""

import asyncio
import enum
import logging
from dataclasses import dataclass
from typing import Callable, Awaitable, Optional

import httpx
from pysignalr.client import SignalRClient
from pysignalr.messages import CompletionMessage

from app.config import settings

logger = logging.getLogger(__name__)


class ConnectionState(enum.Enum):
    """SignalR connection states."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"


@dataclass
class FileEvent:
    """Parsed Shoko file event."""
    file_id: int
    managed_folder_id: int
    relative_path: str
    has_cross_references: bool
    event_type: str  # "matched", "deleted", "relocated"


class ShokoClient:
    """
    Persistent SignalR connection to Shoko Server.

    Handles:
    - Connection with API key authentication
    - Automatic reconnection with configurable backoff
    - Event parsing and callback dispatch

    Usage:
        client = ShokoClient()
        client.on_file_matched(my_callback)
        await client.start()  # Runs until stopped
        await client.stop()
    """

    def __init__(
        self,
        host: str = settings.SHOKO_HOST,
        port: int = settings.SHOKO_PORT,
        api_key: str = settings.SHOKO_API_KEY,
        reconnect_intervals: Optional[list[int]] = None,
    ):
        self.host = host
        self.port = port
        self.api_key = api_key
        self.reconnect_intervals = reconnect_intervals or settings.shoko_reconnect_intervals_list

        self._state = ConnectionState.DISCONNECTED
        self._client: Optional[SignalRClient] = None
        self._stop_event = asyncio.Event()
        self._reconnect_attempt = 0

        # Event callbacks
        self._file_matched_callbacks: list[Callable[[FileEvent], Awaitable[None]]] = []

    @property
    def state(self) -> ConnectionState:
        """Current connection state."""
        return self._state

    @property
    def hub_url(self) -> str:
        """Full SignalR hub URL with feeds parameter."""
        return f"http://{self.host}:{self.port}/signalr/aggregate?feeds=shoko,file"

    def on_file_matched(self, callback: Callable[[FileEvent], Awaitable[None]]) -> None:
        """Register callback for file matched events."""
        self._file_matched_callbacks.append(callback)

    async def start(self) -> None:
        """
        Start the SignalR connection and run until stopped.

        This method runs indefinitely, handling reconnections automatically.
        Call stop() to exit gracefully.
        """
        if not self.api_key:
            logger.warning("Shoko API key not configured, SignalR connection disabled")
            return

        self._stop_event.clear()

        while not self._stop_event.is_set():
            try:
                await self._connect_and_run()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Shoko SignalR error: {e}")
                await self._handle_reconnect()

        self._state = ConnectionState.DISCONNECTED
        logger.info("Shoko SignalR client stopped")

    async def stop(self) -> None:
        """Stop the SignalR connection gracefully."""
        self._stop_event.set()
        if self._client:
            try:
                await self._client.close()
            except Exception as e:
                logger.debug(f"Error closing SignalR client: {e}")
            self._client = None

    async def is_healthy(self) -> bool:
        """Check if connection is healthy."""
        return self._state == ConnectionState.CONNECTED

    async def _connect_and_run(self) -> None:
        """Establish connection and process messages."""
        self._state = ConnectionState.CONNECTING
        logger.info(f"Connecting to Shoko SignalR hub: {self.hub_url}")

        # Create SignalR client with API key auth
        self._client = SignalRClient(
            self.hub_url,
            access_token_factory=lambda: self.api_key,
            headers={"apikey": self.api_key},
        )

        # Register connection lifecycle callbacks
        # on_open fires when WebSocket connection is established
        self._client.on_open(self._on_connected)
        self._client.on_close(self._on_disconnected)
        self._client.on_error(self._on_error)

        # Register event handlers
        self._client.on("ReceiveMessage", self._handle_message)
        # Legacy event format (Shoko 4.x)
        self._client.on("ShokoEvent:FileMatched", self._handle_legacy_file_matched)
        # Movie events (Shoko sends these for anime movies instead of file events)
        self._client.on("ShokoEvent:MovieUpdated", self._handle_movie_updated)
        # Modern event format (Shoko 5.x+)
        self._client.on("file:matched", self._handle_file_matched)
        self._client.on("file:deleted", self._handle_file_deleted)
        self._client.on("file:relocated", self._handle_file_relocated)

        # Connect and run - this blocks until connection closes or errors
        # State is set to CONNECTED via the on_open callback
        await self._client.run()

    async def _on_connected(self) -> None:
        """Called when WebSocket connection is established."""
        self._state = ConnectionState.CONNECTED
        self._reconnect_attempt = 0
        logger.info("Connected to Shoko SignalR hub")

    async def _on_disconnected(self) -> None:
        """Called when WebSocket connection is closed."""
        if self._state != ConnectionState.DISCONNECTED:
            logger.info("Disconnected from Shoko SignalR hub")
            # State will be set to RECONNECTING by _handle_reconnect

    async def _on_error(self, error: Exception) -> None:
        """Called when WebSocket encounters an error."""
        logger.error(f"Shoko SignalR WebSocket error: {error}")

    async def _handle_reconnect(self) -> None:
        """Handle reconnection with backoff."""
        if self._stop_event.is_set():
            return

        self._state = ConnectionState.RECONNECTING

        # Get delay from intervals list (stay at last value if exceeded)
        delay = self.reconnect_intervals[
            min(self._reconnect_attempt, len(self.reconnect_intervals) - 1)
        ]

        logger.info(f"Reconnecting in {delay}s (attempt {self._reconnect_attempt + 1})")
        self._reconnect_attempt += 1

        try:
            await asyncio.wait_for(
                self._stop_event.wait(),
                timeout=delay,
            )
        except asyncio.TimeoutError:
            pass  # Timeout means we should try reconnecting

    async def _handle_message(self, message: CompletionMessage) -> None:
        """Handle generic messages (for debugging/logging)."""
        logger.debug(f"Shoko SignalR message: {message}")

    async def _handle_legacy_file_matched(self, *args) -> None:
        """Handle legacy ShokoEvent:FileMatched events (Shoko 4.x)."""
        try:
            # Legacy format passes data as positional args
            if args:
                data = args[0] if isinstance(args[0], dict) else {"raw": args}
                event = self._parse_file_event(data, "matched")
                await self._dispatch_file_matched(event)
        except Exception as e:
            logger.error(f"Error handling legacy file matched event: {e}")

    async def _handle_file_matched(self, *args) -> None:
        """Handle file:matched events (Shoko 5.x+)."""
        try:
            if args:
                data = args[0] if isinstance(args[0], dict) else {"raw": args}
                event = self._parse_file_event(data, "matched")
                await self._dispatch_file_matched(event)
        except Exception as e:
            logger.error(f"Error handling file matched event: {e}")

    async def _handle_movie_updated(self, *args) -> None:
        """Handle ShokoEvent:MovieUpdated events (anime movies).

        Shoko sends MovieUpdated instead of FileMatched for anime movies.
        We extract the file info and treat it like a file matched event.
        """
        try:
            logger.info(f"Movie updated event received: {args}")
            if args:
                data = args[0] if isinstance(args[0], dict) else {"raw": args}

                # MovieUpdated has different structure - try to extract file info
                # Common fields: MovieId, RelativePath, or nested FileInfo
                file_info = data.get("FileInfo", data)

                event = FileEvent(
                    file_id=file_info.get("FileId", file_info.get("fileId", data.get("MovieId", 0))),
                    managed_folder_id=file_info.get("ManagedFolderId", file_info.get("managedFolderId", 0)),
                    relative_path=file_info.get("RelativePath", file_info.get("relativePath", "")),
                    # Movies are typically matched when we get this event
                    has_cross_references=True,
                    event_type="movie_updated",
                )

                if event.relative_path:
                    await self._dispatch_file_matched(event)
                else:
                    logger.debug(f"MovieUpdated event missing path, raw data: {data}")
        except Exception as e:
            logger.error(f"Error handling movie updated event: {e}")

    async def _handle_file_deleted(self, *args) -> None:
        """Handle file:deleted events."""
        logger.debug(f"File deleted event: {args}")
        # Not used for status tracking currently

    async def _handle_file_relocated(self, *args) -> None:
        """Handle file:relocated events."""
        logger.debug(f"File relocated event: {args}")
        # Not used for status tracking currently

    def _parse_file_event(self, data: dict, event_type: str) -> FileEvent:
        """Parse raw SignalR data into FileEvent."""
        return FileEvent(
            file_id=data.get("FileId", data.get("fileId", 0)),
            managed_folder_id=data.get("ManagedFolderId", data.get("managedFolderId", 0)),
            relative_path=data.get("RelativePath", data.get("relativePath", "")),
            has_cross_references=data.get("HasCrossReferences", data.get("hasCrossReferences", False)),
            event_type=event_type,
        )

    async def _dispatch_file_matched(self, event: FileEvent) -> None:
        """Dispatch file matched event to all registered callbacks."""
        logger.info(
            f"Shoko file matched: {event.relative_path} "
            f"(cross-refs: {event.has_cross_references})"
        )

        for callback in self._file_matched_callbacks:
            try:
                await callback(event)
            except Exception as e:
                logger.error(f"Error in file matched callback: {e}")


# Global instance (lazy initialization)
_shoko_client: Optional[ShokoClient] = None


def get_shoko_client() -> ShokoClient:
    """Get or create the global Shoko client."""
    global _shoko_client
    if _shoko_client is None:
        _shoko_client = ShokoClient()
    return _shoko_client


class ShokoHTTPClient:
    """
    HTTP client for Shoko Server actions.

    Used for triggering server-side operations like removing entries
    for files that no longer exist on disk.
    """

    def __init__(
        self,
        host: str = settings.SHOKO_HOST,
        port: int = settings.SHOKO_PORT,
        api_key: str = settings.SHOKO_API_KEY,
    ):
        self.host = host
        self.port = port
        self.api_key = api_key
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def base_url(self) -> str:
        """Base URL for Shoko API."""
        return f"http://{self.host}:{self.port}"

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=60.0,  # Longer timeout - scan can take time
                headers={
                    "apikey": self.api_key,
                    "Content-Type": "application/json",
                }
            )
        return self._client

    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def remove_missing_files(self, remove_from_mylist: bool = True) -> tuple[bool, str]:
        """
        Trigger Shoko to remove entries for files that no longer exist on disk.

        This is a global operation that scans all managed folders and removes
        database entries where the underlying file is missing. Useful after
        Sonarr/Radarr deletes files.

        Args:
            remove_from_mylist: If True, also remove from AniDB MyList

        Returns:
            Tuple of (success, message)
        """
        if not self.api_key:
            return False, "Shoko API key not configured"

        try:
            client = await self._get_client()
            # Shoko v3 API: GET /api/v3/Action/RemoveMissingFiles/{removeFromMyList}
            response = await client.get(
                f"/api/v3/Action/RemoveMissingFiles/{str(remove_from_mylist).lower()}"
            )

            if response.status_code in (200, 204):
                logger.info("Triggered Shoko RemoveMissingFiles scan")
                return True, "RemoveMissingFiles scan triggered"
            else:
                error_msg = f"RemoveMissingFiles failed with status {response.status_code}"
                try:
                    error_data = response.json()
                    if "message" in error_data:
                        error_msg = error_data["message"]
                    elif "Message" in error_data:
                        error_msg = error_data["Message"]
                except Exception:
                    pass
                logger.error(f"Shoko RemoveMissingFiles failed: {error_msg}")
                return False, error_msg

        except httpx.RequestError as e:
            error_msg = f"Network error: {e}"
            logger.error(f"Request error calling Shoko RemoveMissingFiles: {e}")
            return False, error_msg
        except Exception as e:
            error_msg = f"Unexpected error: {e}"
            logger.error(f"Unexpected error calling Shoko RemoveMissingFiles: {e}")
            return False, error_msg

    async def health_check(self) -> bool:
        """Check if Shoko Server is reachable."""
        if not self.api_key:
            return False
        try:
            client = await self._get_client()
            response = await client.get("/api/v3/Init/Status")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Shoko health check failed: {e}")
            return False


# Singleton HTTP client instance
shoko_http_client = ShokoHTTPClient()
