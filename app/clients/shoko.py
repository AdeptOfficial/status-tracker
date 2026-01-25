"""Shoko client for SignalR events and HTTP API.

Shoko uses SignalR (Microsoft's WebSocket-based protocol) for push notifications
instead of traditional webhooks. This client maintains a persistent connection
to receive FileMatched events when anime files are identified.

SignalR Hub: http://shoko:8111/signalr/aggregate?feeds=shoko,file
Events: file:matched, file:deleted, file:relocated (Shoko 5.x+)

HTTP API: http://shoko:8111/api/v3/...
Used for: removing missing files, health checks, etc.

Connection states:
- DISCONNECTED: Not connected
- CONNECTING: Connection in progress
- CONNECTED: Connected and receiving events
- RECONNECTING: Lost connection, attempting to reconnect
"""

import asyncio
import enum
import logging
from dataclasses import dataclass
from typing import Callable, Awaitable, Optional, Tuple

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

        # Additional Shoko events for visibility/debugging
        self._client.on("ShokoEvent:FileDetected", self._handle_file_detected)
        self._client.on("ShokoEvent:FileHashed", self._handle_file_hashed)
        self._client.on("ShokoEvent:SeriesUpdated", self._handle_series_updated)
        self._client.on("ShokoEvent:OnConnected", self._handle_shoko_connected)
        self._client.on("ShokoEvent:EpisodeUpdated", self._handle_episode_updated)
        self._client.on("ShokoEvent:FileNotMatched", self._handle_file_not_matched)

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
            # Shoko sends data as ([{...}],) - list wrapped in tuple
            if args:
                raw = args[0]
                if isinstance(raw, list) and len(raw) > 0:
                    data = raw[0]
                elif isinstance(raw, dict):
                    data = raw
                else:
                    data = {"raw": args}
                # Debug: log raw payload to understand Shoko's event structure
                logger.debug(f"Legacy FileMatched raw data: {data}")

                # Shoko 4.x may nest file info under FileInfo key
                file_info = data.get("FileInfo", data)
                event = self._parse_file_event(file_info, "matched")

                # Also check top-level data for cross-refs if not in file_info
                if not event.has_cross_references:
                    event.has_cross_references = data.get("HasCrossReferences", data.get("hasCrossReferences", False))

                # If path is still empty, try alternative field names
                if not event.relative_path:
                    event.relative_path = (
                        data.get("FileName", "") or
                        data.get("filename", "") or
                        file_info.get("FileName", "") or
                        file_info.get("filename", "")
                    )
                    if event.relative_path:
                        logger.debug(f"Used fallback field for path: {event.relative_path}")

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

        Shoko sends MovieUpdated events with structure like:
        [{'Source': 'TMDB', 'Reason': 'Added', 'MovieID': 198375, 'ShokoSeriesIDs': [...]}]

        We filter for 'Added' reason (final event indicating movie is ready)
        and trigger Jellyfin verification using the MovieID (TMDB ID).
        """
        try:
            logger.info(f"Movie updated event received: {args}")
            if not args:
                return

            # Handle both list and dict formats
            raw_data = args[0] if args else []
            updates = raw_data if isinstance(raw_data, list) else [raw_data]

            for update in updates:
                if not isinstance(update, dict):
                    continue

                reason = update.get("Reason", "")
                movie_id = update.get("MovieID")  # This is the TMDB ID
                source = update.get("Source", "")

                # Skip non-final events (ImageAdded, etc.)
                if reason != "Added":
                    logger.debug(f"[MOVIE UPDATED] Skipping reason '{reason}' (not 'Added')")
                    continue

                if not movie_id:
                    logger.warning(f"[MOVIE UPDATED] 'Added' event missing MovieID: {update}")
                    continue

                logger.info(
                    f"[MOVIE UPDATED] Added event for TMDB {movie_id} (source: {source}) - "
                    f"triggering Jellyfin verification"
                )

                # Directly trigger Jellyfin verification for this TMDB ID
                # This runs as a background task to not block SignalR processing
                import asyncio
                from app.services.jellyfin_verifier import verify_movie_by_tmdb
                asyncio.create_task(verify_movie_by_tmdb(movie_id))

        except Exception as e:
            logger.error(f"Error handling movie updated event: {e}", exc_info=True)

    async def _handle_file_deleted(self, *args) -> None:
        """Handle file:deleted events."""
        logger.debug(f"File deleted event: {args}")
        # Not used for status tracking currently

    async def _handle_file_relocated(self, *args) -> None:
        """Handle file:relocated events."""
        logger.debug(f"File relocated event: {args}")
        # Not used for status tracking currently

    async def _handle_file_detected(self, *args) -> None:
        """Handle ShokoEvent:FileDetected events.

        Fired when Shoko detects a new file in a watch folder.
        Could be used as early signal that import is starting.
        """
        try:
            if args:
                # Shoko sends data as ([{...}],) - list wrapped in tuple
                raw = args[0]
                if isinstance(raw, list) and len(raw) > 0:
                    data = raw[0]
                elif isinstance(raw, dict):
                    data = raw
                else:
                    data = {"raw": args}
                file_info = data.get("FileInfo", data)
                relative_path = (
                    file_info.get("RelativePath", "") or
                    file_info.get("relativePath", "") or
                    data.get("FileName", "") or
                    data.get("filename", "")
                )
                logger.info(f"Shoko file detected: {relative_path or '(no path)'}")
                logger.debug(f"FileDetected raw data: {data}")
        except Exception as e:
            logger.error(f"Error handling file detected event: {e}")

    async def _handle_file_hashed(self, *args) -> None:
        """Handle ShokoEvent:FileHashed events.

        Fired when Shoko finishes hashing a file. Indicates processing progress.
        """
        try:
            if args:
                data = args[0] if isinstance(args[0], dict) else {"raw": args}
                file_info = data.get("FileInfo", data)
                relative_path = (
                    file_info.get("RelativePath", "") or
                    file_info.get("relativePath", "") or
                    data.get("FileName", "")
                )
                logger.debug(f"Shoko file hashed: {relative_path or '(no path)'}")
        except Exception as e:
            logger.error(f"Error handling file hashed event: {e}")

    async def _handle_series_updated(self, *args) -> None:
        """Handle ShokoEvent:SeriesUpdated events.

        Fired when series metadata is updated. Could trigger verification.
        """
        try:
            if args:
                # Shoko sends data as ([{...}],) - list wrapped in tuple
                raw = args[0]
                if isinstance(raw, list) and len(raw) > 0:
                    data = raw[0]
                elif isinstance(raw, dict):
                    data = raw
                else:
                    data = {"raw": args}
                series_id = data.get("SeriesId", data.get("seriesId", data.get("AnimeID", "unknown")))
                series_name = data.get("SeriesName", data.get("seriesName", ""))
                logger.info(f"Shoko series updated: {series_name or series_id}")
                logger.debug(f"SeriesUpdated raw data: {data}")
        except Exception as e:
            logger.error(f"Error handling series updated event: {e}")

    async def _handle_shoko_connected(self, *args) -> None:
        """Handle ShokoEvent:OnConnected events.

        Initial handshake event when SignalR connection is established.
        """
        logger.info("Shoko SignalR handshake received (OnConnected)")
        if args:
            logger.debug(f"OnConnected data: {args}")

    async def _handle_episode_updated(self, *args) -> None:
        """Handle ShokoEvent:EpisodeUpdated events.

        Fired when episode metadata is updated. For anime movies that AniDB
        categorizes as series, this event fires instead of MovieUpdated.

        Expected structure (from Shoko source):
        {
            "Source": "AniDB",
            "Reason": "Added",
            "EpisodeID": 12345,
            "SeriesID": 6789,
            "ShokoEpisodeIDs": [1],
            "ShokoSeriesIDs": [1]
        }
        """
        try:
            logger.info(f"[DEBUG] EpisodeUpdated raw args: {args}")
            if args:
                # Shoko sends data as ([{...}],) - list wrapped in tuple
                raw = args[0]
                if isinstance(raw, list) and len(raw) > 0:
                    data = raw[0]
                elif isinstance(raw, dict):
                    data = raw
                else:
                    data = {"raw": args}
                logger.info(f"[DEBUG] EpisodeUpdated parsed data: {data}")

                # Extract key fields for debugging
                source = data.get("Source", "unknown")
                reason = data.get("Reason", "unknown")
                episode_id = data.get("EpisodeID", "unknown")
                series_id = data.get("SeriesID", "unknown")
                shoko_episode_ids = data.get("ShokoEpisodeIDs", [])
                shoko_series_ids = data.get("ShokoSeriesIDs", [])

                logger.info(
                    f"Shoko episode updated: Source={source}, Reason={reason}, "
                    f"EpisodeID={episode_id}, SeriesID={series_id}, "
                    f"ShokoEpisodeIDs={shoko_episode_ids}, ShokoSeriesIDs={shoko_series_ids}"
                )
        except Exception as e:
            logger.error(f"Error handling episode updated event: {e}", exc_info=True)

    async def _handle_file_not_matched(self, *args) -> None:
        """Handle ShokoEvent:FileNotMatched events.

        Fired when Shoko cannot match a file to AniDB.
        """
        try:
            logger.info(f"[DEBUG] FileNotMatched raw args: {args}")
            if args:
                # Shoko sends data as ([{...}],) - list wrapped in tuple
                raw = args[0]
                if isinstance(raw, list) and len(raw) > 0:
                    data = raw[0]  # Unwrap the list
                elif isinstance(raw, dict):
                    data = raw
                else:
                    data = {"raw": args}
                logger.info(f"[DEBUG] FileNotMatched parsed data: {data}")

                # Try to extract file info
                file_info = data.get("FileInfo", data)
                relative_path = (
                    file_info.get("RelativePath", "") or
                    file_info.get("relativePath", "") or
                    data.get("FileName", "") or
                    data.get("filename", "")
                )
                logger.warning(f"Shoko file NOT matched: {relative_path or '(no path)'}")
        except Exception as e:
            logger.error(f"Error handling file not matched event: {e}", exc_info=True)

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
        if event.relative_path:
            logger.info(
                f"Shoko file matched: {event.relative_path} "
                f"(cross-refs: {event.has_cross_references})"
            )
        else:
            logger.warning(
                f"Shoko file matched with EMPTY path (file_id: {event.file_id}, "
                f"cross-refs: {event.has_cross_references}) - check debug logs for raw payload"
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


class ShokoHttpClient:
    """
    HTTP API client for Shoko Server.

    Used for actions that require HTTP API calls (not SignalR):
    - Removing missing files
    - Health checks
    - Series/file lookups
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
        self._client = httpx.AsyncClient(timeout=30.0)

    @property
    def base_url(self) -> str:
        """Base URL for Shoko API."""
        return f"http://{self.host}:{self.port}"

    def _headers(self) -> dict:
        """Get headers with API key auth."""
        return {"apikey": self.api_key}

    async def health_check(self) -> bool:
        """Check if Shoko is reachable."""
        if not self.api_key:
            return False
        try:
            resp = await self._client.get(
                f"{self.base_url}/api/v3/Init/Status",
                headers=self._headers(),
            )
            return resp.status_code == 200
        except Exception as e:
            logger.error(f"Shoko health check failed: {e}")
            return False

    async def remove_missing_files(self) -> Tuple[bool, str]:
        """
        Trigger Shoko to scan for and remove entries for missing files.

        This is the key method for deletion sync - when files are deleted
        from disk, Shoko needs to be told to scan and remove the orphaned
        database entries.

        Returns:
            Tuple of (success, message)
        """
        if not self.api_key:
            return False, "Shoko API key not configured"

        try:
            # Shoko API endpoint to remove missing files
            # GET /api/v3/Action/RemoveMissingFiles (Shoko uses GET for actions)
            resp = await self._client.get(
                f"{self.base_url}/api/v3/Action/RemoveMissingFiles",
                headers=self._headers(),
            )

            if resp.status_code in (200, 204):
                logger.info("Triggered Shoko RemoveMissingFiles scan")
                return True, "RemoveMissingFiles scan triggered - orphaned entries will be cleaned up"
            else:
                error_msg = f"Shoko RemoveMissingFiles failed: HTTP {resp.status_code}"
                logger.error(f"{error_msg} - {resp.text}")
                return False, error_msg

        except httpx.TimeoutException:
            return False, "Shoko API timeout"
        except Exception as e:
            logger.error(f"Shoko RemoveMissingFiles error: {e}")
            return False, f"Error: {e}"


# Global HTTP client instance
shoko_http_client = ShokoHttpClient()
