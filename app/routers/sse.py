"""SSE (Server-Sent Events) endpoint for real-time dashboard updates.

Why SSE over WebSocket?
- One-way server→client is exactly what we need (status updates)
- Native browser support with auto-reconnect
- Simpler to implement and debug
"""

import json
import logging
from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from app.core.broadcaster import broadcaster

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["sse"])


@router.get("/sse")
async def sse_endpoint():
    """
    SSE endpoint for real-time updates.

    Clients connect here and receive events when:
    - Request state changes (state_change)
    - Download progress updates (progress_update)
    - New requests are created (new_request)

    Event format:
        event: update
        data: {"event_type": "state_change", "request_id": 1, "request": {...}}
    """

    async def event_generator():
        """Generate SSE events from broadcaster."""
        logger.info("SSE client connecting...")

        # Send initial connected event
        yield {
            "event": "connected",
            "data": '{"status": "connected"}',
        }

        # Subscribe and yield events
        async for message in broadcaster.subscribe():
            if message is None:
                # Heartbeat - yield SSE comment to keep connection alive
                # sse_starlette handles this when we yield a comment string
                yield {"comment": "heartbeat"}
                continue

            # message is a dict with 'event' and 'data' keys
            event_name = message.get("event", "message")
            data = message.get("data", {})

            logger.debug(f"Yielding SSE event: {event_name}")
            yield {
                "event": event_name,
                "data": json.dumps(data) if isinstance(data, dict) else str(data),
            }

    return EventSourceResponse(event_generator())


@router.get("/sse/status")
async def sse_status():
    """Check SSE connection status and client count."""
    return {
        "connected_clients": broadcaster.client_count,
        "status": "healthy",
    }
