"""SSE broadcasting for real-time updates.

Manages connected clients and broadcasts request updates.
Used in Part 5 for live dashboard updates without page refresh.
"""

import asyncio
import json
import logging
from typing import TYPE_CHECKING, AsyncGenerator, Optional

from app.schemas import MediaRequestResponse, SSEUpdate

if TYPE_CHECKING:
    from app.models import MediaRequest

logger = logging.getLogger(__name__)

# Heartbeat interval to keep SSE connections alive (seconds)
# Proxies/browsers may timeout idle connections - this prevents that
SSE_HEARTBEAT_INTERVAL = 15

# Sentinel value for heartbeats
HEARTBEAT = object()


class Broadcaster:
    """
    Manages SSE connections and broadcasts updates to all clients.

    Usage:
        # In SSE endpoint
        async for data in broadcaster.subscribe():
            yield data

        # After state change
        await broadcaster.broadcast_update(request)
    """

    def __init__(self):
        self._clients: list[asyncio.Queue] = []

    async def subscribe(self) -> AsyncGenerator[Optional[dict], None]:
        """
        Subscribe to updates. Returns an async generator for SSE endpoint.

        Yields dicts like:
            {"event": "update", "data": {...}}

        Or None for heartbeats (SSE endpoint handles these).
        """
        queue: asyncio.Queue = asyncio.Queue()
        self._clients.append(queue)
        logger.info(f"Client connected. Total clients: {len(self._clients)}")

        try:
            while True:
                try:
                    # Wait for message with timeout for heartbeat
                    data = await asyncio.wait_for(
                        queue.get(), timeout=SSE_HEARTBEAT_INTERVAL
                    )
                    yield data
                except asyncio.TimeoutError:
                    # No message received within timeout - yield None to signal heartbeat
                    yield None
                    logger.debug("Sent SSE heartbeat")
        except asyncio.CancelledError:
            pass
        finally:
            self._clients.remove(queue)
            logger.info(f"Client disconnected. Total clients: {len(self._clients)}")

    async def broadcast(self, event_type: str, data: dict) -> None:
        """
        Broadcast an event to all connected clients.

        Args:
            event_type: SSE event name (e.g., 'update', 'progress')
            data: Dictionary to send
        """
        client_count = len(self._clients)
        logger.info(f"Broadcasting '{event_type}' to {client_count} clients")

        if not self._clients:
            logger.warning("No SSE clients connected - update will be lost")
            return

        # Put structured data in queue (SSE endpoint handles formatting)
        message = {"event": event_type, "data": data}

        # Send to all clients (non-blocking)
        for queue in self._clients:
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                logger.warning("Client queue full, skipping message")

    async def broadcast_update(
        self,
        request: "MediaRequest",
        event_type: str = "state_change",
    ) -> None:
        """
        Broadcast a request update to all connected clients.

        Args:
            request: The updated MediaRequest
            event_type: Type of update (state_change, progress_update, new_request)
        """
        logger.info(
            f"broadcast_update called: request_id={request.id}, "
            f"title='{request.title}', state='{request.state}', event_type='{event_type}'"
        )
        try:
            # Convert to response schema
            request_data = MediaRequestResponse.model_validate(request).model_dump(
                mode="json"
            )

            update = SSEUpdate(
                event_type=event_type,
                request_id=request.id,
                request=request_data,
            )

            await self.broadcast("update", update.model_dump(mode="json"))
        except Exception as e:
            logger.error(f"broadcast_update failed for request {request.id}: {e}", exc_info=True)

    @property
    def client_count(self) -> int:
        """Number of connected clients."""
        return len(self._clients)


# Global instance
broadcaster = Broadcaster()
